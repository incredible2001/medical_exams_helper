"""F9 整理服务：增量分批调 DeepSeek → 错题卡/分组/一句话考点 → 生成速通手册。
（薄弱知识点由 renderer 从每题 ai_summary 实时生成，见 renderer.build_weak_points）

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
        + "3. summary：一句话考点（本题核心知识点），写清关键鉴别点、易错点，30~60 字。"
        + "用 ** 星号把 1~3 个最关键的信息点包起来突出显示（如诊断名、首选药、关键数值、鉴别特征），"
        + "例如「**铜绿假单胞菌**感染首选**头孢他啶**」；无把握时宁少勿多。\n"
        + "4. mnemonics：从精选评论提炼一条口诀/做题技巧；评论无价值则依据官方解析自拟一条。\n"
        + "5. wrong_reason：若考生答错，一句话指出错选思路错在哪；答对则填空串。\n\n"
        + "严格只输出合法 JSON，结构如下：\n"
        + '{"entries":[{"key":"","group":"","summary":"","mnemonics":"","wrong_reason":""}]}'
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
        # 整理前：把「待绑定」评论尽量并入同试卷的待整理题
        bound = 0
        if self.db.pending_count() and rows:
            for q in rows:
                if q.get("paper"):
                    bound += self.db.bind_pending(q["id"], q["paper"])
        total = 0
        if not rows:
            remain = self.db.pending_count()
            tip = f"；另有 {remain} 条评论待绑定（回题干处按 F7 合并）" if remain else ""
            yield ("status", "没有待整理的新错题，重新生成手册" + tip)
        else:
            if bound:
                yield ("status", f"已先补绑 {bound} 条待绑定评论…")
            # 附带每题精选评论
            for q in rows:
                q["_comments"] = self.db.get_comments(q["id"])

            batch_size = max(1, int(self.cfg.get("deepseek", {}).get("batch_size", 25)))
            batches = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]
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

        yield ("status", "正在生成速通手册…")
        path = renderer.render(self.db, self.cfg)
        summary = f"✅ 整理完成：新增 {total} 题"
        if path:
            summary += f"\n手册已生成：{path}"
        remain = self.db.pending_count()
        if remain:
            summary += f"\n⚠ 还有 {remain} 条评论待绑定（回题干处按 F7 再按一次即合并）"
        yield ("done", summary)
