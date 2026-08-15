"""速通手册渲染：按分组生成 markdown + 合并 HTML（目录/折叠/打印）。"""
from __future__ import annotations

import datetime
import html as _html
from collections import defaultdict
from pathlib import Path

from core.config import load_taxonomy
from core.db import DB
from core.screen_parser import normalize_text

CARD = "card"


def build_weak_points(questions: list[dict]) -> dict[str, list[dict]]:
    """从每题的一句话考点（ai_summary）生成薄弱知识点。

    返回 {分组: [{"text": 考点, "qidx": 组内第几题（对应手册卡片编号）}]}。
    按题目顺序去重；随新题加入自动更新，无条数上限。
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        groups.setdefault(q.get("system_group") or "其他", []).append(q)
    weak: dict[str, list[dict]] = {}
    for g, qs in groups.items():
        seen: set[str] = set()
        pts: list[dict] = []
        for idx, q in enumerate(qs, 1):
            s = (q.get("ai_summary") or "").strip()
            if not s:
                continue
            k = normalize_text(s)
            if k in seen:
                continue
            seen.add(k)
            pts.append({"text": s, "qidx": idx})
        if pts:
            weak[g] = pts
    return weak


def render(db: DB, config: dict) -> str | None:
    """生成分组 md + 合并 HTML，返回 HTML 绝对路径；无已整理错题返回 None。"""
    questions = db.all_processed_questions()
    if not questions:
        return None
    taxonomy = load_taxonomy()
    weak = build_weak_points(questions)
    comments = {q["id"]: db.get_comments(q["id"]) for q in questions}

    groups: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        groups.setdefault(q.get("system_group") or "其他", []).append(q)

    order = [g for g in taxonomy["order"] if g in groups] + \
            [g for g in groups if g not in taxonomy["order"]]

    handbook_dir = Path(config["data"]["handbook_dir"])
    handbook_dir.mkdir(parents=True, exist_ok=True)

    # 分组 markdown
    for g in order:
        path = handbook_dir / f"{g}.md"
        path.write_text(_render_group_md(g, groups[g], comments, weak.get(g)), encoding="utf-8")

    # 合并 HTML
    html_path = handbook_dir / "考前速通手册.html"
    html_path.write_text(_render_html(order, groups, comments, weak), encoding="utf-8")
    return str(html_path)


# ---------------- markdown ----------------

def _render_group_md(group: str, qs: list[dict], comments: dict, weak_points) -> str:
    lines = [f"# {group} · 错题卡（{len(qs)} 题）", ""]
    if weak_points:
        lines += ["## 薄弱知识点", ""]
        lines += [f"- [{p['qidx']}] {p['text']}" for p in weak_points]
        lines += [""]
    for i, q in enumerate(qs, 1):
        lines += [f"### {i}. [{q.get('question_id') or q['id'][:8]}] {q.get('stem')}", ""]
        ok = "✅" if q.get("my_answer") == q.get("correct_answer") else "❌"
        lines += [f"- **正确答案** {q.get('correct_answer')}｜**你的答案** {q.get('my_answer')} {ok}"]
        if q.get("ai_summary"):
            lines += [f"- **一句话考点**：{q['ai_summary']}"]
        expl = q.get("kaodian") or q.get("standard_explanation") or ""
        if expl:
            lines += [f"- **官方解析**：{expl[:200]}"]
        if q.get("ai_mnemonics"):
            lines += [f"- **口诀/技巧**：{q['ai_mnemonics']}"]
        if q.get("ai_wrong_reason"):
            lines += [f"- **错选原因**：{q['ai_wrong_reason']}"]
        cs = comments.get(q["id"], [])
        if cs:
            lines += ["- **精选评论**："]
            for c in cs[:3]:
                lines += [f"  - {c['nickname']}（👍{c['likes']}）：{c['content'][:120]}"]
        lines += [""]
    return "\n".join(lines)


# ---------------- HTML ----------------

def _render_html(order: list[str], groups: dict, comments: dict, weak: dict) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    total = sum(len(groups[g]) for g in order)
    stats = " ｜ ".join(f"{g} {len(groups[g])} 题" for g in order)

    toc = "\n".join(
        f'<li><a href="#sec-{_slug(g)}">{_html.escape(g)}</a>'
        f'<span class="cnt">{len(groups[g])}</span></li>'
        for g in order
    )

    sections = []
    for g in order:
        sections.append(_render_section(g, groups[g], comments, weak.get(g)))
    body = "\n".join(sections)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>考前速通手册</title>
<style>
:root {{
  --bg: #f7f8fa; --card: #ffffff; --ink: #1f2328; --mut: #6b7280;
  --acc: #1a7f64; --line: #e5e7eb; --good: #1a7f64; --bad: #c0392b;
  --mark: #fff3bf;
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font: 15px/1.7 "PingFang SC","Microsoft YaHei",system-ui,sans-serif; }}
.wrap {{ max-width: 860px; margin: 0 auto; padding: 28px 20px 80px; }}
header {{ margin-bottom: 20px; }}
h1 {{ font-size: 26px; margin: 0 0 6px; }}
.sub {{ color: var(--mut); font-size: 13px; }}
.stats {{ margin: 14px 0; padding: 10px 14px; background:var(--card);
  border:1px solid var(--line); border-radius: 10px; font-size: 13px; }}
.toolbar {{ margin: 10px 0; }}
.toolbar button {{ padding: 6px 12px; border-radius: 8px; border:1px solid var(--line);
  background:var(--card); cursor:pointer; font-size: 13px; }}
.toolbar button:hover {{ background:#eef2f0; }}
nav.toc {{ background:var(--card); border:1px solid var(--line); border-radius: 12px;
  padding: 14px 18px; margin-bottom: 24px; }}
nav.toc h2 {{ font-size: 14px; margin: 0 0 8px; color: var(--mut); }}
nav.toc ul {{ list-style:none; padding:0; margin:0; }}
nav.toc li {{ display:flex; justify-content:space-between; padding: 4px 0; border-bottom:1px dashed var(--line); }}
nav.toc li:last-child {{ border-bottom:none; }}
nav.toc a {{ color: var(--ink); text-decoration:none; }}
nav.toc .cnt {{ color: var(--mut); font-size: 12px; }}
section h2 {{ font-size: 20px; border-left: 4px solid var(--acc);
  padding-left: 10px; margin: 32px 0 10px; }}
.weakbox {{ background:#fffbe8; border:1px solid #f0e3b0; border-radius: 10px;
  padding: 12px 16px; margin: 10px 0 16px; font-size: 14px; }}
.weakbox b {{ color:#8a6d1a; }}
.weakbox ul {{ margin:6px 0 0; padding:0; list-style:none; }}
.weakbox li {{ padding:2px 0; }}
.weakbox a {{ color:var(--ink); text-decoration:none; }}
.weakbox a:hover {{ color:var(--acc); }}
.widx {{ display:inline-block; min-width:18px; text-align:center; background:var(--acc);
  color:#fff; border-radius:5px; font-size:12px; padding:0 4px; margin-right:6px; }}
details.card {{ background:var(--card); border:1px solid var(--line);
  border-radius: 12px; margin: 10px 0; overflow:hidden; }}
details.card summary {{ cursor:pointer; padding: 12px 16px; list-style:none; }}
details.card summary::-webkit-details-marker {{ display:none; }}
.qtitle {{ font-weight:600; }}
.qid {{ color:var(--acc); font-size: 13px; background:#e6f4ef;
  padding:1px 7px; border-radius:6px; margin-right:6px; white-space:nowrap; }}
.qmeta {{ color:var(--mut); font-size: 13px; margin-top:4px; }}
.qmeta .ok {{ color:var(--good); font-weight:600; }}
.qmeta .no {{ color:var(--bad); font-weight:600; }}
.qbody {{ padding: 0 16px 14px; border-top:1px solid var(--line); font-size: 14px; }}
.opts {{ background:#fafbfc; border-radius:8px; padding:8px 12px; margin:10px 0; }}
.opts .opt {{ display:block; padding:2px 0; }}
.opts mark {{ background:var(--mark); padding:0 4px; border-radius:4px; }}
.qbody b.k {{ color:var(--acc); }}
.comments {{ background:#f6f9fb; border-radius:8px; padding:8px 12px; margin-top:8px; font-size:13px; }}
.comments .c {{ padding:3px 0; }}
.comments .c .who {{ color:var(--mut); font-size:12px; }}
.comments .c:not(:last-child) {{ border-bottom:1px dashed var(--line); }}
details.aiex {{ margin-top:8px; border:1px dashed var(--line); border-radius:8px; padding:6px 10px; }}
details.aiex summary {{ cursor:pointer; font-size:13px; color:var(--acc); }}
details.aiex .aiex-body {{ margin-top:6px; font-size:13px; white-space:pre-wrap; color:#374151; }}
@media print {{
  body {{ background:#fff; }}
  .toolbar, nav.toc {{ display:none; }}
  details.card {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>📖 考前速通手册</h1>
  <div class="sub">医考帮备考助手 · 生成于 {now} · 共 {total} 题</div>
  <div class="stats">{stats}</div>
  <div class="toolbar">
    <button onclick="toggleAll(true)">展开全部</button>
    <button onclick="toggleAll(false)">折叠全部</button>
    <button onclick="window.print()">🖨 打印</button>
  </div>
</header>
<nav class="toc"><h2>目录</h2><ul>{toc}</ul></nav>
{body}
</div>
<script>
function toggleAll(open) {{
  document.querySelectorAll('details.card').forEach(d => d.open = open);
}}
window.addEventListener('beforeprint', () => toggleAll(true));
</script>
</body>
</html>"""


def _render_section(group: str, qs: list[dict], comments: dict, weak_points) -> str:
    slug = _slug(group)
    cards = []
    for i, q in enumerate(qs, 1):
        cards.append(_render_card(i, q, comments.get(q["id"], []), slug))
    weak_html = ""
    if weak_points:
        rows = []
        for p in weak_points:
            cid = f"q-{slug}-{p['qidx']}"
            rows.append(
                f'<li><a href="#{cid}" onclick="document.getElementById(\'{cid}\').open=true">'
                f'<span class="widx">{p["qidx"]}</span>{_html.escape(p["text"])}</a></li>'
            )
        weak_html = f'<div class="weakbox"><b>薄弱知识点</b><ul>{"".join(rows)}</ul></div>'
    return (f'<section id="sec-{slug}">'
            f'<h2>{_html.escape(group)} <span style="color:var(--mut);font-size:14px">（{len(qs)} 题）</span></h2>'
            f'{weak_html}{"".join(cards)}</section>')


def _render_card(i: int, q: dict, cs: list[dict], slug: str) -> str:
    ok = q.get("my_answer") == q.get("correct_answer")
    ok_cls = "ok" if ok else "no"
    ok_label = "答对" if ok else "答错"
    options = "".join(
        f'<span class="opt">{"✅ " if k == q.get("correct_answer") else ""}{k}. {_html.escape(v)}</span>'
        for k, v in sorted((q.get("options") or {}).items())
    )
    expl = q.get("kaodian") or q.get("standard_explanation") or ""
    comments_html = ""
    if cs:
        rows = "".join(
            f'<div class="c"><span class="who">{_html.escape(c["nickname"])}（👍{c["likes"]}）</span> '
            f'{_html.escape(c["content"])}</div>'
            for c in cs[:3]
        )
        comments_html = f'<div class="comments">{rows}</div>'
    aiex = q.get("ai_explanation") or ""
    aiex_html = (
        f'<details class="aiex"><summary><b class="k">AI 完整讲解</b></summary>'
        f'<div class="aiex-body">{_html.escape(aiex)}</div></details>'
        if aiex else ""
    )
    return f"""<details class="card" id="q-{slug}-{i}">
<summary>
  <div class="qtitle">{i}. <span class="qid">{_html.escape(q.get("question_id") or "")}</span>{_html.escape(q.get("stem") or "")}</div>
  <div class="qmeta"><span class="{ok_cls}">{ok_label}</span> ｜ 正确答案 {q.get("correct_answer")} ｜ 你的答案 {q.get("my_answer") or "-"}</div>
</summary>
<div class="qbody">
  <div class="opts">{options}</div>
  {"<p><b class=\"k\">一句话考点：</b>" + _html.escape(q.get("ai_summary") or "") + "</p>" if q.get("ai_summary") else ""}
  {"<p><b class=\"k\">口诀/技巧：</b>" + _html.escape(q.get("ai_mnemonics") or "") + "</p>" if q.get("ai_mnemonics") else ""}
  {"<p><b class=\"k\">错选原因：</b>" + _html.escape(q.get("ai_wrong_reason") or "") + "</p>" if q.get("ai_wrong_reason") else ""}
  {"<p><b class=\"k\">官方解析：</b>" + _html.escape(expl[:300]) + "</p>" if expl else ""}
  {comments_html}
  {aiex_html}
</div>
</details>"""


def _slug(g: str) -> str:
    import re
    return re.sub(r"\W+", "_", g)
