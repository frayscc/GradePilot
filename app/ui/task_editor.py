from __future__ import annotations

import uuid
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.task_manager import ensure_rule_version, save_task, store_question_image
from app.data.models import Question, Rubric, RubricItem, Task


def split_lines(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


class RubricItemEditor(QGroupBox):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, item: RubricItem | None = None, *, default_part: str = "1") -> None:
        super().__init__()
        self.part = QLineEdit(item.part if item else default_part)
        self.max_score = QDoubleSpinBox()
        self.max_score.setRange(0.01, 100)
        self.max_score.setDecimals(2)
        self.max_score.setSingleStep(0.5)
        self.max_score.setValue(float(item.max_score) if item else 1)
        self.reference_answers = QTextEdit("\n".join(item.reference_answers) if item else "")
        self.reference_answers.setPlaceholderText("每行一个参考答案")
        self.reference_answers.setMaximumHeight(80)
        self.criteria = QTextEdit(item.criteria if item else "")
        self.criteria.setPlaceholderText("例如：表达出改变钩码数量即可")
        self.criteria.setMaximumHeight(80)
        self.accepted = QTextEdit("\n".join(item.accepted_expressions) if item else "")
        self.accepted.setPlaceholderText("每行一个明确接受表达，可留空")
        self.accepted.setMaximumHeight(70)
        self.rejected = QTextEdit("\n".join(item.rejected_expressions) if item else "")
        self.rejected.setPlaceholderText("每行一个明确拒绝表达，可留空")
        self.rejected.setMaximumHeight(70)
        self.require_unit = QCheckBox("必须有正确单位")
        self.exact_match = QCheckBox("必须完全匹配")
        self.forbid_typos = QCheckBox("不允许错别字")
        self.notes = QLineEdit(item.notes if item else "")
        if item:
            self.require_unit.setChecked(item.require_unit)
            self.exact_match.setChecked(item.exact_match)
            self.forbid_typos.setChecked(item.forbid_typos)

        remove_button = QPushButton("删除此空")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        header = QHBoxLayout()
        header.addWidget(QLabel("编号"))
        header.addWidget(self.part)
        header.addWidget(QLabel("满分"))
        header.addWidget(self.max_score)
        header.addStretch()
        header.addWidget(remove_button)
        layout = QVBoxLayout(self)
        layout.addLayout(header)
        form = QFormLayout()
        form.addRow("参考答案*", self.reference_answers)
        form.addRow("得分标准*", self.criteria)
        form.addRow("接受表达", self.accepted)
        form.addRow("不接受表达", self.rejected)
        flags = QHBoxLayout()
        flags.addWidget(self.require_unit)
        flags.addWidget(self.exact_match)
        flags.addWidget(self.forbid_typos)
        flags.addStretch()
        form.addRow("特殊规则", flags)
        form.addRow("其他说明", self.notes)
        layout.addLayout(form)
        self._connect_changes()
        self._refresh_title()

    def _connect_changes(self) -> None:
        for widget in (self.part, self.notes):
            widget.textChanged.connect(lambda _text: self._emit_changed())
        for widget in (self.reference_answers, self.criteria, self.accepted, self.rejected):
            widget.textChanged.connect(lambda: self.changed.emit())
        self.max_score.valueChanged.connect(lambda _value: self.changed.emit())
        for widget in (self.require_unit, self.exact_match, self.forbid_typos):
            widget.toggled.connect(lambda _checked: self.changed.emit())

    def _emit_changed(self) -> None:
        self._refresh_title()
        self.changed.emit()

    def _refresh_title(self) -> None:
        self.setTitle(f"第 {self.part.text().strip() or '？'} 空")

    def to_model(self) -> RubricItem:
        return RubricItem(
            part=self.part.text().strip(),
            max_score=Decimal(str(self.max_score.value())),
            reference_answers=split_lines(self.reference_answers.toPlainText()),
            criteria=self.criteria.toPlainText().strip(),
            accepted_expressions=split_lines(self.accepted.toPlainText()),
            rejected_expressions=split_lines(self.rejected.toPlainText()),
            require_unit=self.require_unit.isChecked(),
            exact_match=self.exact_match.isChecked(),
            forbid_typos=self.forbid_typos.isChecked(),
            notes=self.notes.text().strip(),
        )


class TaskEditorDialog(QDialog):
    task_saved = Signal(object, object)

    def __init__(
        self,
        task_path: Path,
        task: Task | None = None,
        parent: QWidget | None = None,
        *,
        default_model: str = "deepseek-flash",
    ) -> None:
        super().__init__(parent)
        self.task_path = task_path.resolve()
        self.original_task = task
        self.dirty = False
        self.item_editors: list[RubricItemEditor] = []
        self.setWindowTitle("编辑阅卷任务" if task else "新建阅卷任务")
        self.resize(920, 820)
        root = QVBoxLayout(self)

        general = QGroupBox("任务信息")
        general_form = QFormLayout(general)
        self.task_id = QLineEdit(task.task_id if task else str(uuid.uuid4()))
        self.name = QLineEdit(task.name if task else "")
        self.question_number = QLineEdit(task.question_number if task else "")
        self.max_score = self._score_box(float(task.max_score) if task else 1)
        self.score_step = self._score_box(float(task.score_step) if task else 1)
        self.provider = QComboBox()
        self.provider.addItem("DeepSeek", "deepseek")
        self.model = QLineEdit(task.model if task else default_model)
        self.rule_version = QSpinBox()
        self.rule_version.setRange(1, 9999)
        self.rule_version.setValue(task.rule_version if task else 1)
        general_form.addRow("任务 ID*", self.task_id)
        general_form.addRow("考试/任务名称*", self.name)
        general_form.addRow("题号*", self.question_number)
        general_form.addRow("整题满分*", self.max_score)
        general_form.addRow("分数步长*", self.score_step)
        general_form.addRow("AI 服务", self.provider)
        general_form.addRow("模型*", self.model)
        general_form.addRow("评分规则版本", self.rule_version)
        root.addWidget(general)

        automation = QGroupBox("自动化设置")
        automation_form = QFormLayout(automation)
        self.observation_delay = QDoubleSpinBox()
        self.observation_delay.setRange(0, 5)
        self.observation_delay.setSingleStep(0.5)
        self.observation_delay.setValue(task.observation_delay if task else 1.0)
        self.max_continuous = QSpinBox()
        self.max_continuous.setRange(1, 10000)
        self.max_continuous.setValue(task.max_continuous if task and task.max_continuous else 100)
        self.unlimited = QCheckBox("无限制")
        self.unlimited.setChecked(bool(task and task.max_continuous is None))
        self.max_continuous.setEnabled(not self.unlimited.isChecked())
        maximum_row = QHBoxLayout()
        maximum_row.addWidget(self.max_continuous)
        maximum_row.addWidget(self.unlimited)
        self.pause_hotkey = QLineEdit(task.pause_hotkey if task else "f8")
        self.resume_hotkey = QLineEdit(task.resume_hotkey if task else "f9")
        self.stop_hotkey = QLineEdit(task.stop_hotkey if task else "ctrl+alt+q")
        automation_form.addRow("提交前观察秒数", self.observation_delay)
        automation_form.addRow("最大连续阅卷", maximum_row)
        automation_form.addRow("暂停快捷键", self.pause_hotkey)
        automation_form.addRow("继续快捷键", self.resume_hotkey)
        automation_form.addRow("紧急停止快捷键", self.stop_hotkey)
        root.addWidget(automation)

        question_group = QGroupBox("题目")
        question_layout = QVBoxLayout(question_group)
        self.question_text = QTextEdit(task.question.text if task else "")
        self.question_text.setPlaceholderText("输入完整题目文字；题目文字和题图至少需要一个")
        self.question_text.setMaximumHeight(110)
        image_row = QHBoxLayout()
        self.question_image_path: Path | None = task.question.image_path if task else None
        self.image_label = QLabel()
        self.image_label.setWordWrap(True)
        choose_image = QPushButton("选择题图")
        clear_image = QPushButton("移除题图")
        choose_image.clicked.connect(self.choose_question_image)
        clear_image.clicked.connect(self.clear_question_image)
        image_row.addWidget(self.image_label, 1)
        image_row.addWidget(choose_image)
        image_row.addWidget(clear_image)
        self.image_preview = QLabel()
        self.image_preview.setMaximumHeight(150)
        question_layout.addWidget(self.question_text)
        question_layout.addLayout(image_row)
        question_layout.addWidget(self.image_preview)
        self._refresh_image()
        root.addWidget(question_group)

        rubric_header = QHBoxLayout()
        rubric_header.addWidget(QLabel("逐空评分标准"))
        rubric_header.addStretch()
        total_button = QPushButton("按各空合计更新满分")
        add_button = QPushButton("添加一空")
        total_button.clicked.connect(self.update_total)
        add_button.clicked.connect(lambda: self.add_item())
        rubric_header.addWidget(total_button)
        rubric_header.addWidget(add_button)
        root.addLayout(rubric_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        rubric_widget = QWidget()
        self.items_layout = QVBoxLayout(rubric_widget)
        self.items_layout.addStretch()
        scroll.setWidget(rubric_widget)
        root.addWidget(scroll, 1)
        for item in (task.rubric.items if task else (None,)):
            self.add_item(item, schedule=False)

        supplemental_group = QGroupBox("全题补充评分规则")
        supplemental_layout = QVBoxLayout(supplemental_group)
        self.supplemental = QTextEdit(task.rubric.supplemental_rules if task else "")
        self.supplemental.setMaximumHeight(90)
        supplemental_layout.addWidget(self.supplemental)
        root.addWidget(supplemental_group)

        footer = QHBoxLayout()
        self.save_status = QLabel("等待编辑")
        self.save_status.setWordWrap(True)
        save_button = QPushButton("立即保存")
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        save_button.clicked.connect(self.save_now)
        close_buttons.rejected.connect(self.close)
        footer.addWidget(self.save_status, 1)
        footer.addWidget(save_button)
        footer.addWidget(close_buttons)
        root.addLayout(footer)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(600)
        self.timer.timeout.connect(self.save_now)
        self._connect_general_changes()

    @staticmethod
    def _score_box(value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(0.01, 1000)
        box.setDecimals(2)
        box.setSingleStep(0.5)
        box.setValue(value)
        return box

    def _connect_general_changes(self) -> None:
        for widget in (self.task_id, self.name, self.question_number, self.model):
            widget.textChanged.connect(lambda _text: self.schedule_save())
        for widget in (self.max_score, self.score_step):
            widget.valueChanged.connect(lambda _value: self.schedule_save())
        for widget in (self.observation_delay, self.max_continuous):
            widget.valueChanged.connect(lambda _value: self.schedule_save())
        self.unlimited.toggled.connect(self._toggle_unlimited)
        for widget in (self.pause_hotkey, self.resume_hotkey, self.stop_hotkey):
            widget.textChanged.connect(lambda _text: self.schedule_save())
        self.rule_version.valueChanged.connect(lambda _value: self.schedule_save())
        self.question_text.textChanged.connect(lambda: self.schedule_save())
        self.supplemental.textChanged.connect(lambda: self.schedule_save())

    def add_item(self, item: RubricItem | None = None, *, schedule: bool = True) -> None:
        editor = RubricItemEditor(item, default_part=str(len(self.item_editors) + 1))
        editor.changed.connect(self.schedule_save)
        editor.remove_requested.connect(self.remove_item)
        self.item_editors.append(editor)
        self.items_layout.insertWidget(self.items_layout.count() - 1, editor)
        if schedule:
            self.schedule_save()

    def remove_item(self, editor: RubricItemEditor) -> None:
        if len(self.item_editors) == 1:
            QMessageBox.warning(self, "不能删除", "任务至少需要一个评分项。")
            return
        self.item_editors.remove(editor)
        editor.deleteLater()
        self.schedule_save()

    def choose_question_image(self) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "选择题目图片", filter="Images (*.png *.jpg *.jpeg *.webp *.gif)")
        if value:
            self.question_image_path = Path(value).resolve()
            self._refresh_image()
            self.schedule_save()

    def clear_question_image(self) -> None:
        self.question_image_path = None
        self._refresh_image()
        self.schedule_save()

    def _refresh_image(self) -> None:
        if self.question_image_path is None:
            self.image_label.setText("未选择题图")
            self.image_preview.clear()
            return
        self.image_label.setText(str(self.question_image_path))
        pixmap = QPixmap(str(self.question_image_path))
        if pixmap.isNull():
            self.image_preview.setText("题图无法预览")
        else:
            self.image_preview.setPixmap(pixmap.scaledToHeight(140))

    def update_total(self) -> None:
        total = sum(editor.max_score.value() for editor in self.item_editors)
        self.max_score.setValue(total)
        self.schedule_save()

    def build_task(self) -> Task:
        task = Task(
            task_id=self.task_id.text().strip(),
            name=self.name.text().strip(),
            question_number=self.question_number.text().strip(),
            max_score=Decimal(str(self.max_score.value())),
            score_step=Decimal(str(self.score_step.value())),
            provider=str(self.provider.currentData()),
            model=self.model.text().strip(),
            rule_version=self.rule_version.value(),
            question=Question(self.question_text.toPlainText().strip(), self.question_image_path),
            rubric=Rubric(tuple(editor.to_model() for editor in self.item_editors), self.supplemental.toPlainText().strip()),
            observation_delay=self.observation_delay.value(),
            max_continuous=None if self.unlimited.isChecked() else self.max_continuous.value(),
            pause_hotkey=self.pause_hotkey.text().strip().lower(),
            resume_hotkey=self.resume_hotkey.text().strip().lower(),
            stop_hotkey=self.stop_hotkey.text().strip().lower(),
        )
        versioned = ensure_rule_version(self.original_task, task)
        if versioned.rule_version != task.rule_version:
            task = versioned
            self.rule_version.blockSignals(True)
            self.rule_version.setValue(task.rule_version)
            self.rule_version.blockSignals(False)
        return task

    def _toggle_unlimited(self, checked: bool) -> None:
        self.max_continuous.setEnabled(not checked)
        self.schedule_save()

    def schedule_save(self) -> None:
        self.dirty = True
        self.save_status.setText("有未保存修改……")
        self.save_status.setStyleSheet("color: #475467;")
        self.timer.start()

    def save_now(self) -> bool:
        self.timer.stop()
        try:
            task = self.build_task()
            if task.question.image_path is not None:
                stored_image = store_question_image(task.question.image_path, self.task_path)
                if stored_image != task.question.image_path:
                    task = replace(task, question=Question(task.question.text, stored_image))
                    self.question_image_path = stored_image
                    self._refresh_image()
            save_task(task, self.task_path)
        except Exception as exc:
            self.save_status.setText(f"尚未保存：{exc}")
            self.save_status.setStyleSheet("color: #b42318;")
            return False
        self.dirty = False
        self.save_status.setText(f"已自动保存：{self.task_path}")
        self.save_status.setStyleSheet("color: #027a48;")
        self.task_saved.emit(self.task_path, task)
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.dirty or self.save_now():
            event.accept()
            return
        answer = QMessageBox.question(self, "配置尚未有效", "当前配置不能保存，确定关闭并放弃这些内容吗？")
        if answer == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()
