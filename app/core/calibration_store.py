import json
import os
import tempfile
from pathlib import Path

from app.data.calibration import CalibrationError, CalibrationProfile


def load_calibration(path: Path) -> CalibrationProfile:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CalibrationError(f"标定文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise CalibrationError(f"标定文件不是有效 JSON：{exc}") from exc
    return CalibrationProfile.from_dict(payload)


def save_calibration(profile: CalibrationProfile, path: Path) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(profile.as_dict(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
