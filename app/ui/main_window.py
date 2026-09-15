from __future__ import annotations

import asyncio
import os
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.ai.deepseek import DeepSeekConfig, DeepSeekProvider
from app.core.grading_engine import DryRunRecord, GradingEngine
from app.core.task_manager import load_task
from app.data.models import Task

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


class MainWindow(QMainWindow):
    def __init__(self, task_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("AI 阅卷助手 — Phase 2")
        self.resize(1200, 760)
        self.task: Task | None = None
        self.task_path: Path | None = None
        self.image: Path | None = None
        self.thread: QThread | None = None
        self.worker: GradeWorker | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        toolbar = QHBoxLayout()
        self.task_label = QLabel("任务：未加载")
        new_button = QPushButton("新建任务")
        load_button = QPushButton("打开任务")
        self.edit_button = QPushButton("编辑任务")
        self.edit_button.setEnabled(False)
        image_button = QPushButton("选择学生答案图片")
        self.grade_button = QPushButton("识别当前卷（Dry Run）")
        self.grade_button.setEnabled(False)
        new_button.clicked.connect(self.new_task)
        load_button.clicked.connect(self.choose_task)
        self.edit_button.clicked.connect(self.edit_task)
        image_button.clicked.connect(self.choose_image)
        self.grade_button.clicked.connect(self.grade)
        for widget in (new_button, load_button, self.edit_button, image_button, self.grade_button, self.task_label):
            toolbar.addWidget(widget)
        layout.addLayout(toolbar)

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
        self.grade_button.setEnabled(self.task is not None and self.image is not None and self.thread is None)
        self.edit_button.setEnabled(self.task is not None and self.task_path is not None)

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
