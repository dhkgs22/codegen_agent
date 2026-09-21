"""语言档案注册表：把「一种语言相关的一切」收口到一处。

为什么要这一层：早期的沙箱和四个 Agent 把 Python 硬编码在各处——
文件名 main.py、`python 文件.py`、Python traceback 解析、pytest 测试、
提示词里的「资深 Python 工程师」。要支持多语言，如果每加一种语言就在
这些地方各打一个 if，很快会不可维护。

于是把「语言相关」的全部差异抽成 Language 档案：
    默认文件名 / 编译命令 / 运行命令 / 报错解析 / 提示词片段 / 测试策略

沙箱按文件后缀取档案，Agent 按语言取提示词与报错解析器。
新增一种语言 = 在 LANGUAGES 里加一条，其它模块一行都不用改。

支持：Python / C / C++ / Go / Java
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Windows 下编译产物带 .exe 后缀
EXE = ".exe" if os.name == "nt" else ""


# --------------------------------------------------------------------------
# 报错解析：各语言编译/运行报错的格式差异都在这里消化
# --------------------------------------------------------------------------
def parse_python_traceback(stderr: str) -> dict[str, Any]:
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


def _blank_diag() -> dict[str, Any]:
    return {"error_type": "", "message": "", "line_no": 0, "file": ""}


def _tail_diag(stderr: str, error_type: str) -> dict[str, Any]:
    """兜底：拿最后一行非空输出当错误消息。"""
    info = _blank_diag()
    lines = [l.strip() for l in (stderr or "").strip().splitlines() if l.strip()]
    if lines:
        info["error_type"] = error_type
        info["message"] = lines[-1][:200]
    return info


# gcc / g++:  main.c:5:10: error: expected ';' before '}' token
_GCC_RE = re.compile(
    r"^(?P<file>[^\s:]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
    r"(?P<kind>error|fatal error|warning):\s*(?P<msg>.+)$",
    re.MULTILINE,
)
# javac:  Main.java:5: error: ';' expected
_JAVAC_RE = re.compile(
    r"^(?P<file>[^\s:]+\.java):(?P<line>\d+):\s*(?P<kind>error|warning):\s*(?P<msg>.+)$",
    re.MULTILINE,
)
# go:  ./main.go:5:2: undefined: foo
_GO_RE = re.compile(
    r"^(?P<file>\.?/?[^\s:]*\.go):(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?P<msg>.+)$",
    re.MULTILINE,
)


def parse_compiler_error(stderr: str, pattern: re.Pattern[str], error_type: str = "CompileError") -> dict[str, Any]:
    """从编译器输出里取「第一条真正的错误」（warning 不算）。"""
    if not stderr:
        return _blank_diag()
    matches = [m for m in pattern.finditer(stderr) if m.groupdict().get("kind") != "warning"]
    if not matches:
        # 链接期错误没有 file:line 结构，取第一条含关键字的行，
        # 比取最后一行（往往是 collect2 / ld 的总结）有用得多。
        keywords = ("undefined reference", "cannot find", "no such file", "error")
        for line in (stderr or "").splitlines():
            low = line.lower()
            if any(k in low for k in keywords):
                info = _blank_diag()
                info["error_type"] = error_type
                info["message"] = line.strip()[:200]
                return info
        return _tail_diag(stderr, error_type)
    m = matches[0]
    return {
        "error_type": error_type,
        "message": m.group("msg").strip()[:200],
        "line_no": int(m.group("line")),
        "file": m.group("file"),
    }


def parse_python_error(stderr: str, stage: str = "") -> dict[str, Any]:
    diag = parse_python_traceback(stderr)
    if not diag["error_type"] and (stderr or "").strip():
        diag["error_type"] = "CompileError" if stage == "build" else "RuntimeError"
    return diag


# --------------------------------------------------------------------------
# 语言档案
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Language:
    """一种语言的完整档案：怎么编译、怎么跑、怎么写提示词、怎么测。"""

    key: str
    display: str
    ext: str
    fence: str  # markdown 代码块标记
    entry: str  # 默认入口文件名
    run_tpl: tuple[str, ...]  # 运行命令模板，占位符见 _fmt
    compile_tpl: tuple[str, ...] | None = None  # 编译命令模板（None = 解释型）
    tools: tuple[str, ...] = ()  # 依赖的外部可执行文件
    test_strategy: str = "blackbox"  # pytest | blackbox
    rules: str = ""  # CodeAgent 的语言特有要求（编号从 3 开始）
    debug_rules: str = ""  # DebugAgent 的语言特有要求
    error_parser: str = "compiler"  # python | gcc | javac | go | compiler
    error_type: str = "CompileError"

    # ---- 路径与命令 ----
    @property
    def needs_build(self) -> bool:
        return self.compile_tpl is not None

    @property
    def artifact_name(self) -> str:
        """编译产物文件名（相对 workspace）。解释型语言返回空串。"""
        if not self.needs_build:
            return ""
        if self.key == "java":
            return Path(self.entry).stem + ".class"
        return Path(self.entry).stem + EXE

    def artifact_path(self, workdir: Path) -> Path | None:
        name = self.artifact_name
        return (workdir / name) if name else None

    def _fmt(self, tpl: tuple[str, ...], workdir: Path, filename: str) -> list[str]:
        src = workdir / filename
        art = self.artifact_path(workdir)
        mapping = {
            "{src}": str(src),
            "{out}": str(art) if art else "",
            "{workdir}": str(workdir),
            "{stem}": Path(filename).stem,
            "{python}": sys.executable,
        }
        out: list[str] = []
        for part in tpl:
            for k, v in mapping.items():
                if k in part:
                    part = part.replace(k, v)
            out.append(part)
        return out

    def build_cmd(self, workdir: Path, filename: str) -> list[str] | None:
        if self.compile_tpl is None:
            return None
        return self._fmt(self.compile_tpl, workdir, filename)

    def exec_cmd(self, workdir: Path, filename: str, args: list[str] | None = None) -> list[str]:
        return self._fmt(self.run_tpl, workdir, filename) + [str(a) for a in (args or [])]

    # ---- 人类可读命令（写进 README / 文档，不含临时目录路径）----
    def build_hint(self, filename: str | None = None) -> str:
        name = filename or self.entry
        if self.compile_tpl is None:
            return ""
        if self.key == "java":
            return f"javac {name}"
        return " ".join(self._fmt(self.compile_tpl, Path("."), name))

    def run_hint(self, filename: str | None = None) -> str:
        name = filename or self.entry
        if self.key == "python":
            return f"python {name}"
        if self.key == "java":
            return f"java {Path(name).stem}"
        prefix = "" if os.name == "nt" else "./"
        return f"{prefix}{Path(name).stem}{EXE}"

    # ---- 环境检查 ----
    def missing_tools(self) -> list[str]:
        """返回本机缺失的可执行文件；Python 用当前解释器，不检查。"""
        return [t for t in self.tools if shutil.which(t) is None]

    def available(self) -> bool:
        return not self.missing_tools()

    # ---- 报错解析 ----
    def parse_error(self, stderr: str, stage: str = "") -> dict[str, Any]:
        if self.error_parser == "python":
            return parse_python_error(stderr, stage)
        if self.error_parser == "gcc":
            return parse_compiler_error(stderr, _GCC_RE, self.error_type)
        if self.error_parser == "javac":
            return parse_compiler_error(stderr, _JAVAC_RE, self.error_type)
        if self.error_parser == "go":
            return parse_compiler_error(stderr, _GO_RE, self.error_type)
        return _tail_diag(stderr, self.error_type)

    # ---- 提示词 ----
    def code_system_prompt(self) -> str:
        return (
            f"你是一名资深 {self.display} 工程师，负责根据用户需求编写代码。\n\n"
            "要求：\n"
            f"1. 只输出一份完整可运行的 {self.display} 程序，不要输出解释文字（可以放在代码注释里）。\n"
            f"2. 输出格式：必须用 ```{self.fence} 代码块包裹整个代码。\n"
            f"{self.rules}\n"
        )

    def debug_system_prompt(self) -> str:
        return (
            f"你是一名 {self.display} 调试专家。用户会给你一段代码和它的运行/编译报错。\n\n"
            "请分析报错原因，输出修复后的完整代码（不要只输出修改片段，必须是完整可运行的程序）。\n"
            "要求：\n"
            f"1. 输出格式：必须用 ```{self.fence} 代码块包裹整个修复后的代码。\n"
            "2. 如果报错信息不完整，做最可能的修复。\n"
            "3. 保持原程序的功能不变，只修复导致运行失败的问题。\n"
            f"{self.debug_rules}"
        )


# --------------------------------------------------------------------------
# 各语言档案
# --------------------------------------------------------------------------
_PY_RULES = """3. 代码必须能直接 `python 文件.py` 运行，不要依赖未安装的第三方库。
4. 程序要有明确的输入/输出：可以读 sys.argv，但必须提供默认值
   （例如 `n = int(sys.argv[1]) if len(sys.argv) > 1 else 10`），
   保证不带参数直接运行也不会报错。
5. 如果任务要求不确定，做合理假设并在注释中说明。"""

_PY_DEBUG_RULES = """4. 如果程序因缺少命令行参数（如 IndexError: list index out of range）而失败，
   请在读参数处加上默认值（如 `n = int(sys.argv[1]) if len(sys.argv) > 1 else 10`），
   保证不带参数也能运行。"""

_C_RULES = """3. 代码必须能直接 `gcc -std=c11 文件.c -o 程序` 编译通过：只写一个 .c 文件，只用 C 标准库，不依赖第三方库。
4. 程序要有明确的输入/输出：用 argc/argv 读命令行参数，但必须提供默认值
   （例如 `int n = argc > 1 ? atoi(argv[1]) : 10;`），保证不带参数运行也不报错。
5. 若用到 math.h 的函数，注意编译时会链接 -lm；输出请用 printf 并在行尾补 '\\n'。
6. 如果任务要求不确定，做合理假设并在注释中说明。"""

_C_DEBUG_RULES = """4. 编译报错优先看行号，常见原因是缺分号、缺 #include、类型不匹配、变量未声明。
5. 若因缺少命令行参数而崩溃，请在读参数处加上默认值（如 `int n = argc > 1 ? atoi(argv[1]) : 10;`）。"""

_CPP_RULES = """3. 代码必须能直接 `g++ -std=c++17 文件.cpp -o 程序` 编译通过：只写一个 .cpp 文件，只用 C++ 标准库。
4. 用 `int main(int argc, char** argv)` 读参数并提供默认值
   （例如 `int n = argc > 1 ? std::stoi(argv[1]) : 10;`），保证不带参数运行也不报错。
5. 不要使用 C++20/23 才有的特性（如 concepts、ranges）；输出用 std::cout 并在行尾补 '\\n'。
6. 如果任务要求不确定，做合理假设并在注释中说明。"""

_CPP_DEBUG_RULES = """4. 编译报错优先看行号，常见原因是缺分号、缺 #include、命名空间未加 std::、类型不匹配。
5. 若因缺少命令行参数而崩溃，请在读参数处加上默认值（如 `int n = argc > 1 ? std::stoi(argv[1]) : 10;`）。"""

_GO_RULES = """3. 代码必须能直接 `go build 文件.go` 编译通过：只写一个 .go 文件，package main + func main()，只用标准库。
4. 用 os.Args 读参数并提供默认值
   （例如 `n := 10; if len(os.Args) > 1 { n, _ = strconv.Atoi(os.Args[1]) }`），保证不带参数运行也不报错。
5. 注意 Go 里「声明了未使用的变量/import」会直接导致编译失败，不要留下没用到的东西。
6. 输出用 fmt.Println / fmt.Printf。
7. 如果任务要求不确定，做合理假设并在注释中说明。"""

_GO_DEBUG_RULES = """4. 编译报错优先看行号。Go 最常见的失败原因是「声明但未使用」的变量或 import（编译错误，不是警告）。
5. 若因缺少命令行参数而越界，请在读参数处加上默认值（如 `n := 10; if len(os.Args) > 1 { n, _ = strconv.Atoi(os.Args[1]) }`）。"""

_JAVA_RULES = """3. 代码必须能直接 `javac Main.java && java Main` 编译运行：public class Main 必须放在 Main.java 中（类名与文件名一致），只用 JDK 标准库，不依赖第三方 jar。
4. 用 `public static void main(String[] args)` 读参数并提供默认值
   （例如 `int n = args.length > 0 ? Integer.parseInt(args[0]) : 10;`），保证不带参数运行也不报错。
5. 用 Java 8 兼容语法（不要用 record / var / switch 表达式等较新特性），避免编译环境差异。
6. 输出用 System.out.println，不要用中文类名或包名。
7. 如果任务要求不确定，做合理假设并在注释中说明。"""

_JAVA_DEBUG_RULES = """4. 编译报错优先看行号，常见原因是缺分号、类名与文件名不一致、类型不匹配、缺少 import。
5. 若因缺少命令行参数而越界，请在读参数处加上默认值（如 `int n = args.length > 0 ? Integer.parseInt(args[0]) : 10;`）。"""

LANGUAGES: dict[str, Language] = {
    "python": Language(
        key="python",
        display="Python",
        ext=".py",
        fence="python",
        entry="main.py",
        run_tpl=("{python}", "{src}"),
        test_strategy="pytest",
        rules=_PY_RULES,
        debug_rules=_PY_DEBUG_RULES,
        error_parser="python",
        error_type="RuntimeError",
    ),
    "c": Language(
        key="c",
        display="C",
        ext=".c",
        fence="c",
        entry="main.c",
        compile_tpl=("gcc", "-std=c11", "-O0", "-w", "{src}", "-o", "{out}", "-lm"),
        run_tpl=("{out}",),
        tools=("gcc",),
        rules=_C_RULES,
        debug_rules=_C_DEBUG_RULES,
        error_parser="gcc",
    ),
    "cpp": Language(
        key="cpp",
        display="C++",
        ext=".cpp",
        fence="cpp",
        entry="main.cpp",
        compile_tpl=("g++", "-std=c++17", "-O0", "-w", "{src}", "-o", "{out}"),
        run_tpl=("{out}",),
        tools=("g++",),
        rules=_CPP_RULES,
        debug_rules=_CPP_DEBUG_RULES,
        error_parser="gcc",
    ),
    "go": Language(
        key="go",
        display="Go",
        ext=".go",
        fence="go",
        entry="main.go",
        compile_tpl=("go", "build", "-o", "{out}", "{src}"),
        run_tpl=("{out}",),
        tools=("go",),
        rules=_GO_RULES,
        debug_rules=_GO_DEBUG_RULES,
        error_parser="go",
    ),
    "java": Language(
        key="java",
        display="Java",
        ext=".java",
        fence="java",
        entry="Main.java",
        compile_tpl=("javac", "-encoding", "UTF-8", "-d", "{workdir}", "{src}"),
        run_tpl=("java", "-cp", "{workdir}", "{stem}"),
        tools=("javac", "java"),
        rules=_JAVA_RULES,
        debug_rules=_JAVA_DEBUG_RULES,
        error_parser="javac",
    ),
}

# 别名：用户输入 --lang c++ / golang 这类写法也能识别
ALIASES = {
    "py": "python",
    "python3": "python",
    "c11": "c",
    "c99": "c",
    "c++": "cpp",
    "cxx": "cpp",
    "cplusplus": "cpp",
    "golang": "go",
    "jdk": "java",
}

DEFAULT_LANGUAGE = "python"


class UnknownLanguageError(ValueError):
    """请求了不支持的语言。"""


def language_keys() -> list[str]:
    return list(LANGUAGES)


def resolve_language(name: str | None, default: str = DEFAULT_LANGUAGE) -> Language:
    """按 key 取语言档案；None → 默认语言；未知 key 抛 UnknownLanguageError。"""
    if name is None or str(name).strip() == "":
        return LANGUAGES[default]
    key = str(name).strip().lower()
    key = ALIASES.get(key, key)
    lang = LANGUAGES.get(key)
    if lang is None:
        raise UnknownLanguageError(
            f"不支持的语言：{name}。可选：{', '.join(language_keys())}"
        )
    return lang


def language_from_filename(filename: str, default: str = DEFAULT_LANGUAGE) -> Language:
    """按文件后缀推断语言，认不出则回退到默认语言。"""
    ext = Path(filename).suffix.lower()
    for lang in LANGUAGES.values():
        if lang.ext == ext:
            return lang
    return LANGUAGES[default]


def toolchain_status() -> list[dict[str, Any]]:
    """各语言的语言档案 + 本机工具链可用性（给 CLI / API / UI 展示）。"""
    rows: list[dict[str, Any]] = []
    for lang in LANGUAGES.values():
        missing = lang.missing_tools()
        rows.append(
            {
                "key": lang.key,
                "display": lang.display,
                "ext": lang.ext,
                "entry": lang.entry,
                "test_strategy": lang.test_strategy,
                "needs_build": lang.needs_build,
                "tools": list(lang.tools),
                "available": not missing,
                "missing": missing,
            }
        )
    return rows
