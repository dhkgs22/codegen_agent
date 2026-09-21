"""Code Agent：根据用户任务描述生成指定语言的代码。"""
from __future__ import annotations

import re
from typing import Any

from ..events import EventBus, EV_CODE, EV_LOG
from ..languages import Language, resolve_language
from ..llm import LLMClient


def extract_code(text: str, language: str | Language | None = None) -> str:
    """从 LLM 回复中提取代码。

    优先取与目标语言匹配的 ```lang 代码块（LLM 有时会顺带输出别的语言的片段）；
    没有匹配的代码块则取最长的那个（通常是完整程序）；连代码块都没有就整段当代码。
    """
    if not text:
        return ""
    lang: Language | None
    if isinstance(language, Language):
        lang = language
    elif language is not None:
        lang = resolve_language(language)
    else:
        lang = None

    blocks = re.findall(
        r"```([A-Za-z0-9+#._-]*)[ \t]*\r?\n?(.*?)```", text, flags=re.DOTALL
    )
    if not blocks:
        return text.strip()
    if lang is not None:
        want = {lang.fence.lower(), lang.ext.lstrip(".").lower(), lang.key.lower()}
        for tag, body in blocks:
            if tag.strip().lower() in want:
                return body.strip()
    # 兜底：取最长的代码块
    return max((body for _, body in blocks), key=len).strip()


class CodeAgent:
    def __init__(
        self,
        llm: LLMClient,
        bus: EventBus | None = None,
        harness: Any | None = None,
        language: str | Language | None = None,
    ) -> None:
        # 优先使用 Harness 提供的基础设施（事件总线、沙箱、工具）
        self.llm = llm
        if harness is not None:
            bus = harness.bus
            if language is None:
                language = harness.language
        self.bus = bus or EventBus()
        self.language: Language = (
            language if isinstance(language, Language) else resolve_language(language)
        )

    def generate(
        self,
        task: str,
        existing_files: list[str] | None = None,
        language: str | Language | None = None,
    ) -> str:
        """生成代码，返回代码字符串。"""
        lang = (
            language
            if isinstance(language, Language)
            else resolve_language(language if language is not None else self.language.key)
        )
        existing = ""
        if existing_files:
            existing = "\n".join(f"- {f}" for f in existing_files)
            existing = f"\n工作目录中已有的文件：\n{existing}\n"

        user_prompt = f"""用户任务：
{task}
{existing}
请编写一份可直接运行的 {lang.display} 程序。"""
        self.bus.emit(
            EV_LOG,
            agent="CodeAgent",
            message=f"CodeAgent 正在为任务生成 {lang.display} 代码：{task}",
        )
        raw = self.llm.chat(
            [
                {"role": "system", "content": lang.code_system_prompt()},
                {"role": "user", "content": user_prompt},
            ]
        )
        code = extract_code(raw, lang)
        self.bus.emit(
            EV_CODE,
            agent="CodeAgent",
            message=f"CodeAgent 已生成 {lang.display} 代码",
            data={
                "code": code,
                "raw": raw,
                "language": lang.key,
                "language_display": lang.display,
                "fence": lang.fence,
            },
        )
        return code
