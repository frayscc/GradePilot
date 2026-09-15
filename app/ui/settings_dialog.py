from __future__ import annotations

import asyncio

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
)

from app.ai.deepseek import DeepSeekConfig, DeepSeekProvider
from app.core.settings import ApplicationSettings, CredentialStore, SettingsStore


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 服务设置")
        self.store = SettingsStore()
        self.credentials = CredentialStore()
        settings = self.store.load()
        form = QFormLayout(self)
        form.addRow("AI 服务", QLabel("DeepSeek"))
        self.api_key = QLineEdit(self.credentials.get_api_key())
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("输入后保存到 Windows Credential Manager")
        self.model = QLineEdit(settings.default_model)
        self.base_url = QLineEdit(settings.deepseek_base_url)
        self.status = QLabel(
            "Windows 中密钥保存到 Credential Manager。"
            if self.credentials.persistent else "当前平台仅在本进程中保留密钥；开发环境可使用 .env。"
        )
        self.status.setWordWrap(True)
        test_button = QPushButton("测试连接")
        test_button.clicked.connect(self.test_connection)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow("API Key", self.api_key)
        form.addRow("默认模型", self.model)
        form.addRow("Base URL", self.base_url)
        form.addRow(test_button)
        form.addRow(self.status)
        form.addRow(buttons)

    def values(self) -> tuple[ApplicationSettings, str]:
        settings = ApplicationSettings(
            self.model.text().strip(), self.base_url.text().strip().rstrip("/")
        )
        return settings, self.api_key.text().strip()

    def test_connection(self) -> None:
        try:
            settings, key = self.values()
            message = asyncio.run(
                DeepSeekProvider(DeepSeekConfig(key, settings.deepseek_base_url)).test_connection(
                    settings.default_model
                )
            )
            self.status.setText(message)
            self.status.setStyleSheet("color: #027a48;")
        except Exception as exc:
            self.status.setText(str(exc))
            self.status.setStyleSheet("color: #b42318;")

    def save(self) -> None:
        try:
            settings, key = self.values()
            self.credentials.set_api_key(key)
            self.store.save(settings)
        except Exception as exc:
            QMessageBox.critical(self, "设置保存失败", str(exc))
            return
        self.accept()
