"""Agent Harness：多智能体的统一运行基础设施层。

对应任务书 CS 项目的「Harness 架构」——把智能体运行所需的公共设施
（沙箱隔离执行、事件总线、工具注册、配置）收口到一个对象里，Agent 不再
各自创建资源，而是统一从 Harness 获取：

    harness.sandbox   → 隔离执行环境（临时目录、编译、超时、UTF-8 输出）
    harness.bus       → 事件流（CLI / SSE / Streamlit 实时渲染）
    harness.tools     → 工具注册表（run_file / read_file / write_file / list_files）
    harness.config    → 全局配置
    harness.language  → 本次任务的目标语言档案（Python / C / C++ / Go / Java）

Coordinator 持有一个 Harness 并分发给 Code / Debug / Doc / Test Agent。
新增 Agent、新工具或新语言时，只需在这里扩展，不动其它模块。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .config import settings
from .events import EventBus, EventKind
from .languages import Language, resolve_language, toolchain_status
from .sandbox import RunResult, Sandbox


class ToolRegistry:
    """工具注册表：把沙箱能力包装成可供 Agent 调用的工具。"""

    def __init__(self, sandbox: Sandbox) -> None:
        self.sandbox = sandbox
        self._tools: dict[str, dict[str, Any]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        # run_file 支持全部语言（按文件后缀自动编译/运行）
        self.register(
            "run_file",
            lambda filename="main.py", args=None: self.sandbox.run_file(filename, args),
            "在沙箱中编译并运行一个源文件（按后缀自动识别语言），返回运行结果",
        )
        # run_python 保留为 run_file 的别名，兼容既有调用
        self.register(
            "run_python",
            lambda filename="main.py", args=None: self.sandbox.run_file(filename, args),
            "在沙箱中运行一个 Python 文件，返回运行结果",
        )
        self.register(
            "build_file",
            lambda filename: self.sandbox.build_file(filename),
            "只编译不运行（编译型语言），返回编译结果",
        )
        self.register(
            "read_file",
            lambda filename: self.sandbox.read_file(filename),
            "读取沙箱工作目录下的文件内容",
        )
        self.register(
            "write_file",
            lambda filename, content: self.sandbox.write_file(filename, content).name,
            "把内容写入沙箱工作目录下的文件",
        )
        self.register(
            "list_files",
            lambda: self.sandbox.list_files(),
            "列出沙箱工作目录下的所有文件",
        )
        self.register(
            "list_languages",
            lambda: toolchain_status(),
            "列出支持的编程语言及本机工具链可用性",
        )

    def register(self, name: str, fn: Callable[..., Any], description: str = "") -> None:
        """注册一个工具：name 为工具名，fn 为可调用对象，description 用于展示。"""
        self._tools[name] = {"fn": fn, "description": description}

    def list_tools(self) -> list[dict[str, str]]:
        """列出所有已注册工具（供 UI / 文档展示）。"""
        return [
            {"name": n, "description": t["description"]}
            for n, t in sorted(self._tools.items())
        ]

    def call(self, name: str, **kwargs: Any) -> Any:
        """调用工具；未注册的工具抛 KeyError。"""
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"未知工具：{name}，可用：{[n for n in self._tools]}")
        return tool["fn"](**kwargs)


class Harness:
    """统一基础设施：沙箱 + 事件总线 + 工具注册表 + 配置 + 目标语言。"""

    def __init__(
        self,
        workspace: str | None = None,
        timeout: float | None = None,
        bus: EventBus | None = None,
        python: str | None = None,
        language: str | Language | None = None,
    ) -> None:
        self.config = settings
        self.bus = bus or EventBus()
        self.language: Language = (
            language if isinstance(language, Language) else resolve_language(language)
        )
        self.sandbox = Sandbox(
            workspace=workspace, timeout=timeout, python=python, language=self.language.key
        )
        self.tools = ToolRegistry(self.sandbox)

    # ---- 事件转发 ----
    def emit(
        self,
        kind: EventKind,
        agent: str = "",
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        self.bus.emit(kind, agent=agent, message=message, data=data)

    # ---- 沙箱转发 ----
    def run_file(
        self, filename: str, args: list[str] | None = None, stdin_text: str | None = None
    ) -> RunResult:
        return self.sandbox.run_file(filename, args, stdin_text)

    def run_cmd(self, cmd: list[str], cwd: Path | None = None) -> RunResult:
        return self.sandbox.run_cmd(cmd, cwd)

    def write_file(self, filename: str, content: str) -> Path:
        return self.sandbox.write_file(filename, content)

    def read_file(self, filename: str) -> str:
        return self.sandbox.read_file(filename)

    def list_files(self) -> list[str]:
        return self.sandbox.list_files()

    @property
    def workspace(self) -> Path:
        return self.sandbox.workspace

    def cleanup(self) -> None:
        self.sandbox.cleanup()
