"""沙箱：在隔离的临时目录中编译/执行代码，带超时保护。

用途：让 Debug Agent 安全地「运行」LLM 生成的代码并拿到输出/报错。
用 subprocess + tempfile 隔离，不执行未知依赖安装，超时强制终止。

多语言：编译/运行命令不硬编码在这里，而是查 app/languages.py 的语言档案
（按文件后缀自动分派）。解释型语言直接跑，编译型语言先编译再运行产物。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..languages import Language, language_from_filename, resolve_language


@dataclass
class RunResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_s: float = 0.0
    error: str = ""  # 启动类错误（找不到解释器/编译器、IO 异常等）
    stage: str = "run"  # build = 编译阶段，run = 运行阶段

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.error

    @property
    def summary(self) -> str:
        """给 LLM / 用户看的一句话结果摘要。"""
        if self.error:
            return f"执行失败：{self.error}"
        if self.timed_out:
            phase = "编译" if self.stage == "build" else "执行"
            return f"{phase}超时（> 规定时限），可能陷入了死循环。"
        if self.returncode != 0:
            phase = "编译" if self.stage == "build" else "执行"
            tail = (self.stderr or self.stdout).strip().splitlines()
            tail = "\n".join(tail[-10:])
            return f"{phase}出错，退出码 {self.returncode}，报错如下：\n{tail}"
        tail = (self.stdout or "").strip()
        if not tail:
            tail = "(无输出)"
        return f"执行成功，输出：\n{tail}"


class Sandbox:
    """在一个临时工作目录里编译并运行代码。目录可复用（多次运行共享 workspace）。

    语言由文件名后缀决定：main.py → Python，main.c → C，main.cpp → C++，
    main.go → Go，Main.java → Java，未知后缀回退到默认语言。
    """

    def __init__(
        self,
        workspace: str | None = None,
        timeout: float | None = None,
        python: str | None = None,
        language: str | None = None,
    ) -> None:
        from ..config import settings

        self.timeout = timeout if timeout is not None else settings.sandbox_timeout
        # 沙箱内默认使用当前解释器（python -m pytest 也会用同一环境）
        self.python = python or sys.executable
        # 未知后缀时的兜底语言
        self.language: Language = resolve_language(language)
        self._owns_workspace = workspace is None
        if workspace is None:
            workspace = tempfile.mkdtemp(prefix="codegen-sandbox-")
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        # 编译缓存：源码内容 hash → 是否编译成功，避免同一份代码反复编译
        self._build_sig: dict[str, str] = {}
        self._build_ok: dict[str, bool] = {}

    # ---- 文件操作 ----
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

    # ---- 语言分派 ----
    def language_for(self, filename: str) -> Language:
        """按文件后缀取语言档案，认不出则用沙箱的默认语言。"""
        return language_from_filename(filename, default=self.language.key)

    # ---- 编译 ----
    def build_file(self, filename: str, force: bool = False) -> RunResult | None:
        """编译源码（仅编译型语言）。无需编译时返回 None。

        同一份源码只编译一次（按内容 hash 判断），编译失败不缓存。
        """
        lang = self.language_for(filename)
        if not lang.needs_build:
            return None
        path = self.workspace / filename
        if not path.exists():
            return RunResult(error=f"文件不存在：{filename}", stage="build")

        missing = lang.missing_tools()
        if missing:
            return RunResult(
                error=(
                    f"本机缺少 {', '.join(missing)}，无法编译 {lang.display} 代码。"
                    f"请安装后重试，或改用其它语言。"
                ),
                stage="build",
            )

        sig = hashlib.sha1(path.read_bytes()).hexdigest()
        artifact = lang.artifact_path(self.workspace)
        if (
            not force
            and self._build_sig.get(filename) == sig
            and self._build_ok.get(filename)
            and (artifact is None or artifact.exists())
        ):
            return RunResult(
                returncode=0,
                stdout="(源码未变，复用上次编译产物)",
                stage="build",
            )

        cmd = lang.build_cmd(self.workspace, filename)
        assert cmd is not None
        self._build_sig[filename] = sig
        result = self.run_cmd(cmd, cwd=self.workspace, stage="build")
        self._build_ok[filename] = result.ok
        return result

    # ---- 运行 ----
    def run_file(
        self,
        filename: str,
        args: list[str] | None = None,
        stdin_text: str | None = None,
    ) -> RunResult:
        """编译（需要时）并运行 workspace 下的一个源文件。"""
        path = self.workspace / filename
        if not path.exists():
            return RunResult(error=f"文件不存在：{filename}")
        lang = self.language_for(filename)
        if lang.needs_build:
            build = self.build_file(filename)
            if build is not None and not build.ok:
                return build  # 编译失败：把编译器输出直接交给 Debug Agent
        return self.exec_file(filename, args, stdin_text)

    def exec_file(
        self,
        filename: str,
        args: list[str] | None = None,
        stdin_text: str | None = None,
    ) -> RunResult:
        """只运行，不编译（黑盒测试里先编译一次、再多次运行时用）。"""
        path = self.workspace / filename
        if not path.exists():
            return RunResult(error=f"文件不存在：{filename}")
        lang = self.language_for(filename)

        missing = lang.missing_tools()
        if missing:
            return RunResult(
                error=(
                    f"本机缺少 {', '.join(missing)}，无法运行 {lang.display} 代码。"
                    f"请安装后重试，或改用其它语言。"
                )
            )

        cmd = lang.exec_cmd(self.workspace, filename, args)
        # 保留 python= 参数的历史语义：可指定解释器
        if lang.key == "python" and cmd and cmd[0] == sys.executable:
            cmd[0] = self.python
        return self.run_cmd(cmd, cwd=self.workspace, stdin_text=stdin_text, stage="run")

    def run_code(self, code: str, filename: str = "main.py") -> RunResult:
        """把代码写进文件并运行（一条龙）。"""
        self.write_file(filename, code)
        return self.run_file(filename)

    def run_cmd(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        stdin_text: str | None = None,
        stage: str = "run",
    ) -> RunResult:
        """通用命令执行。"""
        import os
        import time

        start = time.time()
        # 强制子进程按 UTF-8 输出，避免 Windows 下中文被 GBK 输出导致乱码
        env = None
        try:
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
        except Exception:  # noqa: BLE001
            env = None
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(cwd) if cwd else None,
                encoding="utf-8",
                errors="replace",
                env=env,
                input=stdin_text if stdin_text is not None else "",
            )
            return RunResult(
                returncode=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_s=round(time.time() - start, 2),
                stage=stage,
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                returncode=-1,
                stdout="",
                stderr="",
                timed_out=True,
                duration_s=round(time.time() - start, 2),
                stage=stage,
            )
        except FileNotFoundError as e:
            return RunResult(
                returncode=-1,
                error=f"找不到可执行文件：{e}",
                duration_s=round(time.time() - start, 2),
                stage=stage,
            )
        except Exception as e:  # noqa: BLE001
            return RunResult(
                returncode=-1,
                error=f"执行异常：{e}",
                duration_s=round(time.time() - start, 2),
                stage=stage,
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
