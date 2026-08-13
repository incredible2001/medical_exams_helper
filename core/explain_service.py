"""F8 讲解服务：dump → 解析 → DeepSeek 流式逐选项分析。

以生成器产出事件：
    ("header", str)   题目头
    ("token",  str)   流式文本片段
    ("error",  str)   错误
    ("done",   dict)  完成，携带解析到的题干记录（供「保存本讲解」）
"""
from __future__ import annotations

from core.adb import AdbError
from core.db import DB
from core.deepseek_client import DeepSeekClient, DeepSeekError, build_explain_messages
from core.screen_parser import parse_dump


class ExplainService:
    def __init__(self, adb, client: DeepSeekClient, db: DB):
        self.adb = adb
        self.client = client
        self.db = db

    def explain(self):
        try:
            xml = self.adb.dump_ui_xml()
        except AdbError as e:
            yield ("error", f"adb 错误：{e}")
            return
        screen = parse_dump(xml)
        if not screen["stem"]:
            yield ("error", "当前屏幕未识别到题目。请把题干区置于可见位置再按 F8。")
            return
        header = screen.get("question_id") or ""
        title = f"{header}  {screen['stem'][:40]}" if header else screen["stem"][:40]
        yield ("header", title)
        try:
            for tok in self.client.chat_stream(build_explain_messages(screen)):
                yield ("token", tok)
        except DeepSeekError as e:
            yield ("error", str(e))
            return
        yield ("done", screen)
