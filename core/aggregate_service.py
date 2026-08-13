"""F9 整理服务：增量分批调 DeepSeek → 错题卡/分组/薄弱点 → 生成速通手册。

事件流：
    ("status", str)   进度
    ("error",  str)   某批失败
    ("done",   str)   完成总结
"""
from __future__ import annotations

from typing import Any, Iterator

from core import renderer
from core.db import DB
from core.deepseek_client import DeepSeekClient, DeepSeekError

_VALID_GROUPS = [
    "基础医学", "临床内科", "临床外科", "妇儿",
    "预防与公共卫生", "医学人文", "中医学基础",
]


def build_aggregate_messages(batch: list[dict]) -> list[dict]:
    records = []
    for q in batch:
        opts = " ".join(f"{k}.{v}" for k, v in sorted((q.get("options") or {}).items()))
        comments = q.get("_comments") or []
        c_text = "\n".join(f"- {c['nickname']}：{c['content']}(赞{c['likes']})" for c in comments[:3])
        records.append(
            "KEY: {key}\n"
            "题号: {qid}\n"
            "题干: {stem}\n"
            "选项: {opts}\n"
            "答案: 正确 {correct} | 考生 {mine}\n"
            "官方解析: {expl}\n"
            "精选评论:\n{comments}".format(
                key=q["id"], qid=q.get("question_id") or "-", stem=q["stem"],
                opts=opts, correct=q.get("correct_answer") or "?", mine=q.get("my_answer") or "未作答",
                expl=(q.get("kaodian") or q.get("standard_explanation") or "")[:500],
                comments=c_text or "（无）",
            )
        )
    user = (
        "下面是一批执业医师真题错题记录。请对每道题完成三件事并输出 JSON：\n\n"
        + "\n\n".join(records)
        + "\n\n要求：\n"
        + "1. 每道题输出一条 entry，key 必须原样返回上面的 KEY。\n"
        + "2. group 必须精确取自：" + " / ".join(_VALID_GROUPS)
        + "（按题干内容归入临床系统/学科，拿不准取最接近的，宁粗勿细）。\n"
        + "3. summary：一句话考点（本题核心知识点）。\n"
        + "4. mnemonics：从精选评论提炼一条口诀/做题技巧；评论无价值则依据官方解析自拟一条。\n"
        + "5. wrong_reason：若考生答错，一句话指出错选思路错在哪；答对则填空串。\n"
        + "6. 最后汇总 group_weak_points：对每个出现的 group，给出该组反复考、易错的 3~6 条高频考点。\n\n"
        + "严格只输出合法 JSON，结构如下：\n"
        + '{"entries":[{"key":"","group":"","summary":"","mnemonics":"","wrong_reason":""}],'
        + '"group_weak_points":{"分组":["考点1","考点2"]}}'
    )
    return [{"role": "system", "content": "你是执业医师考试备考助手，负责把学生的错题整理成考前速通手册。只输出合法 JSON。"},
            {"role": "user", "content": user}]


class AggregateService:
    def __init__(self, db: DB, client: DeepSeekClient, config: dict):
        self.db = db
        self.client = client
        self.cfg = config

    def aggregate(self) -> Iterator[tuple[str, str]]:
        rows = self.db.unprocessed_questions()
        if not rows:
            yield ("status", "没有待整理的新错题")
            yield ("done", "")
            return
        # 附带每题精选评论
        for q in rows:
            q["_comments"] = self.db.get_comments(q["id"])

        batch_size = max(1, int(self.cfg.get("deepseek", {}).get("batch_size", 25)))
        batches = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]
        weak = self.db.meta_get("weak_points", {}) or {}
        total = 0

        for bi, batch in enumerate(batches, 1):
            yield ("status", f"批次 {bi}/{len(batches)}：处理 {len(batch)} 题…")
            try:
                result = self.client.chat_json(build_aggregate_messages(batch))
            except DeepSeekError as e:
                yield ("error", f"批次 {bi} 失败：{e}（本批已跳过，可稍后重试）")
                continue
            for e in result.get("entries") or []:
                key = e.get("key")
                if not key or not self.db.get_question(key):
                    continue
                group = e.get("group") or ""
                if group not in _VALID_GROUPS:
                    group = "其他"
                self.db.set_question_ai(key, group, e.get("summary", ""),
                                        e.get("mnemonics", ""), e.get("wrong_reason", ""))
                total += 1
            for g, points in (result.get("group_weak_points") or {}).items():
                merged = weak.setdefault(g, [])
                for p in points:
                    if p and p not in merged:
                        merged.append(p)

        self.db.meta_set("weak_points", weak)
        yield ("status", "正在生成速通手册…")
        path = renderer.render(self.db, self.cfg)
        groups = len(weak)
        summary = f"✅ 整理完成：新增 {total} 题，更新 {groups} 组薄弱点"
        if path:
            summary += f"\n手册已生成：{path}"
        yield ("done", summary)
