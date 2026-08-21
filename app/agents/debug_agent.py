"""Debug Agent：运行代码，若失败则用 LLM 修复，迭代到通过或达到轮次上限。"""
from __future__ import annotations

import re
from typing import Any

from ..events import EventBus, EV_FIX, EV_LOG, EV_RUN
from ..llm import LLMClient
from ..sandbox import RunResult, Sandbox
from .code_agent import extract_code


def parse_traceback(stderr: str) -> dict[str, Any]:
    """从 Python traceback 文本中提取错误类型、消息与行号（尽力而为）。

    示例输入：
        Traceback (most recent call last):
          File "main.py", line 5, in <module>
            undefined_func(n)
        NameError: name 'undefined_func' is not defined

    返回 {"error_type": "NameError", "message": "...", "line_no": 5, "file": "main.py"}
    """
    info = {"error_type": "", "message": "", "line_no": 0, "file": ""}
    if not stderr:
        return info
    m = re.search(r'File "([^"]+)", line (\d+)', stderr)
    if m:
        info["file"] = m.group(1)
        info["line_no"] = int(m.group(2))
    lines = [l.strip() for l in stderr.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        if re.match(r"^[A-Za-z_][\w.]*(Error|Exception)(\([^)]*\))?:", line):
            typ, _, msg = line.partition(":")
            info["error_type"] = typ.strip()
            info["message"] = msg.strip()
            break
    if not info["error_type"]:
        for line in lines:
            if "Error" in line or "Exception" in line:
                info["message"] = line[:200]
                break
    return info

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
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        """根据一次失败运行结果，让 LLM 修复代码，返回修复后的代码。

        history: 前几轮的失败诊断列表，供 LLM 参考，避免重复犯同样的错。
        """
        diag = parse_traceback(result.stderr)
        # 结构化错误诊断
        diag_text = ""
        if diag["error_type"]:
            diag_text = (
                f"[错误诊断]\n"
                f"类型：{diag['error_type']}\n"
                f"文件：{diag['file']}，行号：{diag['line_no'] or '未知'}\n"
                f"消息：{diag['message'] or '(无)'}\n"
            )
        # 历史记忆：前几轮失败原因
        history_text = ""
        if history:
            rows = []
            for h in history:
                err = h.get("error_type") or "未知"
                msg = h.get("message") or h.get("stderr_tail", "")[:150]
                rows.append(f"- 第 {h.get('round', '?')} 轮失败：{err}：{msg[:150]}")
            history_text = (
                "\n\n[修复历史]（前几轮仍失败，请换一种思路，不要重复同样的修改）\n"
                + "\n".join(rows)
            )

        user_prompt = f"""原始任务：
{task}

当前代码：
```python
{code}
```

运行结果（exit code={result.returncode}, 超时={result.timed_out}）：
{diag_text}
[stdout]
{result.stdout or '(无)'}
[/stdout]
[stderr]
{result.stderr or '(无)'}
[/stderr]
{history_text}
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
