"""Coordinator：编排 Code / Debug / Doc / Test 四个 Agent 完成一次代码生成任务。

语言是「一次任务」的属性：Coordinator 持有目标语言档案，并把它透传给
沙箱（决定怎么编译/运行）、Code/Debug Agent（提示词与报错解析）、
Test Agent（用 pytest 还是黑盒用例）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..events import EventBus, EV_DONE, EV_FAIL, EV_LOG, EV_MSG, EV_START
from ..harness import Harness
from ..languages import Language, language_from_filename, resolve_language
from ..llm import LLMClient
from .code_agent import CodeAgent
from .debug_agent import DebugAgent
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
    test_rounds_used: int = 0
    language: str = "python"
    language_display: str = "Python"
    filename: str = "main.py"

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
            "test_rounds_used": self.test_rounds_used,
            "language": self.language,
            "language_display": self.language_display,
            "filename": self.filename,
        }


class Coordinator:
    """总控：任务 → Code → [Debug 循环] → Doc → [Test 循环] → 结果。"""

    def __init__(
        self,
        llm: LLMClient,
        bus: EventBus | None = None,
        workspace: str | None = None,
        max_rounds: int | None = None,
        sandbox_timeout: float | None = None,
        keep_workspace: bool = False,
        enable_tests: bool | None = None,
        max_test_rounds: int | None = None,
        language: str | Language | None = None,
    ) -> None:
        self.llm = llm
        self.bus = bus or EventBus()
        self.max_rounds = max_rounds if max_rounds is not None else settings.max_fix_rounds
        self.max_test_rounds = (
            max_test_rounds if max_test_rounds is not None else settings.max_test_rounds
        )
        self.language: Language = (
            language if isinstance(language, Language) else resolve_language(language)
        )
        # Harness：统一基础设施（沙箱 + 事件总线 + 工具 + 语言），分发给各 Agent
        self.harness = Harness(
            workspace=workspace,
            timeout=sandbox_timeout,
            bus=self.bus,
            language=self.language,
        )
        self.sandbox = self.harness.sandbox
        self.keep_workspace = keep_workspace
        self.enable_tests = enable_tests if enable_tests is not None else settings.auto_tests

        self.code_agent = CodeAgent(llm, harness=self.harness)
        self.debug_agent = DebugAgent(llm, harness=self.harness, max_rounds=self.max_rounds)
        self.doc_agent = DocAgent(llm, harness=self.harness)
        self.test_agent = TestAgent(llm, harness=self.harness) if self.enable_tests else None

    def _resolve(self, language: str | Language | None, filename: str | None) -> Language:
        """确定本次任务的语言：显式指定 > 文件后缀推断 > Coordinator 默认。"""
        if isinstance(language, Language):
            return language
        if language is not None:
            return resolve_language(language)
        if filename:
            return language_from_filename(filename, default=self.language.key)
        return self.language

    def run(
        self,
        task: str,
        filename: str | None = None,
        language: str | Language | None = None,
    ) -> PipelineResult:
        """执行完整流水线，返回结果。"""
        lang = self._resolve(language, filename)
        filename = filename or lang.entry
        start = time.time()
        self.bus.emit(
            EV_START,
            agent="Coordinator",
            message=f"任务开始（{lang.display}）：{task}",
            data={"language": lang.key, "language_display": lang.display, "filename": filename},
        )

        # 0. 语言工具链自检：本机没装编译器时，早失败并给出可操作的提示
        missing = lang.missing_tools()
        if missing:
            return self._fail(
                task,
                start,
                lang,
                filename,
                f"本机缺少 {', '.join(missing)}，无法编译/运行 {lang.display} 代码。"
                f"请先安装对应工具链，或换一种语言（可选：python/c/cpp/go/java）。",
            )

        # 1. Code Agent 生成初始代码
        code = self.code_agent.generate(task, language=lang)
        if not code.strip():
            return self._fail(task, start, lang, filename, "Code Agent 未生成有效代码")

        self.sandbox.write_file(filename, code)

        # 2. Debug 循环：编译+运行 → 失败则修复（带历史记忆），至多 max_rounds 轮
        result = None
        rounds = 0
        history: list[dict[str, Any]] = []  # 前几轮的失败诊断，供 DebugAgent 参考
        while rounds < self.max_rounds:
            rounds += 1
            result = self.sandbox.run_file(filename)
            self.bus.emit(
                EV_LOG,
                agent="DebugAgent",
                message=(
                    f"第 {rounds} 次运行（exit={result.returncode}, 超时={result.timed_out}）"
                ),
                data={
                    "round": rounds,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "timed_out": result.timed_out,
                    "stage": result.stage,
                    "language": lang.key,
                },
            )
            if result.ok:
                break
            # 运行失败 → 修复（带上历史，避免重复踩坑）
            code = self.debug_agent.fix(task, code, result, filename, history, language=lang)
            diag = lang.parse_error(result.stderr, result.stage)
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
                language=lang.key,
                language_display=lang.display,
                filename=filename,
            )

        # 3. Doc Agent 生成 README
        readme = self.doc_agent.write_readme(task, code, result, filename, language=lang)
        self.sandbox.write_file("README.md", readme)

        # 4. Test Agent（可选）：自动生成测试并在沙箱中运行。
        #    测试失败时通过协作消息反馈给 Debug Agent 修复并复测（Test→Debug 回环）。
        tests_passed: bool | None = None
        tests_summary = ""
        test_rounds_used = 0
        if self.test_agent is not None:
            test_info = self.test_agent.generate_tests(task, code, filename, language=lang)
            test_rounds_used = 1
            tests_passed = test_info.get("passed")
            tests_summary = test_info.get("summary") or ""
            # 只有真的生成了测试，才允许进入 Test→Debug 回环；
            # 测试为空（LLM 未生成）时没有验收标准，无从修复。
            can_loop = bool(test_info.get("tests_code"))
            test_history: list[dict[str, Any]] = []
            while can_loop and not tests_passed and test_rounds_used < self.max_test_rounds:
                test_rounds_used += 1
                # 协作消息：Test Agent 把失败反馈给 Debug Agent
                self.bus.emit(
                    EV_MSG,
                    agent="TestAgent",
                    message=f"TestAgent → DebugAgent：测试失败，请修复（协作回环第 {test_rounds_used} 轮）",
                    data={
                        "target": "DebugAgent",
                        "output": (test_info.get("output") or "")[:2000],
                    },
                )
                # Debug Agent 按测试失败输出修复代码
                code = self.debug_agent.fix_tests(
                    task,
                    code,
                    test_info.get("output") or test_info.get("summary") or "",
                    filename,
                    test_history,
                    language=lang,
                )
                test_history.append({"round": test_rounds_used, "summary": tests_summary})
                # 修复后先确认程序仍能运行
                result = self.sandbox.run_file(filename)
                if not result.ok:
                    break
                # 复测：复用同一份测试验收
                test_info = self.test_agent.rerun()
                tests_passed = test_info.get("passed")
                tests_summary = test_info.get("summary") or ""

        files = self.sandbox.list_files()
        if not self.keep_workspace:
            self.sandbox.cleanup()

        self.bus.emit(
            EV_DONE,
            agent="Coordinator",
            message=f"任务完成（{lang.display}），共 {rounds} 轮运行通过",
            data={
                "files": files,
                "duration_s": round(time.time() - start, 2),
                "tests_passed": tests_passed,
                "tests_summary": tests_summary,
                "language": lang.key,
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
            test_rounds_used=test_rounds_used,
            language=lang.key,
            language_display=lang.display,
            filename=filename,
        )

    def _fail(self, task: str, start: float, lang: Language, filename: str, err: str) -> PipelineResult:
        self.bus.emit(EV_FAIL, agent="Coordinator", message=err)
        return PipelineResult(
            success=False,
            task=task,
            workspace=str(self.sandbox.workspace),
            files=self.sandbox.list_files(),
            duration_s=time.time() - start,
            error=err,
            language=lang.key,
            language_display=lang.display,
            filename=filename,
        )
