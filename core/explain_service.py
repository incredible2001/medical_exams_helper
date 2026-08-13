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
        # 头部：完整题干 + 全部选项 + 正确答案/你的答案，让解析时有完整上下文
        head_parts = []
        if screen.get("question_id"):
            head_parts.append(screen["question_id"])
        if screen.get("question_type"):
            head_parts.append(screen["question_type"])
        lines = ["  ".join(head_parts), screen["stem"]]
        if screen.get("options"):
            lines.append("　".join(f"{k}. {v}" for k, v in sorted(screen["options"].items())))
        if screen.get("correct_answer"):
            ans = f"正确答案：{screen['correct_answer']}"
            if screen.get("my_answer"):
                ans += f"　你的答案：{screen['my_answer']}"
            lines.append(ans)
        yield ("header", "\n".join(lines))
        try:
            for tok in self.client.chat_stream(build_explain_messages(screen)):
                yield ("token", tok)
        except DeepSeekError as e:
            yield ("error", str(e))
            return
        yield ("done", screen)
