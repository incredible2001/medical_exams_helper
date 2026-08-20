# -*- coding: utf-8 -*-
"""全量补跑：把指定数据库里所有错题重新交给 AI 整理（补学科细分类 + 强制 ** 划重点），
再重新生成速通手册。

用法：
    python scripts/reprocess.py [数据库路径] [手册目录]
默认数据库 data20260820/medical_notes.db，手册目录 data20260820/速通手册。

会调用 DeepSeek（分批，每批 25 题），请确保 .env 里已配置 DEEPSEEK_API_KEY。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# Windows 中文输出 + 行缓冲（重定向到文件/日志也能实时看到进度）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:  # noqa: BLE001
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                                  line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from core.config import PROJECT_ROOT, load_config
from core.db import DB
from core.deepseek_client import DeepSeekClient
from core.aggregate_service import AggregateService


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data20260820/medical_notes.db")
    hb_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data20260820/速通手册")

    cfg = load_config()
    cfg["data"]["handbook_dir"] = str((PROJECT_ROOT / hb_dir).resolve())

    db = DB(str((PROJECT_ROOT / db_path).resolve()))
    total = db.count_questions()
    print(f"数据库：{db_path}（共 {total} 题）")

    try:
        client = DeepSeekClient(
            model=cfg.get("deepseek", {}).get("model", "deepseek-v4-flash"),
            base_url=cfg.get("deepseek", {}).get("base_url", "https://api.deepseek.com"),
        )
    except Exception as e:  # noqa: BLE001
        print(f"✗ 初始化 AI 失败：{e}")
        return 1

    svc = AggregateService(db, client, cfg)

    marked = db.mark_all_unprocessed()
    print(f"已标记 {marked} 题待重新整理。")

    # 循环补跑：单批失败（AI 报错）会被跳过，重跑直到全部完成
    retries = 0
    while db.unprocessed_count() > 0:
        if retries >= 3:
            print("⚠ 仍有未完成题目（连续失败），请稍后重跑本脚本。"
                  f"剩余：{db.unprocessed_count()} 题")
            return 2
        for kind, payload in svc.aggregate():
            if kind == "status":
                print(f"[进度] {payload}")
            elif kind == "error":
                print(f"[错误] {payload}")
            elif kind == "done":
                print(f"[完成] {payload}")
        retries += 1
        remain = db.unprocessed_count()
        if remain:
            print(f"  ↪ 还有 {remain} 题未完成，第 {retries} 次重试…")

    print("✅ 全部完成：数据已补齐，手册已生成到", cfg["data"]["handbook_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
