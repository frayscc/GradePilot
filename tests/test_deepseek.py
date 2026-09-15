import asyncio
import json
from pathlib import Path

import httpx

from app.ai.deepseek import DeepSeekConfig, DeepSeekProvider
from app.ai.schemas import GradeRequest

from .helpers import make_task, valid_result


def test_deepseek_uses_task_model_and_answer_image(tmp_path: Path) -> None:
    image = tmp_path / "answer.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer test-key"
        assert body["model"] == "deepseek-flash"
        assert body["response_format"] == {"type": "json_object"}
        user_content = body["messages"][1]["content"]
        assert user_content[-1]["type"] == "image_url"
        assert user_content[-1]["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(valid_result(), ensure_ascii=False)}}]},
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = DeepSeekProvider(DeepSeekConfig("test-key"), client)
            result = await provider.grade(GradeRequest(make_task(), image))
            assert result.total_score == 2

    asyncio.run(run())
