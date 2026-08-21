"""Code Agent：根据用户任务描述生成 Python 代码。"""
from __future__ import annotations

import re
from typing import Any

from ..events import EventBus, EV_CODE, EV_LOG
from ..llm import LLMClient

SYSTEM_PROMPT = """你是一名资深 Python 工程师，负责根据用户需求编写代码。

要求：
1. 只输出一份完整可运行的 Python 代码，不要输出解释文字（可以放在代码注释里）。
2. 代码必须能直接 `python 文件.py` 运行，不要依赖未安装的第三方库。
3. 程序要有明确的输入/输出：可以读 sys.argv，但必须提供默认值
   （例如 `n = int(sys.argv[1]) if len(sys.argv) > 1 else 10`），
   保证不带参数直接运行也不会报错。
4. 如果任务要求不确定，做合理假设并在注释中说明。
5. 输出格式：必须用 ```python 代码块包裹整个代码。"""


def extract_code(text: str) -> str:
    """从 LLM 回复中提取 Python 代码。

    优先取 ```python ... ``` 代码块；若没有则整段视为代码。
    """
    if not text:
        return ""
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL)
    if blocks:
        # 取最长的代码块，通常是完整程序
        return max(blocks, key=len).strip()
    # 兜底：去掉常见的说明前缀后返回
    return text.strip()


class CodeAgent:
    def __init__(self, llm: LLMClient, bus: EventBus | None = None, harness: Any | None = None) -> None:
        # 优先使用 Harness 提供的基础设施（事件总线、沙箱、工具）
        self.llm = llm
        if harness is not None:
            bus = harness.bus
        self.bus = bus or EventBus()

    def generate(self, task: str, existing_files: list[str] | None = None) -> str:
        """生成代码，返回代码字符串。"""
        existing = ""
        if existing_files:
            existing = "\n".join(f"- {f}" for f in existing_files)
            existing = f"\n工作目录中已有的文件：\n{existing}\n"

        user_prompt = f"""用户任务：
{task}
{existing}
请编写一份可直接运行的 Python 程序。"""
        self.bus.emit(EV_LOG, agent="CodeAgent", message=f"CodeAgent 正在为任务生成代码：{task}")
        raw = self.llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
        code = extract_code(raw)
        self.bus.emit(
            EV_CODE,
            agent="CodeAgent",
            message="CodeAgent 已生成代码",
            data={"code": code, "raw": raw},
        )
        return code
