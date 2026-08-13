#!/usr/bin/env python3
"""实测：读当前模拟器屏幕 → 解析 → DeepSeek 逐选项讲解。

用法（先确保 .env 里填好 DEEPSEEK_API_KEY）：
    python scripts/test_explain.py
"""
import json
import os
import sys

# 强制 UTF-8 输出，避免 Windows 控制台中文乱码
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from core.adb import Adb  # noqa: E402
from core.deepseek_client import DeepSeekClient, build_explain_messages  # noqa: E402
from core.screen_parser import parse_dump  # noqa: E402


def main() -> int:
    print("== 1. 连接模拟器 ==")
    adb = Adb()
    serial = adb.connect()
    print(f"  已连接: {serial}")

    xml = adb.dump_ui_xml()
    print(f"  dump 大小: {len(xml)} bytes")

    print("\n== 2. 解析屏幕 ==")
    screen = parse_dump(xml)
    print(json.dumps(screen, ensure_ascii=False, indent=2))

    if not screen["is_question_screen"] or not screen["stem"]:
        print("\n⚠ 当前屏幕未识别到题目。请把医考帮停在题干区（题干+选项可见）再运行。")
        return 1

    print("\n== 3. 调用 DeepSeek (deepseek-v4-flash) ==")
    client = DeepSeekClient()
    messages = build_explain_messages(screen)
    print("  " + "-" * 56)
    try:
        for piece in client.chat_stream(messages):
            print(piece, end="", flush=True)
    finally:
        print("\n  " + "-" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
