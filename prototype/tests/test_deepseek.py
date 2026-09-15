import asyncio
import json
from decimal import Decimal
from pathlib import Path

import httpx

from aigrader_proto.deepseek import DeepSeekConfig, DeepSeekProvider
from aigrader_proto.models import GradeRequest


def test_provider_sends_image_and_validates_result(tmp_path: Path) -> None:
    image = tmp_path / "answer.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    result = {
        "recognized_answers": [{"part": "1", "text": "A"}],
        "grading": [{"part": "1", "score": 1, "max_score": 1, "reason": "正确"}],
        "total_score": 1,
        "max_score": 1,
        "need_review": False,
        "review_reason": None,
        "summary": "满分",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-flash"
        content = body["messages"][1]["content"]
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = DeepSeekProvider(DeepSeekConfig("secret"), client)
            request = GradeRequest(image, "题目", "规则", Decimal("1"), Decimal("1"))
            parsed = await provider.grade(request)
            assert parsed.total_score == Decimal("1")

    asyncio.run(run())
