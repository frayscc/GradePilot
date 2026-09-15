from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path

import httpx

from .base import AIProvider, ProviderError
from .prompts import SYSTEM_PROMPT, build_grading_prompt
from .schemas import GradeRequest, GradeResult, ResultValidationError, validate_grade_result


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    timeout_seconds: float = 90.0

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ProviderError("未配置 DEEPSEEK_API_KEY")


def image_block(path: Path) -> dict:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    if mime not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
        raise ResultValidationError(f"不支持的图片格式：{mime}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "original"}}


class DeepSeekProvider(AIProvider):
    def __init__(self, config: DeepSeekConfig, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self.client = client

    async def grade(self, request: GradeRequest) -> GradeResult:
        content: list[dict] = [{"type": "text", "text": build_grading_prompt(request.task)}]
        if request.task.question.image_path is not None:
            content.append(image_block(request.task.question.image_path))
        content.append(image_block(request.answer_image))
        body = {
            "model": request.task.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.config.timeout_seconds)
        try:
            response = await client.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json=body,
            )
            response.raise_for_status()
            envelope = response.json()
            content_text = envelope["choices"][0]["message"]["content"]
            if not isinstance(content_text, str):
                raise ProviderError("DeepSeek 返回内容不是字符串")
            return validate_grade_result(json.loads(content_text), request.task)
        except ResultValidationError:
            raise
        except json.JSONDecodeError as exc:
            raise ResultValidationError("DeepSeek 未返回有效 JSON") from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"DeepSeek 请求或响应失败：{exc}") from exc
        finally:
            if owns_client:
                await client.aclose()
