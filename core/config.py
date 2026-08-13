"""配置加载：config.toml + taxonomy.json。"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

if getattr(sys, "frozen", False):
    # 打包为 exe 时，项目根 = exe 所在目录（配置/数据都在 exe 旁边）
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else (PROJECT_ROOT / "config.toml")
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    # 把相对 data 目录解析为绝对路径，方便到处使用
    base = path.parent
    cfg.setdefault("data", {})
    cfg["data"]["dir"] = str((base / cfg["data"].get("dir", "data")).resolve())
    cfg["data"]["handbook_dir"] = str(
        (base / cfg["data"].get("handbook_dir", "data/速通手册")).resolve()
    )
    return cfg


def load_taxonomy(path: str | Path | None = None) -> dict:
    path = Path(path) if path else (PROJECT_ROOT / "taxonomy.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
