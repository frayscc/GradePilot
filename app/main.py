from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.ai.deepseek import DeepSeekConfig, DeepSeekProvider
from app.core.grading_engine import GradingEngine, list_images
from app.core.task_manager import load_task


def provider_from_env() -> DeepSeekProvider:
    return DeepSeekProvider(
        DeepSeekConfig(
            os.environ.get("DEEPSEEK_API_KEY", ""),
            os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="AIGrader Phase 2")
    sub = root.add_subparsers(dest="command", required=True)
    ui = sub.add_parser("ui", help="启动 AI 评分结果界面")
    ui.add_argument("--task", type=Path)
    dry = sub.add_parser("dry-run", help="单张图片 Dry Run")
    dry.add_argument("--task", required=True, type=Path)
    dry.add_argument("--image", required=True, type=Path)
    dry.add_argument("--output", type=Path)
    batch = sub.add_parser("batch", help="批量串行 Dry Run")
    batch.add_argument("--task", required=True, type=Path)
    batch.add_argument("--images", required=True, type=Path)
    batch.add_argument("--output", required=True, type=Path)
    batch.add_argument("--min-images", type=int, default=20)
    return root


async def run_dry(task_path: Path, image: Path, output: Path | None) -> int:
    record = await GradingEngine(provider_from_env()).dry_run(load_task(task_path), image)
    text = json.dumps(record.as_dict(), ensure_ascii=False, indent=2)
    print(text)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    return 1 if record.error else (2 if record.result and record.result.need_review else 0)


async def run_batch(task_path: Path, image_dir: Path, output: Path, minimum: int) -> int:
    images = list_images(image_dir)
    if len(images) < minimum:
        raise SystemExit(f"验收图片不足：找到 {len(images)} 张，至少需要 {minimum} 张")
    records = await GradingEngine(provider_from_env()).batch_dry_run(load_task(task_path), images)
    report = {
        "task": str(task_path),
        "count": len(records),
        "success": sum(record.error is None for record in records),
        "need_review": sum(bool(record.result and record.result.need_review) for record in records),
        "failed": sum(record.error is not None for record in records),
        "records": [record.as_dict() for record in records],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("count", "success", "need_review", "failed")}, ensure_ascii=False))
    return 1 if report["failed"] else 0


def main() -> int:
    load_dotenv()
    args = parser().parse_args()
    if args.command == "ui":
        from PySide6.QtWidgets import QApplication
        from app.ui.main_window import MainWindow

        application = QApplication(sys.argv)
        window = MainWindow(args.task)
        window.show()
        return application.exec()
    if args.command == "dry-run":
        return asyncio.run(run_dry(args.task, args.image, args.output))
    if args.command == "batch":
        return asyncio.run(run_batch(args.task, args.images, args.output, args.min_images))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
