"""速通手册渲染：按分组生成 markdown + 合并 HTML（目录/折叠/打印）。"""
from __future__ import annotations

import datetime
import html as _html
import re
from collections import defaultdict
from pathlib import Path

from core.config import load_taxonomy
from core.db import DB
from core.screen_parser import normalize_text

CARD = "card"

_MARK_RE = re.compile(r"\*\*(.+?)\*\*", re.S)

# 旧数据没有 ** 标记时，用启发式关键短语兜底高亮（尽量保证每条摘要至少能划到一处重点）
_HEUR_PATTERNS = [
    r"必备条件[^，。；、]{2,16}",
    r"首选[^，。；、]{2,14}",
    r"最常(?:见|伤|损|引起|累及)[^，。；、]{2,16}",
    r"最常见于[^，。；、]{2,16}",
    r"最可能(?:是|为)[^，。；、]{2,14}",
    r"典型(?:表现|特征)(?:为|是)?[^，。；、]{2,16}",
    r"(?:常)?呈[阴阳]性(?:（[^）]*）)?",
    r"最易(?:见|发生|累及|并发)[^，。；、]{2,12}",
    r"最主要[^，。；、]{1,14}",
    r"(?:金标准|诊断标准|确诊依据)[^，。；、]{0,12}",
    r"(?:药物|药)(?:是|为|首选)[^，。；、]{2,14}",
    r"特征(?:为|是)?[^，。；、]{2,12}",
    r"提示[^，。；、]{2,10}",
    r"表现为[^，。；、]{2,12}",
    r"(?:诊断为|确诊为)[^，。；、]{2,14}",
    r"(?:需|要)(?:注意|警惕|鉴别)[^，。；、]{2,12}",
]


def _merge_spans(spans) -> list[tuple[int, int]]:
    spans = sorted(spans)
    if not spans:
        return []
    out: list[list[int]] = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def highlight_key(text: str) -> str:
    """把一句话考点（ai_summary）的关键部分渲染成 <mark> 高亮，HTML 已转义。

    优先识别 **...** 标记（AI 新版 prompt 输出）；旧数据无标记时用启发式关键短语兜底。
    """
    if not text:
        return ""
    marks = [(m.start(1), m.end(1)) for m in _MARK_RE.finditer(text)]
    if not marks:
        marks = _merge_spans(
            (m.start(), m.end())
            for pat in _HEUR_PATTERNS
            for m in re.finditer(pat, text)
        )
    parts, prev = [], 0
    for s, e in marks:
        parts.append(_html.escape(text[prev:s]))
        parts.append(f"<mark>{_html.escape(text[s:e])}</mark>")
        prev = e
    parts.append(_html.escape(text[prev:]))
    return "".join(parts)


def _chapter_of(q: dict, chapter_map: dict) -> tuple[str, str]:
    """返回 (所属分组, 章节名)：章节优先取 chapter；缺省时用「分组·其他」兜底。
    注意：chapter 为空才算缺省——「中医学基础」这类分组名与学科名相同的是合法学科，不能改。"""
    g = q.get("system_group") or "其他"
    c = (q.get("chapter") or "").strip()
    if not c:
        c = f"{g}·其他"
    return chapter_map.get(c) or g, c


def _chapter_map(taxonomy: dict) -> dict[str, str]:
    """taxonomy.groups 倒排：学科名 → 所属分组。"""
    return {s: g for g, subs in taxonomy["groups"].items() for s in subs}


def _chapter_placements(questions: list[dict], taxonomy: dict) -> list[tuple[str, str, list[dict]]]:
    """有序章节占位 [(分组, 学科, 该学科题目列表), ...]。

    顺序：分组按 taxonomy.order，组内学科按 taxonomy.groups 顺序，未收录学科追加。
    章节内题目按录入顺序（与 build_weak_points 一致，保证编号对齐）。
    """
    chapter_map = _chapter_map(taxonomy)
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for q in questions:
        g, c = _chapter_of(q, chapter_map)
        buckets[(g, c)].append(q)
    order: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for g in taxonomy["order"]:
        for s in taxonomy["groups"].get(g, []):
            if (g, s) in buckets and (g, s) not in seen:
                order.append((g, s))
                seen.add((g, s))
        for key in list(buckets):
            if key[0] == g and key not in seen:
                order.append(key)
                seen.add(key)
    for key in list(buckets):
        if key not in seen:
            order.append(key)
    return [(g, c, buckets[(g, c)]) for (g, c) in order]


def build_weak_points(questions: list[dict], taxonomy: dict) -> dict[str, list[dict]]:
    """从每题的一句话考点（ai_summary）按学科生成薄弱知识点。

    返回 {学科: [{"text": 考点, "qidx": 该学科内第几题（对应手册卡片编号）}]}。
    按题目顺序去重；随新题加入自动更新，无条数上限。
    """
    chapter_map = _chapter_map(taxonomy)
    groups: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        _, c = _chapter_of(q, chapter_map)
        groups[c].append(q)
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
    """生成每学科 md + 合并 HTML，返回 HTML 绝对路径；无已整理错题返回 None。"""
    questions = db.all_processed_questions()
    if not questions:
        return None
    taxonomy = load_taxonomy()
    weak = build_weak_points(questions, taxonomy)
    comments = {q["id"]: db.get_comments(q["id"]) for q in questions}
    placements = _chapter_placements(questions, taxonomy)

    handbook_dir = Path(config["data"]["handbook_dir"])
    handbook_dir.mkdir(parents=True, exist_ok=True)

    # 每学科一个 markdown；清掉旧分组级 .md 残留
    md_stems = set()
    for _, c, qs in placements:
        md_stems.add(c)
        path = handbook_dir / f"{c}.md"
        path.write_text(_render_chapter_md(c, qs, comments, weak.get(c)), encoding="utf-8")
    for old in handbook_dir.glob("*.md"):
        if old.stem not in md_stems:
            old.unlink()

    # 合并 HTML
    html_path = handbook_dir / "考前速通手册.html"
    html_path.write_text(_render_html(placements, comments, weak), encoding="utf-8")
    return str(html_path)


# ---------------- markdown ----------------

def _render_chapter_md(chapter: str, qs: list[dict], comments: dict, weak_points) -> str:
    lines = [f"# {chapter} · 错题卡（{len(qs)} 题）", ""]
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

def _render_html(placements: list[tuple[str, str, list[dict]]], comments: dict, weak: dict) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    total = sum(len(qs) for _, _, qs in placements)
    g_total: dict[str, int] = {}
    for g, _, qs in placements:
        g_total[g] = g_total.get(g, 0) + len(qs)
    stats = " ｜ ".join(f"{g} {n} 题" for g, n in g_total.items())

    # 两级目录：分组作标签（toc-group），组内每个学科一条可点链接
    toc: list[str] = []
    last_g: str | None = None
    for g, c, qs in placements:
        if g != last_g:
            toc.append(f'<li class="toc-group">{_html.escape(g)}</li>')
            last_g = g
        toc.append(
            f'<li><a href="#sec-{_slug(c)}">'
            f'<span class="toc-name">{_html.escape(c)}</span>'
            f'<span class="cnt">{len(qs)}</span></a></li>'
        )
    toc_html = "\n".join(toc)

    sections = [_render_section(c, qs, comments, weak.get(c)) for _, c, qs in placements]
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
  --mark: #fff3bf; --side: 170px;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font: 15px/1.7 "PingFang SC","Microsoft YaHei",system-ui,sans-serif; }}
.layout {{ display:flex; min-height:100vh; }}
/* 左侧固定目录 */
nav.toc {{ position:fixed; top:0; left:0; bottom:0; width:var(--side); overflow-y:auto;
  background:var(--card); border-right:1px solid var(--line); padding:18px 12px; z-index:10; }}
nav.toc h2 {{ font-size:14px; margin:0 0 10px; color:var(--mut); letter-spacing:1px; }}
nav.toc ul {{ list-style:none; padding:0; margin:0; }}
nav.toc li.toc-group {{ color:var(--mut); font-size:12px; font-weight:600; letter-spacing:.5px;
  padding:14px 9px 3px; }}
nav.toc li.toc-group:first-child {{ padding-top:2px; }}
nav.toc li a {{ display:flex; align-items:center; justify-content:space-between; gap:8px;
  padding:7px 9px; padding-left:18px; border-radius:8px; color:var(--ink); text-decoration:none;
  margin:2px 0; font-size:14px; }}
nav.toc li a:hover {{ background:#eef2f0; }}
nav.toc li a.active {{ background:var(--acc); color:#fff; }}
nav.toc .toc-name {{ min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
nav.toc .cnt {{ color:var(--mut); font-size:12px; flex:none; }}
nav.toc li a.active .cnt {{ color:#d9f2ea; }}
.content {{ flex:1; margin-left:var(--side); max-width:940px; padding:28px 26px 90px; }}
header {{ margin-bottom: 20px; }}
h1 {{ font-size: 26px; margin: 0 0 6px; }}
.sub {{ color: var(--mut); font-size: 13px; }}
.stats {{ margin: 14px 0; padding: 10px 14px; background:var(--card);
  border:1px solid var(--line); border-radius: 10px; font-size: 13px; }}
.toolbar {{ margin: 10px 0; }}
.toolbar button {{ padding: 6px 12px; border-radius: 8px; border:1px solid var(--line);
  background:var(--card); cursor:pointer; font-size: 13px; }}
.toolbar button:hover {{ background:#eef2f0; }}
.toolbar button.primary {{ background:var(--acc); border-color:var(--acc); color:#fff; }}
section h2 {{ font-size: 20px; border-left: 4px solid var(--acc);
  padding-left: 10px; margin: 32px 0 10px; }}
.weakbox {{ background:#fffbe8; border:1px solid #f0e3b0; border-radius: 10px;
  padding: 12px 16px; margin: 10px 0 16px; font-size: 14px; }}
.weakbox b {{ color:#8a6d1a; }}
.weakbox ul {{ margin:6px 0 0; padding:0; list-style:none; }}
.weakbox li {{ padding:2px 0; }}
.weakbox a {{ color:var(--ink); text-decoration:none; }}
.weakbox a:hover {{ color:var(--acc); }}
.weakbox mark {{ background:#ffe08a; }}
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
mark {{ background:var(--mark); color:inherit; padding:0 3px; border-radius:4px;
  -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
.comments {{ background:#f6f9fb; border-radius:8px; padding:8px 12px; margin-top:8px; font-size:13px; }}
.comments .c {{ padding:3px 0; }}
.comments .c .who {{ color:var(--mut); font-size:12px; }}
.comments .c:not(:last-child) {{ border-bottom:1px dashed var(--line); }}
details.aiex {{ margin-top:8px; border:1px dashed var(--line); border-radius:8px; padding:6px 10px; }}
details.aiex summary {{ cursor:pointer; font-size:13px; color:var(--acc); }}
details.aiex .aiex-body {{ margin-top:6px; font-size:13px; white-space:pre-wrap; color:#374151; }}
@media print {{
  body {{ background:#fff; }}
  .layout {{ display:block; }}
  nav.toc, .toolbar {{ display:none !important; }}
  .content {{ margin-left:0; max-width:none; padding:16px; }}
  details.card {{ break-inside: avoid; }}
  /* 仅打印薄弱知识点 */
  body.print-weak .stats {{ display:none !important; }}
  body.print-weak details.card,
  body.print-weak details.aiex,
  body.print-weak .comments {{ display:none !important; }}
  body.print-weak section h2 {{ margin:14px 0 6px; font-size:17px; }}
  body.print-weak .weakbox {{ break-inside:avoid; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  body.print-weak .weakbox a {{ text-decoration:none; color:var(--ink); }}
}}
</style>
</head>
<body>
<div class="layout">
<nav class="toc"><h2>📑 目录</h2><ul>{toc_html}</ul></nav>
<div class="content">
<header>
  <h1>📖 考前速通手册</h1>
  <div class="sub">医考帮备考助手 · 生成于 {now} · 共 {total} 题</div>
  <div class="stats">{stats}</div>
  <div class="toolbar">
    <button onclick="toggleAll(true)">展开全部</button>
    <button onclick="toggleAll(false)">折叠全部</button>
    <button class="primary" onclick="printWeak()">🖨 打印薄弱知识点</button>
    <button onclick="window.print()">打印全部</button>
  </div>
</header>
{body}
</div>
</div>
<script>
function toggleAll(open) {{
  document.querySelectorAll('details.card').forEach(d => d.open = open);
}}
// 打印：只输出各分组「薄弱知识点」，不打印题目卡片
function printWeak() {{
  document.body.classList.add('print-weak');
  window.print();
}}
window.addEventListener('beforeprint', () => toggleAll(true));
window.addEventListener('afterprint', () => document.body.classList.remove('print-weak'));
// 目录滚动高亮当前分组
(function () {{
  const links = Array.from(document.querySelectorAll('nav.toc a'));
  const secs = Array.from(document.querySelectorAll('section'));
  function onScroll() {{
    const pos = window.scrollY + 80;
    let cur = secs[0];
    for (const s of secs) {{ if (s.offsetTop <= pos) cur = s; else break; }}
    links.forEach(l => l.classList.toggle('active', l.getAttribute('href') === '#' + cur.id));
  }}
  window.addEventListener('scroll', onScroll, {{ passive: true }});
  onScroll();
}})();
</script>
</body>
</html>"""


def _render_section(chapter: str, qs: list[dict], comments: dict, weak_points) -> str:
    slug = _slug(chapter)
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
                f'<span class="widx">{p["qidx"]}</span>{highlight_key(p["text"])}</a></li>'
            )
        weak_html = f'<div class="weakbox"><b>薄弱知识点</b><ul>{"".join(rows)}</ul></div>'
    return (f'<section id="sec-{slug}">'
            f'<h2>{_html.escape(chapter)} <span style="color:var(--mut);font-size:14px">（{len(qs)} 题）</span></h2>'
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
  {"<p><b class=\"k\">一句话考点：</b>" + highlight_key(q.get("ai_summary") or "") + "</p>" if q.get("ai_summary") else ""}
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
