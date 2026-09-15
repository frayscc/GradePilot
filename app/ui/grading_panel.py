from PySide6.QtWidgets import QGroupBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from app.ai.schemas import GradeResult


class GradingPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("AI 评分结果")
        layout = QVBoxLayout(self)
        self.status = QLabel("请选择任务和学生答案图片")
        self.status.setWordWrap(True)
        self.answers = QTableWidget(0, 2)
        self.answers.setHorizontalHeaderLabels(["评分项", "识别答案"])
        self.grades = QTableWidget(0, 4)
        self.grades.setHorizontalHeaderLabels(["评分项", "得分", "满分", "判分理由"])
        self.total = QLabel("总分：—")
        self.total.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        for widget in (self.status, self.answers, self.grades, self.total, self.summary):
            layout.addWidget(widget)

    def show_busy(self) -> None:
        self.status.setText("正在识别和评分……Dry Run 不会操作网页。")

    def show_error(self, message: str) -> None:
        self.status.setText(f"失败：{message}\n未执行任何网页操作。")
        self.status.setStyleSheet("color: #b42318; font-weight: 700;")

    def show_result(self, result: GradeResult) -> None:
        self.status.setStyleSheet("")
        if result.need_review:
            self.status.setText(f"需要人工复核：{result.review_reason}")
            self.status.setStyleSheet("color: #b54708; font-weight: 700;")
        else:
            self.status.setText("结构与分数验证通过（Dry Run，未提交）")
        self.answers.setRowCount(len(result.recognized_answers))
        for row, answer in enumerate(result.recognized_answers):
            self.answers.setItem(row, 0, QTableWidgetItem(answer.part))
            self.answers.setItem(row, 1, QTableWidgetItem(answer.text))
        self.grades.setRowCount(len(result.grading))
        for row, grade in enumerate(result.grading):
            values = (grade.part, format(grade.score, "f"), format(grade.max_score, "f"), grade.reason)
            for column, value in enumerate(values):
                self.grades.setItem(row, column, QTableWidgetItem(value))
        self.total.setText(f"总分：{result.total_score} / {result.max_score}")
        self.summary.setText(f"判分摘要：{result.summary}")
