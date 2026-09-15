from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.ai.base import ProviderError
from app.ai.deepseek import DeepSeekConfig
from app.data.paths import user_data_dir


@dataclass(frozen=True)
class ApplicationSettings:
    default_model: str = "deepseek-flash"
    deepseek_base_url: str = "https://api.deepseek.com"

    def __post_init__(self) -> None:
        if not self.default_model.strip():
            raise ValueError("默认模型不能为空")
        if not self.deepseek_base_url.startswith(("https://", "http://")):
            raise ValueError("DeepSeek Base URL 必须以 http:// 或 https:// 开头")


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or user_data_dir() / "settings.json").resolve()

    def load(self) -> ApplicationSettings:
        if not self.path.exists():
            return ApplicationSettings()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"default_model", "deepseek_base_url"}:
            raise ValueError("settings.json 字段无效")
        return ApplicationSettings(str(payload["default_model"]), str(payload["deepseek_base_url"]))

    def save(self, settings: ApplicationSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(
                    {
                        "default_model": settings.default_model,
                        "deepseek_base_url": settings.deepseek_base_url,
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class CredentialStore:
    SERVICE = "AIGrader.DeepSeek"
    USERNAME = "api-key"

    def get_api_key(self) -> str:
        if sys.platform == "win32":
            try:
                import win32cred

                credential = win32cred.CredRead(self.SERVICE, win32cred.CRED_TYPE_GENERIC)
                value = credential["CredentialBlob"]
                if isinstance(value, bytes):
                    value = value.decode("utf-16-le")
                value = str(value).rstrip("\x00")
                if str(value).strip():
                    return str(value).strip()
            except Exception:
                pass
        return os.environ.get("DEEPSEEK_API_KEY", "").strip()

    def set_api_key(self, api_key: str) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise ProviderError("API Key 不能为空")
        if sys.platform == "win32":
            try:
                import win32cred

                win32cred.CredWrite(
                    {
                        "Type": win32cred.CRED_TYPE_GENERIC,
                        "TargetName": self.SERVICE,
                        "UserName": self.USERNAME,
                        "CredentialBlob": api_key,
                        "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
                    },
                    0,
                )
                return
            except Exception as exc:
                raise ProviderError(f"写入 Windows Credential Manager 失败：{exc}") from exc
        os.environ["DEEPSEEK_API_KEY"] = api_key

    @property
    def persistent(self) -> bool:
        return sys.platform == "win32"


def load_deepseek_config() -> DeepSeekConfig:
    settings = SettingsStore().load()
    base_url = os.environ.get("DEEPSEEK_BASE_URL", settings.deepseek_base_url)
    return DeepSeekConfig(CredentialStore().get_api_key(), base_url)
