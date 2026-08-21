"""Test Agent：在程序运行通过后，自动生成 pytest 测试并在沙箱中运行验证。"""
from __future__ import annotations

from typing import Any

from ..events import EventBus, EV_TEST, EV_LOG
from ..llm import LLMClient
from ..sandbox import Sandbox
from .code_agent import extract_code

TEST_SYSTEM_PROMPT = """你是一名测试工程师。用户会给你一个程序文件 main.py 和它的功能说明。

请编写一份 pytest 测试文件 test_main.py：
1. 用 subprocess 运行 main.py 并断言输出（不假设程序内部结构，避免 import 失败）：
   import subprocess, sys, pathlib

   def run(*args):
       return subprocess.run([sys.executable, "main.py", *args],
                             capture_output=True, text=True,
                             cwd=pathlib.Path(__file__).parent)

2. 覆盖 3-6 个用例：正常输入、边界输入（0 / 空 / 负数 / 大数）。
3. 断言要具体（检查输出包含期望的数值或文本），不要太宽松（不要只 assert 退出码）。
4. 只输出 ```python 包裹的完整 test_main.py，不要任何解释。"""


class TestAgent:
    __test__ = False  # 避免 pytest 把该类误当测试类收集

    def __init__(self, llm: LLMClient, sandbox: Sandbox, bus: EventBus | None = None) -> None:
        self.llm = llm
        self.sandbox = sandbox
        self.bus = bus or EventBus()

    def generate_tests(
        self,
        task: str,
        code: str,
        filename: str = "main.py",
    ) -> dict[str, Any]:
        """生成测试文件并在沙箱中运行，返回结果字典。

        返回 {"tests_code", "passed", "summary", "output", "returncode"}。
        测试失败不抛异常——由调用方决定是警告还是终止。
        """
        user_prompt = f"""程序功能说明：
{task}

程序文件 `{filename}` 内容：
```python
{code}
```

请生成 test_main.py。"""
        self.bus.emit(EV_LOG, agent="TestAgent", message="TestAgent 正在生成测试用例")
        raw = self.llm.chat(
            [
                {"role": "system", "content": TEST_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
        tests = extract_code(raw)
        if not tests.strip():
            self.bus.emit(
                EV_TEST,
                agent="TestAgent",
                message="TestAgent 未能生成测试代码",
                data={"passed": False, "error": "空测试代码"},
            )
            return {
                "tests_code": "",
                "passed": False,
                "summary": "未能生成测试代码",
                "output": "",
                "returncode": -1,
            }

        self.sandbox.write_file("test_main.py", tests)
        run_res = self.sandbox.run_cmd(
            [self.sandbox.python, "-m", "pytest", "test_main.py", "-q"],
            cwd=self.sandbox.workspace,
        )
        passed = run_res.returncode == 0 and not run_res.timed_out and not run_res.error
        out = (run_res.stdout or "").strip()
        # 最后一行通常是 pytest 汇总（如 "3 passed in 0.12s"）
        summary = out.splitlines()[-1] if out else (run_res.stderr or "").strip().splitlines()[-1] if (run_res.stderr or "").strip() else "(无输出)"
        self.bus.emit(
            EV_TEST,
            agent="TestAgent",
            message=f"TestAgent：{'测试全部通过' if passed else '测试未通过'}",
            data={
                "passed": passed,
                "summary": summary,
                "output": out[:2000],
                "tests_code": tests,
            },
        )
        return {
            "tests_code": tests,
            "passed": passed,
            "summary": summary,
            "output": out[:2000],
            "returncode": run_res.returncode,
        }
