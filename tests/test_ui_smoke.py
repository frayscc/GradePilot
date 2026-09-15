import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.task_editor import TaskEditorDialog


def test_main_window_and_settings_dialog_construct(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert "V1.0" in window.windowTitle()
    dialog = SettingsDialog(window)
    assert dialog.model.text()
    dialog.close()
    editor = TaskEditorDialog(tmp_path / "task.json", parent=window)
    assert editor.max_continuous.value() == 100
    assert editor.pause_hotkey.text() == "f8"
    editor.close()
    window.close()
    application.processEvents()
