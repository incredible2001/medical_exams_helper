#!/usr/bin/env python3
"""医考帮备考助手 — 入口。

用法：
    pip install -r requirements.txt
    # 在 .env 里填好 DEEPSEEK_API_KEY（参考 .env.example）
    python main.py
"""
import sys


def main():
    try:
        from app import main as app_main
    except ImportError as e:
        print(f"依赖缺失：{e}")
        print("请先执行：pip install -r requirements.txt")
        sys.exit(1)
    app_main()


if __name__ == "__main__":
    main()
