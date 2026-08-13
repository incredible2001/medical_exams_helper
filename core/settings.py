"""设置读写：.env 密钥 / config.toml 修改（供「设置」对话框使用）。"""
from __future__ import annotations

import os
import re

from core.config import PROJECT_ROOT

ENV_PATH = PROJECT_ROOT / ".env"
CONFIG_PATH = PROJECT_ROOT / "config.toml"


def get_env_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def save_env_key(key: str) -> bool:
    key = key.strip()
    if not key:
        return False
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith("DEEPSEEK_API_KEY="):
            lines[i] = f"DEEPSEEK_API_KEY={key}"
            found = True
            break
    if not found:
        lines.append(f"DEEPSEEK_API_KEY={key}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def get_config_value(key: str) -> str:
    """读取 config.toml 中某键的值（path/port/model/base_url）。"""
    if not CONFIG_PATH.exists():
        return ""
    text = CONFIG_PATH.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}\s*=\s*\"?([^\"\n#]*?)\"?\s*$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def set_config_value(key: str, value: str) -> bool:
    """修改 config.toml 中某键的值；字符串键带引号，数值键不带。"""
    if not CONFIG_PATH.exists():
        return False
    text = CONFIG_PATH.read_text(encoding="utf-8")
    value = value.strip()
    if key in ("path", "model", "base_url"):
        new = re.sub(rf'(^{re.escape(key)}\s*=\s*")[^"]*(")',
                     lambda m: m.group(1) + value + m.group(2),
                     text, flags=re.MULTILINE)
    else:
        new = re.sub(rf"(^{re.escape(key)}\s*=\s*)[^\n]*",
                     lambda m: m.group(1) + value,
                     text, flags=re.MULTILINE)
    if new == text:
        return False
    CONFIG_PATH.write_text(new, encoding="utf-8")
    return True
