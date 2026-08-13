"""F7 记录服务：两按式错题收集。

第一按（题干屏）：完整记录题干/选项/对错/考点还原。
第二按（评论区）：把标准解析 + 评论并入最近匹配的题干记录。
匹配信号：时间邻近 + 试卷标签一致 + （可选）解析 blob 的正确答案字母校验。

注：图片题暂不裁剪保存（视频解析缩略图会误判为题目图），has_image 仅作标记。
"""
from __future__ import annotations

import re
from typing import Any

from core.adb import AdbError
from core.db import DB
from core.screen_parser import parse_dump, question_hash


def _blob_correct_answer(blob: str) -> str | None:
    """从解析 blob（如「…（B对AD错）。…」）中反推正确答案字母。"""
    m = re.search(r"（([A-E])对", blob)
    return m.group(1) if m else None


class RecordService:
    def __init__(self, adb, db: DB, config: dict):
        self.adb = adb
        self.db = db
        self.cfg = config

    # ---------- 入口 ----------
    def record(self) -> tuple[bool, str]:
        try:
            xml = self.adb.dump_ui_xml()
        except AdbError as e:
            return False, f"adb 错误：{e}"
        screen = parse_dump(xml)
        if screen["stem"]:
            return self._record_question(screen)
        if screen["comments"] or screen["standard_explanation"] or screen["explanation_blob"]:
            return self._record_comments(screen)
        return False, "未识别到题目或评论区，请确认停留在题目 / 评论区"

    # ---------- 第一按：题干屏 ----------
    def _record_question(self, screen: dict) -> tuple[bool, str]:
        q = self._screen_to_question(screen)
        self.db.upsert_question(q)
        added = self.db.append_comments(q["id"], screen["comments"])  # 部分滚动时题干屏也可能带评论
        if added:  # 新评论并入已整理过的题 → 下次 F9 重整理
            self.db.touch_dirty(q["id"])
        bound = self.db.bind_pending(q["id"], screen["paper"] or "") if screen["paper"] else 0
        parts = [f"已记录 {q.get('question_id') or q['id'][:8]}"]
        if added:
            parts.append(f"评论+{added}")
        if bound:
            parts.append(f"补绑评论{bound}")
        return True, "✅ " + "，".join(parts)

    # ---------- 第二按：评论区 ----------
    def _record_comments(self, screen: dict) -> tuple[bool, str]:
        paper = screen.get("paper")
        if not paper:
            return self._store_pending(screen)
        recent = self.db.recent_question(paper, self.cfg.get("merge", {}).get("window_minutes", 3))
        if recent is None:
            return self._store_pending(screen)
        # 校验：解析 blob 出现时，正确答案字母必须一致，防串题
        blob = screen.get("explanation_blob")
        if blob:
            blob_ans = _blob_correct_answer(blob)
            if blob_ans and recent.get("correct_answer") and blob_ans != recent["correct_answer"]:
                return self._store_pending(screen, reason="正确答案不匹配")
        # 并入解析
        patch = {"id": recent["id"]}
        if screen.get("standard_explanation"):
            patch["standard_explanation"] = screen["standard_explanation"]
        if screen.get("explanation_blob"):
            patch["explanation_blob"] = screen["explanation_blob"]
        if len(patch) > 1:
            self.db.upsert_question(patch)
        added = self.db.append_comments(recent["id"], screen["comments"])
        if added or len(patch) > 1:
            self.db.touch_dirty(recent["id"])  # 新内容并入已整理过的题 → 下次 F9 重整理
        qid = recent.get("question_id") or recent["id"][:8]
        return True, f"✅ 已并入 {qid} 的评论 +{added} 条" if added else f"✅ 已并入 {qid}（无新评论）"

    def _store_pending(self, screen: dict, reason: str = "附近无匹配记录") -> tuple[bool, str]:
        n = self.db.add_pending(screen.get("paper") or "", screen.get("comments") or [])
        tip = f"（{reason}）" if not screen.get("comments") else ""
        return False, f"评论已存为待绑定：请回题干处按一次 F7 自动合并{tip}"

    # ---------- 组装 / 图片 ----------
    @staticmethod
    def _screen_to_question(screen: dict) -> dict[str, Any]:
        return {
            "id": question_hash(screen["stem"]),
            "question_id": screen.get("question_id"),
            "stem": screen["stem"],
            "options": screen.get("options") or {},
            "correct_answer": screen.get("correct_answer"),
            "my_answer": screen.get("my_answer"),
            "paper": screen.get("paper"),
            "unit": screen.get("unit"),
            "question_type": screen.get("question_type"),
            "kaodian": screen.get("kaodian"),
            "standard_explanation": screen.get("standard_explanation"),
            "explanation_blob": screen.get("explanation_blob"),
            "stats": screen.get("stats"),
            "comment_tags": screen.get("comment_tags") or [],
            "has_image": screen.get("has_image") or False,
            "processed": 0,
        }
