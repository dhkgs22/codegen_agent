"""Test Agent：程序运行通过后，自动生成测试并在沙箱中运行验证。

两种测试策略（由语言档案的 test_strategy 决定）：
- pytest   ：Python 专用，生成 test_main.py，用 subprocess 跑程序断言输出。
- blackbox ：C/C++/Go/Java 等，生成语言无关的 JSON 用例集，编译一次后
             逐条用命令行参数/stdin 调用程序并断言 stdout。

两条策略对外接口一致，都返回 {"tests_code", "passed", "summary", "output", "returncode"}，
因此 Coordinator 的 Test→Debug 协作回环不需要关心底层用的是哪种策略。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..events import EV_LOG, EV_TEST, EventBus
from ..languages import Language, language_from_filename, resolve_language
from ..llm import LLMClient
from ..sandbox import Sandbox
from ..sandbox.blackbox import parse_cases, run_cases
from .code_agent import extract_code

PYTEST_SYSTEM_PROMPT = """你是一名测试工程师。用户会给你一个程序文件 {filename} 和它的功能说明。

请编写一份 pytest 测试文件 {testfile}：
1. 用 subprocess 运行 {filename} 并断言输出（不假设程序内部结构，避免 import 失败）：
   import subprocess, sys, pathlib

   def run(*args):
       return subprocess.run([sys.executable, "{filename}", *args],
                             capture_output=True, text=True,
                             cwd=pathlib.Path(__file__).parent)

2. 覆盖 3-6 个用例：正常输入、边界输入（0 / 空 / 负数 / 大数）。
3. 断言要具体（检查输出包含期望的数值或文本），不要太宽松（不要只 assert 退出码）。
4. 只输出 ```python 包裹的完整 {testfile}，不要任何解释。"""

BLACKBOX_SYSTEM_PROMPT = """你是一名测试工程师。用户会给你一个 {display} 程序文件 `{filename}` 和它的功能说明。

请设计黑盒测试用例：只通过「命令行参数 + 标准输入」调用这个程序并断言它的标准输出，
不要假设程序内部结构。不要编写 {display} 代码，只输出 JSON。

输出格式（必须是合法 JSON，用 ```json 代码块包裹）：
{{
  "cases": [
    {{"name": "正常输入", "args": ["5"], "stdin": "",
      "expect_contains": ["10"], "expect_not_contains": [], "expect_exit_code": 0}}
  ]
}}

要求：
1. 覆盖 3-6 个用例：正常输入 + 边界输入（0 / 1 / 空 / 负数 / 较大值）。
2. expect_contains 里放「实际输出中必然出现的片段」（具体数字或关键字），不要留空数组。
3. expect_not_contains 用来排除容易算错的错误答案：例如正确结果是 10 时把 "9" 放进去，
   可以把「差一错误」暴露出来。它按「独立的值」匹配——写 "9" 只在输出里出现独立的 9 时算违规
   （19、29 里的那个 9 不算），所以可以放心使用单个数字。
4. 程序不带参数运行也必须正常结束（有默认值），这本身可以作为一个用例。
5. args 里每个元素都是字符串；不需要参数时写 []。"""


class TestAgent:
    __test__ = False  # 避免 pytest 把该类误当测试类收集

    def __init__(
        self,
        llm: LLMClient,
        sandbox: Sandbox | None = None,
        bus: EventBus | None = None,
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
        self.language: Language = (
            language if isinstance(language, Language) else resolve_language(language)
        )
        # 最近一次生成的测试状态，供 rerun() 复用（复测不重新调用 LLM）
        self._last: dict[str, Any] = {}

    # ---- 语言定位 ----
    def _lang(self, language: str | Language | None, filename: str) -> Language:
        if isinstance(language, Language):
            return language
        if language is not None:
            return resolve_language(language)
        return language_from_filename(filename, default=self.language.key)

    # ---- 对外接口 ----
    def generate_tests(
        self,
        task: str,
        code: str,
        filename: str = "main.py",
        language: str | Language | None = None,
    ) -> dict[str, Any]:
        """生成测试并运行，返回结果字典。

        测试失败不抛异常——由调用方决定是警告还是终止。
        """
        lang = self._lang(language, filename)
        self._last = {"language": lang, "filename": filename, "strategy": lang.test_strategy}
        if lang.test_strategy == "pytest":
            return self._generate_pytest(task, code, filename, lang)
        return self._generate_blackbox(task, code, filename, lang)

    def rerun(self) -> dict[str, Any]:
        """不重新生成测试，直接重跑沙箱里已有的测试。

        用于 Test→Debug 协作回环：Debug 修复代码后，用同一份测试验收。
        """
        lang: Language = self._last.get("language") or self.language
        filename = self._last.get("filename") or lang.entry
        return self._execute(None, filename, lang)

    # ---- pytest 策略（Python）----
    def _generate_pytest(self, task: str, code: str, filename: str, lang: Language) -> dict[str, Any]:
        testfile = f"test_{Path(filename).stem}.py"
        system = PYTEST_SYSTEM_PROMPT.format(filename=filename, testfile=testfile)
        user_prompt = f"""程序功能说明：
{task}

程序文件 `{filename}` 内容：
```{lang.fence}
{code}
```

请生成 {testfile}。"""
        self.bus.emit(EV_LOG, agent="TestAgent", message="TestAgent 正在生成 pytest 测试用例")
        raw = self.llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ]
        )
        tests = extract_code(raw, lang)
        if not tests.strip():
            return self._empty_result("未能生成测试代码")
        return self._execute(tests, filename, lang)

    # ---- 黑盒策略（C/C++/Go/Java 等）----
    def _generate_blackbox(self, task: str, code: str, filename: str, lang: Language) -> dict[str, Any]:
        system = BLACKBOX_SYSTEM_PROMPT.format(display=lang.display, filename=filename)
        user_prompt = f"""程序功能说明：
{task}

程序文件 `{filename}` 的源码（{lang.display}）：
```{lang.fence}
{code}
```

请只输出测试用例 JSON。"""
        self.bus.emit(
            EV_LOG,
            agent="TestAgent",
            message=f"TestAgent 正在为 {lang.display} 程序设计黑盒测试用例",
        )
        raw = self.llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ]
        )
        cases = parse_cases(raw)
        if not cases:
            return self._empty_result("未能生成有效的测试用例 JSON")
        # 归一化成干净的 JSON 存盘，复测时直接读回
        spec = json.dumps(
            {"cases": [asdict(c) for c in cases]}, ensure_ascii=False, indent=2
        )
        return self._execute(spec, filename, lang)

    # ---- 运行测试（两条策略的分派点）----
    def _execute(self, tests: str | None, filename: str, lang: Language) -> dict[str, Any]:
        if lang.test_strategy == "pytest":
            return self._run_pytest(tests, filename, lang)
        return self._run_blackbox(tests, filename, lang)

    def _run_pytest(self, tests: str | None, filename: str, lang: Language) -> dict[str, Any]:
        testfile = f"test_{Path(filename).stem}.py"
        if tests is not None:
            self.sandbox.write_file(testfile, tests)
        if not (self.sandbox.workspace / testfile).exists():
            return self._empty_result(f"沙箱中没有 {testfile}，无法运行测试")

        run_res = self.sandbox.run_cmd(
            [self.sandbox.python, "-m", "pytest", testfile, "-q"],
            cwd=self.sandbox.workspace,
        )
        passed = run_res.returncode == 0 and not run_res.timed_out and not run_res.error
        out = (run_res.stdout or "").strip()
        # 最后一行通常是 pytest 汇总（如 "3 passed in 0.12s"）
        summary = (
            out.splitlines()[-1]
            if out
            else (run_res.stderr or "").strip().splitlines()[-1]
            if (run_res.stderr or "").strip()
            else "(无输出)"
        )
        return self._emit_result(
            strategy="pytest",
            tests_code=tests or "",
            passed=passed,
            summary=summary,
            output=out,
            returncode=run_res.returncode,
            display=lang.display,
        )

    def _run_blackbox(self, tests: str | None, filename: str, lang: Language) -> dict[str, Any]:
        spec_path = self.sandbox.workspace / "test_spec.json"
        if tests is not None:
            self.sandbox.write_file("test_spec.json", tests)
        elif not spec_path.exists():
            return self._empty_result("沙箱中没有 test_spec.json，无法运行测试")
        else:
            tests = spec_path.read_text(encoding="utf-8")

        cases = parse_cases(tests or "")
        if not cases:
            return self._empty_result("未能解析出任何测试用例")

        info = run_cases(self.sandbox, filename, cases)
        return self._emit_result(
            strategy="blackbox",
            tests_code=tests or "",
            passed=bool(info["passed"]),
            summary=info["summary"],
            output=info["output"],
            returncode=info["returncode"],
            display=lang.display,
            extra={"cases_total": info["cases_total"], "cases_passed": info["cases_passed"]},
        )

    # ---- 结果封装 ----
    def _emit_result(
        self,
        strategy: str,
        tests_code: str,
        passed: bool,
        summary: str,
        output: str,
        returncode: int,
        display: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.bus.emit(
            EV_TEST,
            agent="TestAgent",
            message=f"TestAgent（{display}/{strategy}）：{'测试全部通过' if passed else '测试未通过'}",
            data={
                "passed": passed,
                "summary": summary,
                "output": output[:2000],
                "tests_code": tests_code,
                "strategy": strategy,
                **(extra or {}),
            },
        )
        return {
            "tests_code": tests_code,
            "passed": passed,
            "summary": summary,
            "output": output[:2000],
            "returncode": returncode,
            "strategy": strategy,
            **(extra or {}),
        }

    def _empty_result(self, reason: str) -> dict[str, Any]:
        self.bus.emit(
            EV_TEST,
            agent="TestAgent",
            message=f"TestAgent：{reason}",
            data={"passed": False, "error": reason},
        )
        return {
            "tests_code": "",
            "passed": False,
            "summary": reason,
            "output": "",
            "returncode": -1,
        }
