from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from .automation import (
    AutomationContext,
    PauseController,
    Point,
    SafeWebAutomation,
    enable_windows_dpi_awareness,
    install_windows_hotkeys,
)
from .capture import Region, capture_region
from .deepseek import DeepSeekConfig, DeepSeekProvider
from .models import GradeRequest, GradeResult, parse_grade_result
from .zhixue import ZhixueCoordinates, ZhixuePlatform


def _add_grade_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--question", required=True)
    parser.add_argument("--rubric", required=True)
    parser.add_argument("--max-score", required=True, type=Decimal)
    parser.add_argument("--score-step", default=Decimal("1"), type=Decimal)
    parser.add_argument("--output", type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIGrader Phase 0 verification CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture", help="capture one fixed screen region")
    for name in ("left", "top", "width", "height"):
        capture.add_argument(f"--{name}", required=True, type=int)
    capture.add_argument("--output", required=True, type=Path)

    grade = sub.add_parser("grade", help="dry run: call AI and print validated JSON; never operates mouse")
    _add_grade_args(grade)

    dpi = sub.add_parser("dpi", help="print DPI and screen diagnostics")

    automate = sub.add_parser("automate", help="explicitly armed score entry/submit verification")
    automate.add_argument("--result", required=True, type=Path, help="previously validated grade JSON")
    automate.add_argument("--max-score", required=True, type=Decimal)
    automate.add_argument("--score-step", default=Decimal("1"), type=Decimal)
    automate.add_argument("--score-x", required=True, type=int)
    automate.add_argument("--score-y", required=True, type=int)
    automate.add_argument("--submit-x", required=True, type=int)
    automate.add_argument("--submit-y", required=True, type=int)
    automate.add_argument("--arm", action="store_true", help="required before any mouse action")
    automate.add_argument("--submit", action="store_true", help="also click submit; omitted means input only")
    return parser


async def _grade(args: argparse.Namespace) -> int:
    request = GradeRequest(args.image, args.question, args.rubric, args.max_score, args.score_step)
    provider = DeepSeekProvider(
        DeepSeekConfig(
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        )
    )
    result = await provider.grade(request)
    rendered = json.dumps(result.as_dict(), ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 2 if result.need_review else 0


def _diagnostics() -> int:
    mode = enable_windows_dpi_awareness()
    print(json.dumps({"platform": sys.platform, "dpi_awareness": mode}, ensure_ascii=False))
    if sys.platform == "win32":
        import pyautogui

        print(json.dumps({"screen_size": list(pyautogui.size()), "position": list(pyautogui.position())}))
    return 0


def _automate(args: argparse.Namespace) -> int:
    if not args.arm:
        raise SystemExit("BLOCKED: --arm is required; no mouse action performed")
    payload = json.loads(args.result.read_text(encoding="utf-8"))
    result: GradeResult = parse_grade_result(payload, expected_max=args.max_score, score_step=args.score_step)
    pause = PauseController()
    automation = SafeWebAutomation(pause)
    platform = ZhixuePlatform(
        ZhixueCoordinates(Point(args.score_x, args.score_y), Point(args.submit_x, args.submit_y)), automation
    )
    context = AutomationContext(enabled=True, ai_success=True, score_valid=True)
    enable_windows_dpi_awareness()
    remove_hotkeys = install_windows_hotkeys(pause)
    try:
        platform.enter_score(result, context)
        if args.submit:
            answer = input("将真实点击提交按钮。输入 SUBMIT 继续（F8 暂停）：")
            if answer != "SUBMIT":
                pause.stop()
                raise SystemExit("提交已取消")
            platform.submit(result, context)
    finally:
        remove_hotkeys()
    return 0


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    if args.command == "capture":
        output = capture_region(Region(args.left, args.top, args.width, args.height), args.output)
        print(output.resolve())
        return 0
    if args.command == "grade":
        return asyncio.run(_grade(args))
    if args.command == "dpi":
        return _diagnostics()
    if args.command == "automate":
        return _automate(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
