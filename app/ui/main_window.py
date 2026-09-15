from __future__ import annotations

import asyncio
import os
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from app.ai.deepseek import DeepSeekConfig, DeepSeekProvider
from app.core.automation import PyAutoGuiDriver, SafeInputController
from app.core.automation_session import AutomationSession, AutomationSettings
from app.core.calibration_store import load_calibration
from app.core.grading_engine import DryRunRecord, GradingEngine
from app.core.safety import RunState, SafetyController, install_hotkeys
from app.core.screenshot import ScreenCapture
from app.core.task_manager import load_task
from app.data.calibration import CalibrationProfile
from app.data.models import Task
from app.platforms.zhixue import ZhixuePlatform

from .calibration_dialog import CalibrationDialog
from .grading_panel import GradingPanel
from .task_editor import TaskEditorDialog


class GradeWorker(QObject):
    finished = Signal(object)

    def __init__(self, task: Task, image: Path) -> None:
        super().__init__()
        self.task = task
        self.image = image

    def run(self) -> None:
        try:
            provider = DeepSeekProvider(
                DeepSeekConfig(
                    os.environ.get("DEEPSEEK_API_KEY", ""),
                    os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                )
            )
            record = asyncio.run(GradingEngine(provider).dry_run(self.task, self.image))
        except Exception as exc:
            record = DryRunRecord(str(self.image), "", 0, None, str(exc))
        self.finished.emit(record)


class AutomationWorker(QObject):
    state_changed = Signal(str, str)
    result_ready = Signal(object)
    finished = Signal(object)

    def __init__(
        self,
        task: Task,
        profile: CalibrationProfile,
        safety: SafetyController,
        count: int,
        observation_delay: float,
    ) -> None:
        super().__init__()
        self.task = task
        self.profile = profile
        self.safety = safety
        self.count = count
        self.observation_delay = observation_delay

    def run(self) -> None:
        remove_hotkeys = lambda: None
        try:
            provider = DeepSeekProvider(
                DeepSeekConfig(
                    os.environ.get("DEEPSEEK_API_KEY", ""),
                    os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                )
            )
            input_controller = SafeInputController(PyAutoGuiDriver(), self.safety)
            platform = ZhixuePlatform(self.profile, ScreenCapture(), input_controller)
            session = AutomationSession(
                self.task,
                provider,
                platform,
                self.safety,
                AutomationSettings(observation_delay=self.observation_delay),
                on_state=lambda state, message: self.state_changed.emit(state.value, message),
                on_result=self.result_ready.emit,
            )
            remove_hotkeys = install_hotkeys(self.safety)
            records = asyncio.run(session.run_many(self.count))
        except Exception as exc:
            self.safety.stop()
            self.state_changed.emit(RunState.STOPPED.value, str(exc))
            records = []
        finally:
            remove_hotkeys()
        self.finished.emit(records)


class MainWindow(QMainWindow):
    def __init__(self, task_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("AI 阅卷助手 — Phase 2")
        self.resize(1200, 760)
        self.task: Task | None = None
        self.task_path: Path | None = None
        self.calibration: CalibrationProfile | None = None
        self.calibration_path: Path | None = None
        self.image: Path | None = None
        self.thread: QThread | None = None
        self.worker: GradeWorker | None = None
        self.automation_thread: QThread | None = None
        self.automation_worker: AutomationWorker | None = None
        self.safety: SafetyController | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        toolbar = QHBoxLayout()
        self.task_label = QLabel("任务：未加载")
        self.new_button = QPushButton("新建任务")
        self.load_button = QPushButton("打开任务")
        self.edit_button = QPushButton("编辑任务")
        self.edit_button.setEnabled(False)
        self.image_button = QPushButton("选择学生答案图片")
        self.grade_button = QPushButton("识别当前卷（Dry Run）")
        self.grade_button.setEnabled(False)
        self.new_button.clicked.connect(self.new_task)
        self.load_button.clicked.connect(self.choose_task)
        self.edit_button.clicked.connect(self.edit_task)
        self.image_button.clicked.connect(self.choose_image)
        self.grade_button.clicked.connect(self.grade)
        for widget in (
            self.new_button, self.load_button, self.edit_button, self.image_button,
            self.grade_button, self.task_label,
        ):
            toolbar.addWidget(widget)
        layout.addLayout(toolbar)

        automation_bar = QHBoxLayout()
        self.calibrate_button = QPushButton("坐标标定")
        self.calibration_label = QLabel("标定：未加载")
        self.run_count = QSpinBox()
        self.run_count.setRange(1, 20)
        self.run_count.setValue(1)
        self.observation_delay = QDoubleSpinBox()
        self.observation_delay.setRange(0, 5)
        self.observation_delay.setSingleStep(0.5)
        self.observation_delay.setValue(1)
        self.start_button = QPushButton("开始自动化测试（真实提交）")
        self.pause_button = QPushButton("暂停 F8")
        self.resume_button = QPushButton("继续 F9")
        self.stop_button = QPushButton("紧急停止 Ctrl+Alt+Q")
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.calibrate_button.clicked.connect(self.calibrate)
        self.start_button.clicked.connect(self.start_automation)
        self.pause_button.clicked.connect(self.pause_automation)
        self.resume_button.clicked.connect(self.resume_automation)
        self.stop_button.clicked.connect(self.stop_automation)
        for widget in (
            self.calibrate_button, self.calibration_label, QLabel("连续份数"), self.run_count,
            QLabel("观察秒数"), self.observation_delay, self.start_button,
            self.pause_button, self.resume_button, self.stop_button,
        ):
            automation_bar.addWidget(widget)
        layout.addLayout(automation_bar)

        content = QHBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.preview = QLabel("学生答案图片预览")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumWidth(520)
        scroll.setWidget(self.preview)
        self.panel = GradingPanel()
        content.addWidget(scroll, 3)
        content.addWidget(self.panel, 2)
        layout.addLayout(content)
        if task_path:
            self.open_task(task_path)

    def choose_task(self) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "选择任务", filter="JSON (*.json)")
        if value:
            self.open_task(Path(value))

    def new_task(self) -> None:
        value, _ = QFileDialog.getSaveFileName(self, "新建任务", "task.json", "JSON (*.json)")
        if not value:
            return
        path = Path(value)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        editor = TaskEditorDialog(path, parent=self)
        editor.task_saved.connect(self._on_task_saved)
        editor.exec()

    def edit_task(self) -> None:
        if self.task is None or self.task_path is None:
            return
        editor = TaskEditorDialog(self.task_path, self.task, self)
        editor.task_saved.connect(self._on_task_saved)
        editor.exec()

    def _on_task_saved(self, path: Path, task: Task) -> None:
        self.task_path = path
        self.task = task
        self.task_label.setText(f"任务：{task.name} 第{task.question_number}题 · 规则 v{task.rule_version}")
        self.calibration_path = path.with_suffix(".calibration.json")
        try:
            self.calibration = load_calibration(self.calibration_path)
            self.calibration_label.setText("标定：已加载" if self.calibration.page_marker else "标定：需补充进度标记")
        except Exception:
            self.calibration = None
            self.calibration_label.setText("标定：未完成")
        self._refresh_button()

    def calibrate(self) -> None:
        if self.task_path is None:
            QMessageBox.information(self, "请先选择任务", "新建或打开任务后才能保存对应标定。")
            return
        path = self.task_path.with_suffix(".calibration.json")
        dialog = CalibrationDialog(path, self.calibration, self)
        dialog.profile_saved.connect(self._on_calibration_saved)
        dialog.exec()

    def _on_calibration_saved(self, path: Path, profile: CalibrationProfile) -> None:
        self.calibration_path = path
        self.calibration = profile
        self.calibration_label.setText("标定：已保存")
        self._refresh_button()

    def open_task(self, path: Path) -> None:
        try:
            task = load_task(path)
            self._on_task_saved(path.resolve(), task)
        except Exception as exc:
            QMessageBox.critical(self, "任务无效", str(exc))

    def choose_image(self) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "选择学生答案图片", filter="Images (*.png *.jpg *.jpeg *.webp *.gif)")
        if value:
            self.image = Path(value)
            pixmap = QPixmap(value)
            self.preview.setPixmap(pixmap.scaled(700, 620, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self._refresh_button()

    def _refresh_button(self) -> None:
        idle = self.thread is None and self.automation_thread is None
        self.grade_button.setEnabled(self.task is not None and self.image is not None and idle)
        self.edit_button.setEnabled(self.task is not None and self.task_path is not None and idle)
        self.calibrate_button.setEnabled(self.task_path is not None and idle)
        calibrated = self.calibration is not None and self.calibration.page_marker is not None
        self.start_button.setEnabled(self.task is not None and calibrated and idle)
        self.new_button.setEnabled(idle)
        self.load_button.setEnabled(idle)
        self.image_button.setEnabled(idle)

    def grade(self) -> None:
        if self.task is None or self.image is None:
            return
        self.panel.show_busy()
        self.grade_button.setEnabled(False)
        self.thread = QThread(self)
        self.worker = GradeWorker(self.task, self.image)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self._refresh_button()
        self.thread.start()

    def on_finished(self, record: DryRunRecord) -> None:
        if record.error:
            self.panel.show_error(record.error)
        elif record.result:
            self.panel.show_result(record.result)

    def _thread_finished(self) -> None:
        if self.thread:
            self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self._refresh_button()

    def start_automation(self) -> None:
        if self.task is None or self.calibration is None:
            return
        count = self.run_count.value()
        answer = QMessageBox.warning(
            self,
            "确认真实提交",
            f"将连续处理最多 {count} 份并真实填写、提交分数。请保持浏览器布局不变。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.safety = SafetyController()
        self.safety.enable()
        self.automation_thread = QThread(self)
        self.automation_worker = AutomationWorker(
            self.task, self.calibration, self.safety, count, self.observation_delay.value()
        )
        self.automation_worker.moveToThread(self.automation_thread)
        self.automation_thread.started.connect(self.automation_worker.run)
        self.automation_worker.state_changed.connect(self.on_automation_state)
        self.automation_worker.result_ready.connect(self.panel.show_result)
        self.automation_worker.finished.connect(self.on_automation_finished)
        self.automation_worker.finished.connect(self.automation_thread.quit)
        self.automation_thread.finished.connect(self.automation_worker.deleteLater)
        self.automation_thread.finished.connect(self._automation_thread_finished)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self._refresh_button()
        self.automation_thread.start()

    def pause_automation(self) -> None:
        if self.safety:
            self.safety.pause()
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)

    def resume_automation(self) -> None:
        if self.safety:
            self.safety.resume()
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)

    def stop_automation(self) -> None:
        if self.safety:
            self.safety.stop()
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(False)
            self.stop_button.setEnabled(False)

    def on_automation_state(self, state: str, message: str) -> None:
        self.panel.status.setText(f"状态：{state}\n{message}")
        if state == RunState.PAUSED.value:
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)
        elif self.automation_thread is not None:
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)

    def on_automation_finished(self, records: list) -> None:
        submitted = sum(record.submitted for record in records)
        last_error = records[-1].error if records and records[-1].error else None
        message = f"已成功提交 {submitted} 份。"
        if last_error:
            message += f"\n已安全停止：{last_error}"
        QMessageBox.information(self, "自动化测试结束", message)

    def _automation_thread_finished(self) -> None:
        if self.automation_thread:
            self.automation_thread.deleteLater()
        self.automation_thread = None
        self.automation_worker = None
        self.safety = None
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self._refresh_button()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.thread is not None or self.automation_thread is not None:
            if self.safety:
                self.safety.stop()
            QMessageBox.information(self, "正在安全停止", "后台操作尚未结束。已请求停止，请等待当前网络或截图操作返回后再关闭。")
            event.ignore()
            return
        event.accept()
