"""沙箱：在隔离的临时目录中执行 Python 代码，带超时保护。

用途：让 Debug Agent 安全地「运行」LLM 生成的代码并拿到输出/报错。
用 subprocess + tempfile 隔离，不执行未知依赖安装，超时强制终止。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_s: float = 0.0
    error: str = ""  # 启动类错误（找不到解释器、IO 异常等）

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.error

    @property
    def summary(self) -> str:
        """给 LLM / 用户看的一句话结果摘要。"""
        if self.error:
            return f"执行失败：{self.error}"
        if self.timed_out:
            return f"执行超时（> 规定时限），可能陷入了死循环。"
        if self.returncode != 0:
            tail = (self.stderr or self.stdout).strip().splitlines()
            tail = "\n".join(tail[-10:])
            return f"执行出错，退出码 {self.returncode}，报错如下：\n{tail}"
        tail = (self.stdout or "").strip()
        if not tail:
            tail = "(无输出)"
        return f"执行成功，输出：\n{tail}"


class Sandbox:
    """在一个临时工作目录里跑代码。目录可复用（多次运行共享 workspace）。"""

    def __init__(
        self,
        workspace: str | None = None,
        timeout: float | None = None,
        python: str | None = None,
    ) -> None:
        from ..config import settings

        self.timeout = timeout if timeout is not None else settings.sandbox_timeout
        # 沙箱内默认使用当前解释器（python -m pytest 也会用同一环境）
        self.python = python or sys.executable
        self._owns_workspace = workspace is None
        if workspace is None:
            workspace = tempfile.mkdtemp(prefix="codegen-sandbox-")
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def write_file(self, filename: str, content: str) -> Path:
        """把文件写入沙箱 workspace，返回绝对路径。"""
        path = self.workspace / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_file(self, filename: str) -> str:
        path = self.workspace / filename
        return path.read_text(encoding="utf-8")

    def list_files(self) -> list[str]:
        if not self.workspace.exists():
            return []
        return sorted(
            str(p.relative_to(self.workspace)).replace("\\", "/")
            for p in self.workspace.rglob("*")
            if p.is_file()
        )

    def run_file(self, filename: str, args: list[str] | None = None) -> RunResult:
        """运行 workspace 下的某个脚本文件（显式调用解释器，跨平台）。"""
        path = self.workspace / filename
        if not path.exists():
            return RunResult(error=f"文件不存在：{filename}")
        return self.run_cmd([self.python, str(path), *(args or [])], cwd=self.workspace)

    def run_code(self, code: str, filename: str = "main.py") -> RunResult:
        """把代码写进文件并运行（一条龙）。"""
        self.write_file(filename, code)
        return self.run_file(filename)

    def run_cmd(self, cmd: list[str], cwd: Path | None = None) -> RunResult:
        """通用命令执行。"""
        import time

        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(cwd) if cwd else None,
                encoding="utf-8",
                errors="replace",
            )
            return RunResult(
                returncode=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_s=round(time.time() - start, 2),
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                returncode=-1,
                stdout="",
                stderr="",
                timed_out=True,
                duration_s=round(time.time() - start, 2),
            )
        except FileNotFoundError as e:
            return RunResult(
                returncode=-1,
                error=f"找不到可执行文件：{e}",
                duration_s=round(time.time() - start, 2),
            )
        except Exception as e:  # noqa: BLE001
            return RunResult(
                returncode=-1,
                error=f"执行异常：{e}",
                duration_s=round(time.time() - start, 2),
            )

    def cleanup(self) -> None:
        """删除沙箱临时目录（仅当目录是本沙箱创建时才删）。"""
        if self._owns_workspace and self.workspace.exists():
            import shutil

            shutil.rmtree(self.workspace, ignore_errors=True)

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.cleanup()
