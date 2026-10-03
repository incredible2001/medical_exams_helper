"""解析 uiautomator dump XML → 结构化题目记录。

实测格式（医考帮题面）：
    text="2022（一试+二试）"                    试卷标签
    text="U2（一试）"                            单元标签
    text="A1型题"                               题型
    text="32 /150"                              题号
    text="2022U2-32 髋关节前脱位最典型的临床表现是"   题干（真题，带年份ID前缀）
    text="A.伸直，外展，外旋畸形"                  选项
    text="答案：正确答案 B，你的答案 B"             对错
    text="（外科学P651）"..."                   考点还原

另外两种题面（题干前缀形态不同，靠下面的分支分别识别）：
    模考卷：text="医考帮26执医万人模考二  U1" / text="6.题干正文"（仅题号前缀，无年份）
    章节练习：text="中医学基础" / text="第一章 中医基本特点" / text="1 /14"
             / text="我国现存最早的医学专著是"（题干无任何前缀，题号只在顶部）

评论区额外：
    text="最热评论(47)"                         评论分区
    text="昵称" / "学校 日期" / 评论内容 / "赞同(N)" ...
"""
from __future__ import annotations

import hashlib
import html
import re
from typing import Any

_KNOWN_LABELS = {
    "考点还原", "标准解析", "解析", "写评论", "笔记", "收藏", "评论", "点赞",
    "内容持续优化", "难度：", "统计：", "标签：", "纠错",
}


def normalize_text(s: str) -> str:
    """题干规范化（去空白/标点/转义/小写），用于去重哈希。"""
    return re.sub(r"[\s\W_]+", "", html.unescape(s)).lower()


def question_hash(stem: str) -> str:
    """题干 → 稳定短哈希（去重主键）。"""
    return hashlib.md5(normalize_text(stem).encode("utf-8")).hexdigest()[:16]


def _is_paper_like(t: str) -> bool:
    """试卷标签：真题「2022（一试+二试）」或模考卷「医考帮26执医万人模考二  U1」。

    模考卷标签特征：含「模考/模拟/试卷」且为短行（≤40 字）、非选项/题干/对错行。
    """
    return bool(
        re.fullmatch(r"20\d{2}（.+）", t)
        or (len(t) <= 40 and re.search(r"模考|模拟|试卷", t)
            and not re.match(r"^[A-E]\.", t)
            and not re.match(r"^\d+\.", t)
            and not re.match(r"^答案：", t))
    )


def _split_mock_unit(t: str) -> tuple[str, str | None]:
    """模考卷标签尾部常带单元号（「医考帮26执医万人模考二  U1」）→ (去单元标签, 单元号)。"""
    m = re.search(r"\s+U(\d+)\s*$", t)
    if m:
        return t[: m.start()].strip(), "U" + m.group(1)
    return t, None


def _is_header_line(t: str) -> bool:
    """章节练习模式的顶部章节标签行（「第一章 中医基本特点」「第2节 骨学」）。

    题号在顶部、题干无前缀时，这类行是题干上方最近的正文，必须排除，
    否则会被当成题干或 A3/A4 病例题干。
    """
    return bool(re.match(r"^第\s*[0-9一二三四五六七八九十百千]+\s*[章节讲篇部]", t))


def _looks_like_stem(t: str) -> bool:
    """裸题干候选校验（章节练习）：有实际文字，且不是标签/表头/选项/数字行。"""
    return bool(len(t) >= 4 and not _is_skip_before_stem(t))


def _fallback_source(texts: list[str]) -> str | None:
    """无试卷标签时的「来源」兜底：取界面顶部第一行的短文本。

    章节练习没有试卷标签，两个屏的顶部栏也不一样：
    题干屏是「学科 + 章节名」，评论区屏滚走了章节名、只剩学科名。
    取两屏共有的第一行（学科名），第二按并入评论才有可匹配的键。
    """
    t = texts[0] if texts else ""
    if t and len(t) <= 20 and t not in _KNOWN_LABELS and "。" not in t and not _is_school_line(t):
        return t
    return None


def _looks_like_case(t: str) -> bool:
    """A3/A4 共用题干（病例）特征：成段的叙述文字（够长且有中文标点）。

    章节练习里题干上方还可能是科目标题（「中医学基础」）或章节名，靠这个长度+
    标点条件把它们挡掉，避免把标题当病例并入题干。
    """
    return bool(len(t) >= 20 and re.search(r"[，。；：]", t))


def _is_skip_before_stem(t: str) -> bool:
    """ID 前缀题干之前应跳过的非正文文本（头标签 / 第N问 / 选项 / 对错行等）。"""
    return bool(
        re.fullmatch(r"第\d+问", t)
        or _is_header_line(t)                       # 章节练习的章节标题行
        or re.fullmatch(r"20\d{2}（[^）]*）", t)
        or re.fullmatch(r"U\d+（[^）]*）", t)
        or re.fullmatch(r"U\d+", t)                 # 模考卷独立单元号
        or _is_paper_like(t)                        # 试卷标签（真题 / 模考卷）
        or re.match(r"^第\d+", t)                    # 模考分数说明行「第1-66题，…」
        or re.match(r"^统计[:：]", t)                # 「统计：全部考生作答…」
        or re.fullmatch(r"[A-Z]\d*型题", t)
        or re.fullmatch(r"\d+\s*/\s*\d+", t)
        or re.match(r"^[A-E]\.\s*\S+", t)
        or re.match(r"^答案：", t)
        or t in _KNOWN_LABELS
        or re.fullmatch(r"\d+", t)
    )


def _case_before(texts: list[str], i: int) -> str | None:
    """A3/A4 共用题干（病例）：取子题（下标 i）之前第一个非标签正文。

    这个候选必须「像病例」（见 _looks_like_case）才采用：章节练习里子题上方
    还可能是科目标题（「生理学」）或章节名（「第八章 尿的生成和排出」），
    不加这道关卡会被当成病例并进题干（实测：stem 变成「生理学\\n在肾脏产生的是」）。
    真题卷实测 85 条 A3/A4 病例题干最短 35 字，与门槛（20 字）有充足余量。
    """
    for t in reversed(texts[:i]):
        if _is_skip_before_stem(t):
            continue
        return t if _looks_like_case(t) else None
    return None


def parse_dump(xml: str) -> dict[str, Any]:
    texts = [html.unescape(t) for t in re.findall(r'text="([^"]*)"', xml) if t.strip()]
    scr: dict[str, Any] = {
        "paper": None, "unit": None, "question_type": None,
        "question_no": None, "question_id": None, "stem": None,
        "case_stem": None, "chapter_label": None,
        "options": {}, "correct_answer": None, "my_answer": None,
        "kaodian": None, "standard_explanation": None, "stats": None,
        "explanation_blob": None,
        "comment_tags": [], "comments": [],
        "is_question_screen": False, "has_image": _has_image_node(xml),
    }

    # 是否具备「题目屏」特征（有选项或对错行）。模拟卷/章节练习的题干前缀更弱
    # （"6.xxx" / 完全无前缀），必须见到选项/对错行才认题干，
    # 避免把评论区/解析里的「数字.文本」误当题干。
    _q_signal = (any(re.match(r"^答案：正确答案", t) for t in texts)
                 or any(re.match(r"^[A-E]\.\s*\S", t) for t in texts))

    # 题号 / 题型行的下标：章节练习的裸题干必须位于其下方（上方是科目标题、章节名）
    header_idx = -1

    # 按顺序扫描
    for i, t in enumerate(texts):
        # 章节练习的章节标题行（题号上方，用来给无试卷标签的题一个「来源」标签）
        if (scr["chapter_label"] is None and header_idx < 0
                and _is_header_line(t) and len(t) <= 40):
            scr["chapter_label"] = t
        # 试卷标签（真题 "2022（一试+二试）" / 模考卷 "医考帮26执医万人模考二  U1"）
        if scr["paper"] is None and _is_paper_like(t):
            paper, unit = _split_mock_unit(t)
            scr["paper"] = paper
            if unit and scr["unit"] is None:
                scr["unit"] = unit
        # 单元标签（真题 "U2（一试）"；模考独立 "U1"）
        if scr["unit"] is None and re.fullmatch(r"U\d+（[^）]*）|U\d+", t):
            scr["unit"] = t
        # 题型（A1/A2/A3/A4/B1/C 型题等）
        is_head_line = False   # 本行是否为题号/题型行（正文区从它下面开始）
        if scr["question_type"] is None and re.fullmatch(r"[A-Z]\d*(?:/[A-Z]\d+)*型题", t):
            scr["question_type"] = t
            is_head_line = True
        # 题号
        m = re.fullmatch(r"(\d+)\s*/\s*\d+", t)
        if m and scr["question_no"] is None:
            scr["question_no"] = m.group(1)
            is_head_line = True
        if is_head_line:
            header_idx = i
        # 题干（真题带 ID 前缀，年份后的代码不固定：2022U2-32 / 2022ESU1-1 ...）
        m = re.match(r"^(20\d{2}[A-Za-z0-9]*-\d+)\s+(.+)$", t)
        if m and scr["stem"] is None:
            scr["question_id"] = m.group(1)
            scr["stem"] = m.group(2)
            # A3/A4 共用题干（病例）：把子题前的病例正文并入题干，保留完整上下文
            case = _case_before(texts, i)
            if case:
                scr["case_stem"] = case
                scr["stem"] = case + "\n" + scr["stem"]
            scr["is_question_screen"] = True
        # 题干（模拟卷：仅题号前缀 "6.xxx"，无 ID；需有选项/对错行佐证）
        if scr["stem"] is None and _q_signal:
            m = re.match(r"^(\d{1,3})\.\s*(.+)$", t)
            if m:
                scr["question_no"] = scr["question_no"] or m.group(1)
                scr["stem"] = m.group(2)
                if scr["question_id"] is None:
                    scr["question_id"] = f"{scr['unit'] or '模拟'}-{m.group(1)}"
                case = _case_before(texts, i)
                if case:
                    scr["case_stem"] = case
                    scr["stem"] = case + "\n" + scr["stem"]
                scr["is_question_screen"] = True
        # 题干（章节练习：题干完全无前缀，题号只在顶部「1 /14」）
        # 定位方式：第一个选项行的上一行，且必须落在题号/题型行之下（排除科目标题、章节名）。
        if (scr["stem"] is None and _q_signal and not scr["options"]
                and header_idx >= 0 and i - 1 > header_idx
                and re.match(r"^[A-E]\.\s*\S", t)):
            cand = texts[i - 1]
            if _looks_like_stem(cand):
                scr["stem"] = cand
                scr["is_question_screen"] = True
                case = _case_before(texts, i - 1)
                if case:
                    scr["case_stem"] = case
                    scr["stem"] = case + "\n" + scr["stem"]
        # 选项
        m = re.match(r"^([A-E])\.\s*(.+)$", t)
        if m and m.group(1) not in scr["options"]:
            scr["options"][m.group(1)] = m.group(2)
        # 对错（真题 "答案：正确答案 B，你的答案 D"；模考 "答案：正确答案C，你的答案：B"）
        m = re.match(r"^答案：正确答案\s*([A-E])\s*[，,]\s*你的答案\s*[:：]?\s*([A-E])$", t)
        if m:
            scr["correct_answer"], scr["my_answer"] = m.group(1), m.group(2)
        # 统计
        if t.startswith("本题") and "收藏" in t and scr["stats"] is None:
            scr["stats"] = t
        # 评论标签（答案有争议 704 等）
        m = re.match(r"^(答案有争议|题目质量低|评论无看点|评论很精彩)\s*\d+$", t)
        if m:
            scr["comment_tags"].append(t)
        # 解析类标签：考点还原 / 标准解析 / 解析 → 下一条非标签文本为正文
        if t in ("考点还原", "标准解析", "解析"):
            nxt = _next_content(texts, i)
            if t == "考点还原":
                if scr["kaodian"] is None and nxt:
                    scr["kaodian"] = nxt
            else:
                if scr["standard_explanation"] is None and nxt:
                    scr["standard_explanation"] = nxt
        # 逐选项解析 blob（长文本且含 X对/X错）
        if len(t) > 150 and re.search(r"（[A-E]对|（[A-E]错）", t) and scr["explanation_blob"] is None:
            scr["explanation_blob"] = t

    # 章节练习等无试卷标签的题面：用顶部学科名充当「来源」标签，
    # 否则 paper 为空 → 评论区第二按无处可并、待绑定评论永远绑不上。
    if not scr["paper"]:
        scr["paper"] = _fallback_source(texts)

    scr["comments"] = _extract_comments(texts)
    return scr


def _next_content(texts: list[str], i: int) -> str | None:
    """标签文本之后的下一条非标签、非纯数字文本。"""
    for nxt in texts[i + 1:]:
        if nxt in _KNOWN_LABELS or re.fullmatch(r"\d+", nxt):
            continue
        return nxt
    return None


def _is_school_line(line: str) -> bool:
    """判断是否为评论的学校行：学校/医院名（无中文标点，≤40字）+ 日期结尾。

    真题评论日期为「2026-06-16」，模考卷为「08-09」——两者都接受。
    刻意排除含中文标点的行（如「内容持续优化，最近更新时间：2026-06-16」）。
    """
    return bool(re.fullmatch(r"[^，。；：？！、\s]{1,40}\s*(?:\d{4}-)?\d{2}-\d{2}", line))


def _extract_comments(texts: list[str]) -> list[dict[str, Any]]:
    """从文本流中提取评论 (昵称, 内容, 赞同数)。

    评论块结构稳定：昵称 → 「学校 日期」 → [内容] → 赞同(N) → 反对(N) → [N 回复]。
    以「后一行是学校日期」来定位昵称位置，每条评论的内容 = 该昵称到下一个昵称之间
    的第一个非数字、非标签、非赞同/反对/回复文本；赞同数取其中的「赞同(N)」。
    """
    comments: list[dict[str, Any]] = []
    n = len(texts)
    nick_idx = [i for i in range(n - 1)
                if _is_school_line(texts[i + 1])]
    for idx, i in enumerate(nick_idx):
        end = nick_idx[idx + 1] if idx + 1 < len(nick_idx) else n
        content, likes = "", 0
        for t in texts[i + 2:end]:
            if re.fullmatch(r"\d+", t) or t in _KNOWN_LABELS:
                continue
            m = re.fullmatch(r"赞同\((\d+)\)", t)
            if m:
                likes = int(m.group(1))
                continue
            if re.fullmatch(r"反对\(\d+\)", t) or re.fullmatch(r"\d*\s*回复", t):
                continue
            if not content:
                content = t
        comments.append({"nickname": texts[i], "content": content, "likes": likes})
    return comments


def _has_image_node(xml: str) -> bool:
    """是否有较大尺寸的 ImageView（疑似题干配图，如心电图/影像）。"""
    for m in re.finditer(r'class="android\.widget\.ImageView"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        l, t, r, b = (int(g) for g in m.groups())
        if r - l > 80 and b - t > 80:
            return True
    return False
