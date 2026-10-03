"""screen_parser 回归自测：三种题面格式各一份合成 dump，直接运行看 PASS/FAIL。

    python scripts/test_parser.py

合成 dump 只保留 uiautomator 里 text= 文本节点的顺序（parse_dump 只读这个），
不依赖模拟器；题面文字为自造示例，不含真题内容。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.screen_parser import parse_dump  # noqa: E402


def _dump(texts: list[str]) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?><hierarchy>'
            + "".join(f'<node text="{t}" bounds="[0,0][10,10]"/>' for t in texts)
            + "</hierarchy>")


# 真题（A3/A4：病例 + 年份ID前缀子题）
_REAL = [
    "2022（一试+二试）", "U2（一试）", "A3/A4型题", "32 /150",
    "男，58岁，突发胸痛2小时，伴大汗。心电图示V1-V4导联ST段抬高。",
    "2022U2-32 最可能的诊断是",
    "A.急性心包炎", "B.急性心肌梗死", "C.主动脉夹层", "D.肺栓塞", "E.气胸",
    "答案：正确答案 B，你的答案 D",
]

# 模考卷（无年份，仅 "6." 题号前缀；单元号并在试卷标签尾部）
_MOCK = [
    "医考帮26执医万人模考二  U1", "A1型题", "6 /150",
    "6.下列属于抗血小板药物的是",
    "A.华法林", "B.阿司匹林", "C.肝素", "D.尿激酶", "E.氨甲环酸",
    "答案：正确答案C，你的答案：B",
]

# 章节练习（题干完全无前缀，题号只在顶部「1 /14」）
_CHAPTER = [
    "中医学基础", "第一章 中医基本特点", "A1型题", "1 /14",
    "我国现存最早的医学专著是",
    "A.《五十二病方》", "B.《神农本草经》", "C.《黄帝内经》", "D.《中藏经》", "E.《伤寒论》",
    "答案：正确答案 C，你的答案 C",
    "第一章 中医基本特点",
]

# 章节练习里出现的真题（带年份ID前缀，但上方是「学科名 + 章节名」而非真题卷头）
# 这两行标题不得被当成 A3/A4 病例并进题干
_CHAPTER_REAL = [
    "生理学", "第八章 尿的生成和排出", "A1型题", "3 /45",
    "2016U2-33 在肾脏产生的是",
    "A.皮质醇", "B.醛固酮", "C.肾上腺素", "D.去甲肾上腺素", "E.肾素",
    "答案：正确答案 E，你的答案 C",
]

# 章节练习 A3/A4（病例在上、无前缀子题在下）
_CHAPTER_CASE = [
    "内科学", "第三章 呼吸系统", "A3/A4型题", "1 /5",
    "男，60岁，反复咳嗽咳痰10年，活动后气短3年，加重1周。",
    "最可能的诊断是",
    "A.支气管哮喘", "B.慢性阻塞性肺疾病", "C.支气管扩张", "D.肺结核", "E.肺癌",
    "答案：正确答案 B，你的答案 A",
]

# 章节练习的评论区屏（章节名被回收走，只剩学科名 → 来源标签必须与题干屏一致）
_CHAPTER_COMMENTS = [
    "中医学基础", "内容持续优化，最近更新时间：2026-08-17",
    "最热评论(13)", "张三", "兰州大学 2024-01-24",
    "1.《黄帝内经》：我国现存最早的医学专著。", "赞同(2149)", "反对(15)", "13 回复",
]

# 评论区屏（无题干、无选项 → 不得识别成题目）
_COMMENTS = [
    "2022（一试+二试）", "U2（一试）", "内容持续优化",
    "最热评论(47)", "张三", "北京大学医学部 2026-06-16",
    "这题的鉴别点在于心电图变化，注意区分。", "赞同(23)", "反对(1)", "3 回复",
    "A. 这条评论开头长得像选项，但这里是评论区",
]


def _check(name: str, texts: list[str], expect: dict) -> bool:
    got = parse_dump(_dump(texts))
    bad = [f"{k}: 期望 {v!r}，实际 {got.get(k)!r}"
           for k, v in expect.items() if got.get(k) != v]
    print(("PASS  " if not bad else "FAIL  ") + name)
    for b in bad:
        print("      " + b)
    return not bad


def main() -> int:
    ok = True
    ok &= _check("真题 A3/A4", _REAL, {
        "paper": "2022（一试+二试）", "unit": "U2（一试）",
        "question_id": "2022U2-32", "stem": _REAL[4] + "\n最可能的诊断是",
        "case_stem": _REAL[4], "correct_answer": "B", "my_answer": "D",
        "question_no": "32", "is_question_screen": True,
    })
    ok &= _check("模考卷", _MOCK, {
        "paper": "医考帮26执医万人模考二", "unit": "U1",
        "question_id": "U1-6", "stem": "下列属于抗血小板药物的是",
        "correct_answer": "C", "my_answer": "B", "question_no": "6",
        "is_question_screen": True,
    })
    ok &= _check("章节练习（裸题干）", _CHAPTER, {
        # paper 取顶部学科名（两屏共有），章节名只进 chapter_label
        "paper": "中医学基础", "chapter_label": "第一章 中医基本特点",
        "stem": "我国现存最早的医学专著是", "case_stem": None,
        "question_type": "A1型题", "question_no": "1",
        "correct_answer": "C", "my_answer": "C", "is_question_screen": True,
    })
    ok &= _check("章节练习里的真题（标题不得并入题干）", _CHAPTER_REAL, {
        "paper": "生理学", "chapter_label": "第八章 尿的生成和排出",
        "question_id": "2016U2-33", "stem": "在肾脏产生的是", "case_stem": None,
        "correct_answer": "E", "my_answer": "C",
    })
    ok &= _check("章节练习 A3/A4（病例并入）", _CHAPTER_CASE, {
        "paper": "内科学",
        "stem": _CHAPTER_CASE[4] + "\n最可能的诊断是",
        "case_stem": _CHAPTER_CASE[4], "correct_answer": "B",
    })
    ok &= _check("章节练习评论区（来源标签与题干屏一致）", _CHAPTER_COMMENTS, {
        "paper": "中医学基础", "stem": None, "is_question_screen": False,
    })
    ok &= _check("评论区不得误判为题目", _COMMENTS, {
        "stem": None, "is_question_screen": False,
    })
    print("\n" + ("全部通过 ✅" if ok else "存在失败 ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
