"""Coordinator：编排 Code / Debug / Doc 三个 Agent 完成一次代码生成任务。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..events import EventBus, EV_DONE, EV_FAIL, EV_LOG, EV_START
from ..llm import LLMClient
from ..sandbox import Sandbox
from .code_agent import CodeAgent
from .debug_agent import DebugAgent, parse_traceback
from .doc_agent import DocAgent
from .test_agent import TestAgent


@dataclass
class PipelineResult:
    success: bool
    task: str
    workspace: str
    files: list[str] = field(default_factory=list)
    main_code: str = ""
    readme: str = ""
    rounds_used: int = 0
    max_rounds: int = 0
    duration_s: float = 0.0
    error: str = ""
    final_output: str = ""
    tests_passed: bool | None = None
    tests_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "task": self.task,
            "workspace": self.workspace,
            "files": self.files,
            "main_code": self.main_code,
            "readme": self.readme,
            "rounds_used": self.rounds_used,
            "max_rounds": self.max_rounds,
            "duration_s": round(self.duration_s, 2),
            "error": self.error,
            "final_output": self.final_output,
            "tests_passed": self.tests_passed,
            "tests_summary": self.tests_summary,
        }


class Coordinator:
    """总控：任务 → Code → [Debug 循环] → Doc → 结果。"""

    def __init__(
        self,
        llm: LLMClient,
        bus: EventBus | None = None,
        workspace: str | None = None,
        max_rounds: int | None = None,
        sandbox_timeout: float | None = None,
        keep_workspace: bool = False,
        enable_tests: bool | None = None,
    ) -> None:
        self.llm = llm
        self.bus = bus or EventBus()
        self.max_rounds = max_rounds if max_rounds is not None else settings.max_fix_rounds
        self.sandbox = Sandbox(workspace=workspace, timeout=sandbox_timeout)
        self.keep_workspace = keep_workspace
        self.enable_tests = enable_tests if enable_tests is not None else settings.auto_tests

        self.code_agent = CodeAgent(llm, self.bus)
        self.debug_agent = DebugAgent(llm, self.sandbox, self.bus, self.max_rounds)
        self.doc_agent = DocAgent(llm, self.bus)
        self.test_agent = TestAgent(llm, self.sandbox, self.bus) if self.enable_tests else None

    def run(self, task: str, filename: str = "main.py") -> PipelineResult:
        """执行完整流水线，返回结果。"""
        start = time.time()
        self.bus.emit(EV_START, agent="Coordinator", message=f"任务开始：{task}")

        # 1. Code Agent 生成初始代码
        code = self.code_agent.generate(task)
        if not code.strip():
            return self._fail(task, start, "Code Agent 未生成有效代码")

        self.sandbox.write_file(filename, code)

        # 2. Debug 循环：运行 → 失败则修复（带历史记忆），至多 max_rounds 轮
        result = None
        rounds = 0
        history: list[dict[str, Any]] = []  # 前几轮的失败诊断，供 DebugAgent 参考
        while rounds < self.max_rounds:
            rounds += 1
            result = self.sandbox.run_file(filename)
            self.bus.emit(
                EV_LOG,
                agent="DebugAgent",
                message=f"第 {rounds} 次运行（exit={result.returncode}, 超时={result.timed_out}）",
                data={
                    "round": rounds,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "timed_out": result.timed_out,
                },
            )
            if result.ok:
                break
            # 运行失败 → 修复（带上历史，避免重复踩坑）
            code = self.debug_agent.fix(task, code, result, filename, history)
            diag = parse_traceback(result.stderr)
            history.append(
                {
                    "round": rounds,
                    "error_type": diag["error_type"] or "",
                    "message": (diag["message"] or (result.stderr or result.stdout))[:200],
                }
            )

        if result is None or not result.ok:
            err = f"经过 {rounds} 轮仍未能成功运行"
            self.bus.emit(EV_FAIL, agent="Coordinator", message=err, data={"rounds": rounds})
            return PipelineResult(
                success=False,
                task=task,
                workspace=str(self.sandbox.workspace),
                files=self.sandbox.list_files(),
                main_code=code,
                rounds_used=rounds,
                max_rounds=self.max_rounds,
                duration_s=time.time() - start,
                error=err,
            )

        # 3. Doc Agent 生成 README
        readme = self.doc_agent.write_readme(task, code, result, filename)
        self.sandbox.write_file("README.md", readme)

        # 4. Test Agent（可选）：自动生成测试并在沙箱中运行
        tests_passed: bool | None = None
        tests_summary = ""
        if self.test_agent is not None:
            test_info = self.test_agent.generate_tests(task, code, filename)
            tests_passed = test_info.get("passed")
            tests_summary = test_info.get("summary") or ""

        files = self.sandbox.list_files()
        if not self.keep_workspace:
            self.sandbox.cleanup()

        self.bus.emit(
            EV_DONE,
            agent="Coordinator",
            message=f"任务完成，共 {rounds} 轮运行通过",
            data={
                "files": files,
                "duration_s": round(time.time() - start, 2),
                "tests_passed": tests_passed,
                "tests_summary": tests_summary,
            },
        )
        return PipelineResult(
            success=True,
            task=task,
            workspace=str(self.sandbox.workspace),
            files=files,
            main_code=code,
            readme=readme,
            rounds_used=rounds,
            max_rounds=self.max_rounds,
            duration_s=time.time() - start,
            final_output=result.stdout or "",
            tests_passed=tests_passed,
            tests_summary=tests_summary,
        )

    def _fail(self, task: str, start: float, err: str) -> PipelineResult:
        self.bus.emit(EV_FAIL, agent="Coordinator", message=err)
        return PipelineResult(
            success=False,
            task=task,
            workspace=str(self.sandbox.workspace),
            files=self.sandbox.list_files(),
            duration_s=time.time() - start,
            error=err,
        )
