"""DeepSeek 客户端（OpenAI 兼容协议）+ prompt 模板。"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Iterator

from openai import OpenAI

DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"


class DeepSeekError(Exception):
    pass


class DeepSeekClient:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL,
                 base_url: str = DEFAULT_BASE_URL):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not self.api_key:
            raise DeepSeekError("未找到 DEEPSEEK_API_KEY。请把密钥填到项目根目录 .env 文件（参考 .env.example）。")
        self.model = model
        self.client = OpenAI(api_key=self.api_key, base_url=base_url)

    def chat(self, messages: list[dict], temperature: float = 0.3) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=temperature
            )
            return resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            raise DeepSeekError(f"DeepSeek 请求失败: {e}") from e

    def chat_stream(self, messages: list[dict], temperature: float = 0.3) -> Iterator[str]:
        try:
            stream = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=temperature, stream=True
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:  # noqa: BLE001
            raise DeepSeekError(f"DeepSeek 流式请求失败: {e}") from e

    def chat_json(self, messages: list[dict], temperature: float = 0.2) -> dict:
        """请求 JSON 结构化输出（用于 F9 整理），失败自动从文本中提取 JSON。"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=temperature,
                response_format={"type": "json_object"},
            )
            return _extract_json(resp.choices[0].message.content or "")
        except Exception as e:  # noqa: BLE001
            raise DeepSeekError(f"DeepSeek JSON 请求失败: {e}") from e


def _extract_json(text: str) -> dict:
    """从回复中解析 JSON（容忍 markdown 代码块包裹）。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            return json.loads(text[s : e + 1])
        raise DeepSeekError("AI 返回的内容不是合法 JSON") from None


# ---------- prompt 模板 ----------

_SYSTEM_EXPLAIN = (
    "你是执业医师资格考试的资深讲师。你擅长把一道题的考点讲透，"
    "输出简洁、准确、结构化的中文，不得编造教材没有的内容。必须严格按用户要求的格式输出。"
)


def build_explain_messages(record: dict[str, Any]) -> list[dict]:
    """F8 一键讲解：逐选项分析 + 考点讲解。"""
    options_text = "\n".join(f"{k}. {v}" for k, v in sorted(record["options"].items()))
    user = f"""下面是一道执业医师真题，请逐选项讲解并给出考点。

【题干】{record['stem']}
【题型】{record['question_type'] or '未知'}
【选项】
{options_text}
【正确答案】{record.get('correct_answer') or '未知'}
【考生答案】{record.get('my_answer') or '未作答'}
【App考点还原（教材原文参考）】{record.get('kaodian') or '无'}

请严格按以下格式输出：
【考点】一句话说明本题在考什么（对应哪个系统/章节）
【逐选项】逐行列出，A~E 全部覆盖：A：正确/错误——原因（1~2句）；B：……；C：……
【易错点】本题最容易错的思路；若考生答错，重点分析为什么选错
【记忆锚点】一句口诀或对比表，方便快速记忆"""
    return [{"role": "system", "content": _SYSTEM_EXPLAIN},
            {"role": "user", "content": user}]
