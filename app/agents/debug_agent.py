"""Debug Agent：运行代码，若失败则用 LLM 修复，迭代到通过或达到轮次上限。

多语言：报错解析与提示词都取自语言档案（app/languages.py）。
C/C++ 的编译报错、Go 的编译错误、Java 的 javac 报错都各自有不同的格式，
由 Language.parse_error 分派到对应的解析器。
"""
from __future__ import annotations

from typing import Any

from ..events import EventBus, EV_FIX, EV_LOG
from ..languages import Language, language_from_filename, parse_python_traceback, resolve_language
from ..llm import LLMClient
from ..sandbox import RunResult, Sandbox
from .code_agent import extract_code

# 兼容旧调用路径：Python traceback 解析器仍在 debug_agent 命名空间下可用
parse_traceback = parse_python_traceback


class DebugAgent:
    def __init__(
        self,
        llm: LLMClient,
        sandbox: Sandbox | None = None,
        bus: EventBus | None = None,
        max_rounds: int | None = None,
        harness: Any | None = None,
        language: str | Language | None = None,
    ) -> None:
        # 优先使用 Harness 提供的基础设施（事件总线、沙箱、工具）
        if harness is not None:
            sandbox = harness.sandbox
            bus = harness.bus
            if language is None:
                language = harness.language
        self.llm = llm
        self.sandbox = sandbox if sandbox is not None else Sandbox()
        self.bus = bus or EventBus()
        self.max_rounds = max_rounds
        self.language: Language = (
            language if isinstance(language, Language) else resolve_language(language)
        )

    def _lang(self, language: str | Language | None, filename: str) -> Language:
        """定位本次修复所用的语言档案：显式指定 > 文件后缀推断 > Agent 默认。"""
        if isinstance(language, Language):
            return language
        if language is not None:
            return resolve_language(language)
        return language_from_filename(filename, default=self.language.key)

    def fix(
        self,
        task: str,
        code: str,
        result: RunResult,
        filename: str = "main.py",
        history: list[dict[str, Any]] | None = None,
        language: str | Language | None = None,
    ) -> str:
        """根据一次失败运行结果，让 LLM 修复代码，返回修复后的代码。

        history: 前几轮的失败诊断列表，供 LLM 参考，避免重复犯同样的错。
        """
        lang = self._lang(language, filename)
        diag = lang.parse_error(result.stderr, result.stage)
        # 结构化错误诊断
        diag_text = ""
        if diag["error_type"]:
            stage_name = "编译" if result.stage == "build" else "运行"
            diag_text = (
                f"[错误诊断]（{stage_name}阶段）\n"
                f"类型：{diag['error_type']}\n"
                f"文件：{diag['file'] or filename}，行号：{diag['line_no'] or '未知'}\n"
                f"消息：{diag['message'] or '(无)'}\n"
            )
        # 崩溃但没有任何报错输出（C/C++ 里很常见：越界、空指针）
        crash_hint = ""
        if result.returncode != 0 and not (result.stderr or "").strip() and not result.timed_out:
            crash_hint = (
                "\n提示：程序异常终止但没有输出任何报错信息，"
                "常见原因是数组越界、空指针解引用、除以零或未捕获的异常，请重点检查边界条件。\n"
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

当前代码（{lang.display}）：
```{lang.fence}
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
{crash_hint}{history_text}
请输出修复后的完整代码。"""
        self.bus.emit(
            EV_LOG,
            agent="DebugAgent",
            message=f"DebugAgent 分析报错并修复 {lang.display} 代码",
            data={"stderr": result.stderr or result.stdout},
        )
        raw = self.llm.chat(
            [
                {"role": "system", "content": lang.debug_system_prompt()},
                {"role": "user", "content": user_prompt},
            ]
        )
        fixed = extract_code(raw, lang)
        self.sandbox.write_file(filename, fixed)
        self.bus.emit(
            EV_FIX,
            agent="DebugAgent",
            message="DebugAgent 已修复代码",
            data={
                "code": fixed,
                "raw": raw,
                "language": lang.key,
                "fence": lang.fence,
            },
        )
        return fixed

    def fix_tests(
        self,
        task: str,
        code: str,
        test_output: str,
        filename: str = "main.py",
        history: list[dict[str, Any]] | None = None,
        language: str | Language | None = None,
    ) -> str:
        """根据测试失败输出修复代码，返回修复后的代码。

        与 fix() 不同：这里程序本身能运行，但输出不满足测试断言，
        需要按测试要求修正行为逻辑。Test→Debug 协作回环会调用它。
        测试可以是 pytest（Python）或黑盒用例（其它语言）。
        """
        lang = self._lang(language, filename)
        label = "pytest 失败输出" if lang.test_strategy == "pytest" else "黑盒用例失败输出"
        history_text = ""
        if history:
            rows = [
                f"- 第 {h.get('round', '?')} 轮测试失败：{(h.get('summary') or '')[:150]}"
                for h in history
            ]
            history_text = (
                "\n\n[修复历史]（前几轮测试仍未通过，请换一种思路，不要重复同样的修改）\n"
                + "\n".join(rows)
            )

        user_prompt = f"""原始任务：
{task}

当前代码（{lang.display}，能运行，但测试未通过）：
```{lang.fence}
{code}
```

{label}：
{(test_output or '(无输出)')[:3000]}
{history_text}
请修复代码，使所有测试断言通过。保持程序原有功能，只做必要的修改。
请输出修复后的完整代码（```{lang.fence} 包裹）。"""
        self.bus.emit(
            EV_LOG,
            agent="DebugAgent",
            message="DebugAgent 根据测试失败反馈修复代码",
            data={"test_output": test_output[:1000]},
        )
        raw = self.llm.chat(
            [
                {"role": "system", "content": lang.debug_system_prompt()},
                {"role": "user", "content": user_prompt},
            ]
        )
        fixed = extract_code(raw, lang)
        self.sandbox.write_file(filename, fixed)
        self.bus.emit(
            EV_FIX,
            agent="DebugAgent",
            message="DebugAgent 已按测试要求修复代码",
            data={
                "code": fixed,
                "raw": raw,
                "language": lang.key,
                "fence": lang.fence,
            },
        )
        return fixed
