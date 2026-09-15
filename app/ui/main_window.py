from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from app.ai.deepseek import DeepSeekConfig, DeepSeekProvider
from app.core.automation import PyAutoGuiDriver, SafeInputController
from app.core.automation_session import AutomationSession, AutomationSettings
from app.core.calibration_store import load_calibration
from app.core.grading_engine import DryRunRecord, GradingEngine
from app.core.safety import RunState, SafetyController, install_hotkeys
from app.core.screenshot import ScreenCapture
from app.core.task_manager import load_task
from app.core.trial_service import TrialService
from app.data.calibration import CalibrationProfile
from app.data.models import Task
from app.data.paths import user_data_dir
from app.data.repository import TrialRepository
from app.data.trial_models import ErrorCategory, TrialRecord
from app.platforms.zhixue import ZhixuePlatform

from .calibration_dialog import CalibrationDialog
from .grading_panel import GradingPanel
from .task_editor import TaskEditorDialog
from .trial_panel import TrialPanel


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
    trial_record_ready = Signal(object, str, object, object)
    finished = Signal(object)

    def __init__(
        self,
        task: Task,
        profile: CalibrationProfile,
        safety: SafetyController,
        count: int,
        observation_delay: float,
        start_index: int = 1,
        trial_service: TrialService | None = None,
        capture_directory: Path | None = None,
    ) -> None:
        super().__init__()
        self.task = task
        self.profile = profile
        self.safety = safety
        self.count = count
        self.observation_delay = observation_delay
        self.start_index = start_index
        self.trial_service = trial_service
        self.capture_directory = capture_directory

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

            def result_detail(index: int, result, image: Path) -> None:
                if self.trial_service is None:
                    return
                trial_record = self.trial_service.record_ai_result(
                    index, result, image, automation_state=RunState.AI_VALIDATION.value
                )
                self.trial_record_ready.emit(
                    trial_record, str(image), result, self.trial_service.metrics()
                )

            def completed(record, image: Path) -> None:
                if self.trial_service is None or record.result is None:
                    return
                trial_record = self.trial_service.repository.get_record_for_sequence(
                    self.trial_service.session.session_id, record.index
                )
                self.trial_service.complete_automation(trial_record.record_id, record)
                trial_record = self.trial_service.repository.get_record(trial_record.record_id)
                self.trial_record_ready.emit(
                    trial_record, str(image), record.result, self.trial_service.metrics()
                )

            session = AutomationSession(
                self.task,
                provider,
                platform,
                self.safety,
                AutomationSettings(observation_delay=self.observation_delay),
                on_state=lambda state, message: self.state_changed.emit(state.value, message),
                on_result=self.result_ready.emit,
                on_result_detail=result_detail,
                on_completed=completed,
                capture_directory=self.capture_directory,
            )
            remove_hotkeys = install_hotkeys(self.safety)
            records = asyncio.run(session.run_many(self.count, start_index=self.start_index))
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
        self.setWindowTitle("AI 阅卷助手 — Phase 4")
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
        self.trial_repository: TrialRepository | None = None
        self.trial_service: TrialService | None = None
        self.trial_temp: tempfile.TemporaryDirectory | None = None
        self.trial_screenshots: dict[str, Path] = {}

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
        self.trial_mode = QCheckBox("试改模式")
        self.trial_mode.setChecked(True)
        self.run_count.setEnabled(False)
        self.trial_mode.toggled.connect(
            lambda checked: self.run_count.setEnabled(not checked and self.automation_thread is None)
        )
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
            self.trial_mode, self.pause_button, self.resume_button, self.stop_button,
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
        self.trial_panel = TrialPanel()
        self.trial_panel.review_started.connect(self.begin_trial_review)
        self.trial_panel.review_cancelled.connect(self.cancel_trial_review)
        self.trial_panel.mark_correct_requested.connect(self.mark_trial_correct)
        self.trial_panel.mark_error_requested.connect(self.mark_trial_error)
        self.trial_panel.new_session_requested.connect(self.new_trial_session)
        self.trial_panel.export_requested.connect(self.export_trial_report)
        right = QVBoxLayout()
        right.addWidget(self.panel, 3)
        right.addWidget(self.trial_panel, 2)
        content.addWidget(scroll, 3)
        content.addLayout(right, 2)
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
        if self.task is not None and self.task.task_id != task.task_id:
            self._clear_active_trial()
        self.task_path = path
        self.task = task
        self.trial_panel.set_score_step(task.score_step)
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
        self.run_count.setEnabled(idle and not self.trial_mode.isChecked())
        self.observation_delay.setEnabled(idle)
        self.trial_mode.setEnabled(idle)

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
        start_index = 1
        capture_directory = None
        trial_service = None
        if self.trial_mode.isChecked():
            if self.trial_service is None or self.trial_service.task.task_id != self.task.task_id:
                self._create_trial_session()
            assert self.trial_service is not None
            metrics = self.trial_service.metrics()
            remaining = metrics.target_count - metrics.processed
            if remaining <= 0:
                QMessageBox.information(self, "试改已完成", "当前试改会话已经达到目标份数，请新建试改会话。")
                return
            count = remaining
            start_index = metrics.processed + 1
            trial_service = self.trial_service
            assert self.trial_temp is not None
            capture_directory = Path(self.trial_temp.name)
        else:
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
            self.task,
            self.calibration,
            self.safety,
            count,
            self.observation_delay.value(),
            start_index,
            trial_service,
            capture_directory,
        )
        self.automation_worker.moveToThread(self.automation_thread)
        self.automation_thread.started.connect(self.automation_worker.run)
        self.automation_worker.state_changed.connect(self.on_automation_state)
        self.automation_worker.result_ready.connect(self.panel.show_result)
        self.automation_worker.trial_record_ready.connect(self.on_trial_record)
        self.automation_worker.finished.connect(self.on_automation_finished)
        self.automation_worker.finished.connect(self.automation_thread.quit)
        self.automation_thread.finished.connect(self.automation_worker.deleteLater)
        self.automation_thread.finished.connect(self._automation_thread_finished)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.trial_panel.set_running(True)
        self._refresh_button()
        self.automation_thread.start()

    def pause_automation(self) -> None:
        if self.safety:
            self.safety.pause()
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)

    def begin_trial_review(self) -> None:
        if self.safety:
            self.safety.lock_pause()
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(False)

    def cancel_trial_review(self) -> None:
        if self.safety:
            self.safety.unlock_pause()
            self.safety.resume()
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)

    def resume_automation(self) -> None:
        if self.safety:
            self.safety.resume()
            resumed = not self.safety.paused
            self.pause_button.setEnabled(resumed)
            self.resume_button.setEnabled(not resumed and not self.safety.pause_locked)

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
            self.resume_button.setEnabled(bool(self.safety and not self.safety.pause_locked))
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
        self.trial_panel.set_running(False)
        self._refresh_button()

    def _create_trial_session(self) -> None:
        if self.task is None:
            return
        base = user_data_dir()
        self.trial_repository = TrialRepository(base / "trials.db", base / "review_screenshots")
        self.trial_service = TrialService.start(
            self.trial_repository,
            self.task,
            target_count=self.trial_panel.target.value(),
            error_threshold_percent=Decimal(str(self.trial_panel.threshold.value())),
        )
        if self.trial_temp is not None:
            self.trial_temp.cleanup()
        self.trial_temp = tempfile.TemporaryDirectory(prefix="aigrader-trial-")
        self.trial_screenshots.clear()
        self.trial_panel.clear_current()
        self.trial_panel.show_metrics(self.trial_service.metrics())

    def new_trial_session(self) -> None:
        if self.automation_thread is not None:
            return
        if self.trial_service is not None and self.trial_service.metrics().processed:
            answer = QMessageBox.question(
                self,
                "新建试改会话",
                "当前试改统计会保留在数据库，但界面将开始一组新的统计。是否继续？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._clear_active_trial()

    def _clear_active_trial(self) -> None:
        self.trial_service = None
        self.trial_repository = None
        if self.trial_temp is not None:
            self.trial_temp.cleanup()
            self.trial_temp = None
        self.trial_screenshots.clear()
        self.trial_panel.clear_current()
        self.trial_panel.metrics.setText("尚未开始试改")

    def export_trial_report(self) -> None:
        if self.trial_service is None:
            QMessageBox.information(self, "暂无报告", "请先开始一个试改会话。")
            return
        value, _ = QFileDialog.getSaveFileName(
            self, "导出试改报告", "trial-report.json", "JSON (*.json)"
        )
        if not value:
            return
        destination = Path(value)
        if destination.suffix.lower() != ".json":
            destination = destination.with_suffix(".json")
        try:
            saved = self.trial_service.export_report(destination)
            QMessageBox.information(self, "导出成功", f"报告已保存到：\n{saved}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def on_trial_record(self, record: TrialRecord, screenshot: str, result, metrics) -> None:
        self.trial_screenshots[record.record_id] = Path(screenshot)
        self.trial_panel.set_current(record, result)
        self.trial_panel.show_metrics(metrics)

    def mark_trial_correct(self, record_id: str, correct_score: Decimal) -> None:
        if self.trial_service is None:
            return
        try:
            self.trial_service.mark_ai_correct(record_id, correct_score)
            self.trial_panel.show_metrics(self.trial_service.metrics())
            self.trial_panel.clear_current()
        except Exception as exc:
            QMessageBox.critical(self, "记录失败", str(exc))

    def mark_trial_error(
        self,
        record_id: str,
        correct_score: Decimal,
        category: ErrorCategory,
        note: str,
    ) -> None:
        if self.trial_service is None:
            return
        screenshot = self.trial_screenshots.get(record_id)
        if screenshot is None:
            self.cancel_trial_review()
            QMessageBox.critical(self, "记录失败", "当前答案截图已不可用")
            return
        try:
            self.trial_service.mark_ai_error(record_id, screenshot, correct_score, category, note)
            self.trial_panel.show_metrics(self.trial_service.metrics())
            self.trial_panel.clear_current()
            self.stop_automation()
        except Exception as exc:
            self.cancel_trial_review()
            QMessageBox.critical(self, "记录失败", str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.thread is not None or self.automation_thread is not None:
            if self.safety:
                self.safety.stop()
            QMessageBox.information(self, "正在安全停止", "后台操作尚未结束。已请求停止，请等待当前网络或截图操作返回后再关闭。")
            event.ignore()
            return
        if self.trial_temp is not None:
            self.trial_temp.cleanup()
        event.accept()
