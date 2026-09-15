import asyncio
import sys
from types import SimpleNamespace

import httpx

from app.ai.deepseek import DeepSeekConfig, DeepSeekProvider
from app.core.settings import ApplicationSettings, CredentialStore, SettingsStore


def test_application_settings_are_atomic_and_never_contain_api_key(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    settings = ApplicationSettings("deepseek-test", "https://example.test")
    store.save(settings)
    assert store.load() == settings
    assert "api" not in path.read_text(encoding="utf-8").lower()


def test_windows_credential_manager_is_used(monkeypatch) -> None:
    written = {}

    def write(payload, flags):
        written.update(payload)

    fake = SimpleNamespace(
        CRED_TYPE_GENERIC=1,
        CRED_PERSIST_LOCAL_MACHINE=2,
        CredWrite=write,
        CredRead=lambda target, kind: {"CredentialBlob": "stored-secret"},
    )
    monkeypatch.setattr("app.core.settings.sys.platform", "win32")
    monkeypatch.setitem(sys.modules, "win32cred", fake)
    credentials = CredentialStore()
    credentials.set_api_key("new-secret")
    assert written["TargetName"] == CredentialStore.SERVICE
    assert written["CredentialBlob"] == "new-secret"
    assert credentials.get_api_key() == "stored-secret"


def test_non_windows_credentials_use_process_environment(monkeypatch) -> None:
    monkeypatch.setattr("app.core.settings.sys.platform", "darwin")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    credentials = CredentialStore()
    credentials.set_api_key("session-secret")
    assert credentials.get_api_key() == "session-secret"


def test_deepseek_connection_test_lists_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/models"
        return httpx.Response(200, json={"data": [{"id": "deepseek-flash"}]})

    async def run() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await DeepSeekProvider(DeepSeekConfig("key"), client).test_connection(
                "deepseek-flash"
            )

    assert "可用" in asyncio.run(run())
