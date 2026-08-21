"""Debug Agent：运行代码，若失败则用 LLM 修复，迭代到通过或达到轮次上限。"""
from __future__ import annotations

from ..events import EventBus, EV_FIX, EV_LOG, EV_RUN
from ..llm import LLMClient
from ..sandbox import RunResult, Sandbox
from .code_agent import extract_code

DEBUG_SYSTEM_PROMPT = """你是一名 Python 调试专家。用户会给你一段代码和它的运行报错。

请分析报错原因，输出修复后的完整代码（不要只输出修改片段，必须是完整可运行的程序）。
要求：
1. 输出格式：必须用 ```python 代码块包裹整个修复后的代码。
2. 如果报错信息不完整，做最可能的修复。
3. 保持原程序的功能不变，只修复导致运行失败的问题。
4. 如果程序因缺少命令行参数（如 IndexError: list index out of range）而失败，
   请在读参数处加上默认值（如 `n = int(sys.argv[1]) if len(sys.argv) > 1 else 10`），
   保证不带参数也能运行。"""


class DebugAgent:
    def __init__(
        self,
        llm: LLMClient,
        sandbox: Sandbox,
        bus: EventBus | None = None,
        max_rounds: int | None = None,
    ) -> None:
        self.llm = llm
        self.sandbox = sandbox
        self.bus = bus or EventBus()
        self.max_rounds = max_rounds

    def fix(
        self,
        task: str,
        code: str,
        result: RunResult,
        filename: str = "main.py",
    ) -> str:
        """根据一次失败运行结果，让 LLM 修复代码，返回修复后的代码。"""
        user_prompt = f"""原始任务：
{task}

当前代码：
```python
{code}
```

运行结果（exit code={result.returncode}, 超时={result.timed_out}）：
[stdout]
{result.stdout or '(无)'}
[/stdout]
[stderr]
{result.stderr or '(无)'}
[/stderr]

请输出修复后的完整代码。"""
        self.bus.emit(
            EV_LOG,
            agent="DebugAgent",
            message="DebugAgent 分析报错并修复代码",
            data={"stderr": result.stderr or result.stdout},
        )
        raw = self.llm.chat(
            [
                {"role": "system", "content": DEBUG_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
        fixed = extract_code(raw)
        self.sandbox.write_file(filename, fixed)
        self.bus.emit(
            EV_FIX,
            agent="DebugAgent",
            message="DebugAgent 已修复代码",
            data={"code": fixed, "raw": raw},
        )
        return fixed
