from pathlib import Path

import app
import app.data.paths as data_paths


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_windows_user_data_and_tasks_are_outside_program_dir(
    tmp_path: Path, monkeypatch
) -> None:
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setattr(data_paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    assert data_paths.user_data_dir() == local_app_data / "AIGrader"
    assert data_paths.user_tasks_dir() == local_app_data / "AIGrader" / "tasks"
    assert data_paths.user_tasks_dir().is_dir()


def test_portable_build_files_match_release_version() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (PROJECT_ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")
    spec = (PROJECT_ROOT / "packaging/AIGrader.spec").read_text(encoding="utf-8")
    version_info = (PROJECT_ROOT / "packaging/windows_version_info.txt").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "scripts/build_windows.ps1").read_text(encoding="utf-8")

    assert 'version = "1.0.0"' in pyproject
    assert app.__version__ == "1.0.0"
    assert "windows-latest" in workflow and 'python-version: "3.12"' in workflow
    assert "pytest" in workflow and "PyInstaller" in spec
    assert 'name="AIGrader-Windows-x64"' in spec
    assert "1.0.0" in version_info
    assert "Compress-Archive" in script
    assert "AIGrader-v$Version-Windows-x64.zip" in script
    compile(spec, "AIGrader.spec", "exec")
