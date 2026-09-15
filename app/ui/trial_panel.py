from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from app.ai.schemas import GradeResult
from app.data.trial_models import ErrorCategory, TrialMetrics, TrialRecord


CATEGORY_LABELS = {
    ErrorCategory.RECOGNITION: "字迹识别错误",
    ErrorCategory.RUBRIC: "评分标准理解错误",
    ErrorCategory.PHYSICS_REASONING: "物理语义判断错误",
    ErrorCategory.OTHER: "其他",
}


class ErrorReviewDialog(QDialog):
    def __init__(self, result: GradeResult, score_step: Decimal, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("标记 AI 错判")
        form = QFormLayout(self)
        self.correct_score = QDoubleSpinBox()
        self.correct_score.setRange(0, float(result.max_score))
        decimals = max(0, -score_step.normalize().as_tuple().exponent)
        self.correct_score.setDecimals(decimals)
        self.correct_score.setSingleStep(float(score_step))
        self.correct_score.setValue(float(result.total_score))
        self.category = QComboBox()
        for value, label in CATEGORY_LABELS.items():
            self.category.addItem(label, value)
        self.note = QTextEdit()
        self.note.setPlaceholderText("可选备注")
        self.note.setMaximumHeight(100)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow("AI 分数", QLabel(format(result.total_score, "f")))
        form.addRow("正确分数", self.correct_score)
        form.addRow("错判类型", self.category)
        form.addRow("备注", self.note)
        form.addRow(buttons)


class TrialPanel(QGroupBox):
    review_started = Signal()
    review_cancelled = Signal()
    mark_correct_requested = Signal(str, object)
    mark_error_requested = Signal(str, object, object, str)
    new_session_requested = Signal()
    export_requested = Signal()

    def __init__(self) -> None:
        super().__init__("试改模式")
        layout = QVBoxLayout(self)
        settings = QHBoxLayout()
        self.target = QSpinBox()
        self.target.setRange(1, 1000)
        self.target.setValue(100)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0, 100)
        self.threshold.setSuffix(" %")
        self.threshold.setValue(5)
        settings.addWidget(QLabel("目标份数"))
        settings.addWidget(self.target)
        settings.addWidget(QLabel("参考错判率阈值"))
        settings.addWidget(self.threshold)
        layout.addLayout(settings)
        self.metrics = QLabel("尚未开始试改")
        self.metrics.setWordWrap(True)
        layout.addWidget(self.metrics)
        actions = QHBoxLayout()
        self.correct_button = QPushButton("复核后 AI 正确")
        self.error_button = QPushButton("标记 AI 错判")
        self.new_button = QPushButton("新建试改会话")
        self.export_button = QPushButton("导出报告")
        self.correct_button.setEnabled(False)
        self.error_button.setEnabled(False)
        self.correct_button.clicked.connect(self.mark_correct)
        self.error_button.clicked.connect(self.mark_error)
        self.new_button.clicked.connect(lambda: self.new_session_requested.emit())
        self.export_button.clicked.connect(lambda: self.export_requested.emit())
        actions.addWidget(self.correct_button)
        actions.addWidget(self.error_button)
        actions.addWidget(self.new_button)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)
        self.record: TrialRecord | None = None
        self.result: GradeResult | None = None
        self.score_step = Decimal("1")

    def set_score_step(self, score_step: Decimal) -> None:
        self.score_step = score_step

    def set_current(self, record: TrialRecord, result: GradeResult) -> None:
        self.record = record
        self.result = result
        self.correct_button.setEnabled(record.need_review)
        self.error_button.setEnabled(True)

    def clear_current(self) -> None:
        self.record = None
        self.result = None
        self.correct_button.setEnabled(False)
        self.error_button.setEnabled(False)

    def set_running(self, running: bool) -> None:
        self.target.setEnabled(not running)
        self.threshold.setEnabled(not running)
        self.new_button.setEnabled(not running)
        self.export_button.setEnabled(not running)

    def show_metrics(self, metrics: TrialMetrics) -> None:
        reference = "已达到自动模式参考条件（仍需用户手动启用）" if metrics.meets_reference_condition else "尚未达到自动模式参考条件"
        self.metrics.setText(
            f"已处理：{metrics.processed}/{metrics.target_count}\n"
            f"AI 直接正常：{metrics.ai_direct_normal}　AI 主动复核：{metrics.ai_requested_review}\n"
            f"复核后 AI 正确：{metrics.review_ai_correct}　AI 真实错判：{metrics.ai_actual_errors}\n"
            f"漏报错判率：{metrics.unreported_misjudgments}/{metrics.automatic_decisions} "
            f"= {metrics.unreported_rate_percent:.2f}%\n{reference}"
        )

    def mark_correct(self) -> None:
        if self.record is None or self.result is None:
            return
        self.mark_correct_requested.emit(self.record.record_id, self.result.total_score)

    def mark_error(self) -> None:
        if self.record is None or self.result is None:
            return
        self.review_started.emit()
        dialog = ErrorReviewDialog(self.result, self.score_step, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.review_cancelled.emit()
            return
        self.mark_error_requested.emit(
            self.record.record_id,
            Decimal(str(dialog.correct_score.value())),
            dialog.category.currentData(),
            dialog.note.toPlainText().strip(),
        )
