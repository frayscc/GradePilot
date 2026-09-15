from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass

import httpx

from .models import GradeRequest, GradeResult, ValidationError, parse_grade_result
from .prompt import SYSTEM_PROMPT, build_prompt
from .provider import AIProvider


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    timeout_seconds: float = 90.0

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("DEEPSEEK_API_KEY is required")


class DeepSeekProvider(AIProvider):
    def __init__(self, config: DeepSeekConfig, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._client = client

    async def grade(self, request: GradeRequest) -> GradeResult:
        mime = mimetypes.guess_type(request.image_path.name)[0] or "image/png"
        if mime not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
            raise ValidationError(f"unsupported image type: {mime}")
        encoded = base64.b64encode(request.image_path.read_bytes()).decode("ascii")
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_prompt(request)},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "original"}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.config.timeout_seconds)
        try:
            response = await client.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json=body,
            )
            response.raise_for_status()
            envelope = response.json()
            content = envelope["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValidationError("DeepSeek returned non-text message content")
            try:
                payload = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ValidationError("DeepSeek content is not valid JSON") from exc
            return parse_grade_result(payload, expected_max=request.max_score, score_step=request.score_step)
        except (KeyError, IndexError, TypeError) as exc:
            raise ValidationError("DeepSeek response envelope is invalid") from exc
        finally:
            if owns_client:
                await client.aclose()
