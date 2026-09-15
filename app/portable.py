from __future__ import annotations

import sys

from dotenv import load_dotenv

from app.core.automation import enable_windows_dpi_awareness
from app.data.paths import user_data_dir


def main() -> int:
    data_dir = user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    load_dotenv(data_dir / ".env")
    enable_windows_dpi_awareness()

    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    application = QApplication(sys.argv)
    application.setApplicationName("AIGrader")
    application.setOrganizationName("AIGrader")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
