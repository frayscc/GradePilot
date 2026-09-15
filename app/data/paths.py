import os
import sys
from pathlib import Path


def user_data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "AIGrader"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AIGrader"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "AIGrader"
