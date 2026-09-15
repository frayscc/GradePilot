from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.core.calibration_store import save_calibration
from app.data.calibration import CalibrationProfile, Point, Region


class CalibrationDialog(QDialog):
    profile_saved = Signal(object, object)

    STEPS = (
        "学生答案区域左上角",
        "学生答案区域右下角",
        "分数输入框中心",
        "“提交分数”按钮中心",
        "阅卷进度数字中心（例如 22/1046）",
    )

    def __init__(
        self,
        profile_path: Path,
        profile: CalibrationProfile | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.profile_path = profile_path.resolve()
        self.points: list[Point] = []
        if profile:
            self.points = [
                Point(profile.answer_region.x, profile.answer_region.y),
                Point(profile.answer_region.x + profile.answer_region.width, profile.answer_region.y + profile.answer_region.height),
                profile.score_input,
                profile.submit_button,
            ]
            if profile.page_marker is not None:
                self.points.append(profile.page_marker)
        self.current_step = min(len(self.points), len(self.STEPS) - 1)
        self.countdown = 0
        self.setWindowTitle("坐标标定")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(560, 360)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "保持浏览器窗口、分辨率和 Windows 缩放不变。每一步点击“开始捕获”后，"
            "在倒计时结束前把鼠标移动到目标位置。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.instruction = QLabel()
        self.instruction.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(self.instruction)
        self.capture_button = QPushButton("开始捕获（3 秒）")
        self.capture_button.clicked.connect(self.start_capture)
        layout.addWidget(self.capture_button)
        self.rows = QGridLayout()
        self.value_labels: list[QLabel] = []
        for index, name in enumerate(self.STEPS):
            self.rows.addWidget(QLabel(f"{index + 1}. {name}"), index, 0)
            value = QLabel("未标定")
            self.value_labels.append(value)
            self.rows.addWidget(value, index, 1)
        layout.addLayout(self.rows)
        reset = QPushButton("重新标定")
        reset.clicked.connect(self.reset)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(reset)
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self._refresh()

    def _refresh(self) -> None:
        for index, label in enumerate(self.value_labels):
            label.setText(f"({self.points[index].x}, {self.points[index].y})" if index < len(self.points) else "未标定")
        if len(self.points) == len(self.STEPS):
            self.instruction.setText("五项标定已完成，可以保存。")
            self.capture_button.setEnabled(False)
        else:
            self.current_step = len(self.points)
            self.instruction.setText(f"第 {self.current_step + 1} 步：定位 {self.STEPS[self.current_step]}")
            self.capture_button.setEnabled(True)

    def start_capture(self) -> None:
        self.countdown = 3
        self.capture_button.setEnabled(False)
        self.capture_button.setText(f"{self.countdown} 秒后捕获鼠标位置")
        self.timer.start()

    def tick(self) -> None:
        self.countdown -= 1
        if self.countdown > 0:
            self.capture_button.setText(f"{self.countdown} 秒后捕获鼠标位置")
            return
        self.timer.stop()
        try:
            import pyautogui

            position = pyautogui.position()
            self.points.append(Point(int(position.x), int(position.y)))
        except Exception as exc:
            QMessageBox.critical(self, "捕获失败", str(exc))
        self.capture_button.setText("开始捕获（3 秒）")
        self._refresh()

    def reset(self) -> None:
        self.timer.stop()
        self.points.clear()
        self.capture_button.setText("开始捕获（3 秒）")
        self._refresh()

    def build_profile(self) -> CalibrationProfile:
        if len(self.points) != len(self.STEPS):
            raise ValueError("请完成全部五项标定")
        return CalibrationProfile(
            answer_region=Region.from_corners(self.points[0], self.points[1]),
            score_input=self.points[2],
            submit_button=self.points[3],
            page_marker=self.points[4],
        )

    def save(self) -> None:
        try:
            profile = self.build_profile()
            save_calibration(profile, self.profile_path)
        except Exception as exc:
            QMessageBox.critical(self, "无法保存标定", str(exc))
            return
        self.profile_saved.emit(self.profile_path, profile)
        self.accept()
