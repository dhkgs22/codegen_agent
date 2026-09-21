"""黑盒测试运行器：不依赖各语言的测试框架，用「用例 + 期望输出」验证程序行为。

为什么需要它：pytest 只适用于 Python。C/C++/Go/Java 各有各的测试框架，在沙箱里
未必装得上（JUnit 还要额外的 jar 包），而本项目的测试目标其实很明确——
「程序对给定输入产生正确输出」，这正是黑盒测试能覆盖的部分。

做法：Test Agent 生成一份语言无关的 JSON 用例集 → 沙箱编译一次 →
逐条用命令行参数 / stdin 调用程序 → 断言 stdout。任何语言共用同一套机制。

用例格式（Test Agent 按此输出）：
    {"cases": [
        {"name": "正常输入", "args": ["5"], "stdin": "",
         "expect_contains": ["10"], "expect_not_contains": [], "expect_exit_code": 0}
    ]}
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .runner import Sandbox

MAX_CASES = 20  # 防止 LLM 生成过多用例把沙箱拖死


@dataclass
class Case:
    name: str = "用例"
    args: list[str] = field(default_factory=list)
    stdin: str = ""
    expect_contains: list[str] = field(default_factory=list)
    expect_not_contains: list[str] = field(default_factory=list)
    expect_exit_code: int = 0

    @classmethod
    def from_dict(cls, raw: dict[str, Any], index: int = 1) -> "Case":
        def _strs(v: Any) -> list[str]:
            if v is None:
                return []
            if isinstance(v, str):
                return [v]
            if isinstance(v, (list, tuple)):
                return [str(x) for x in v]
            return [str(v)]

        args = raw.get("args") or []
        if isinstance(args, str):
            args = [args]
        try:
            exit_code = int(raw.get("expect_exit_code", 0))
        except (TypeError, ValueError):
            exit_code = 0
        return cls(
            name=str(raw.get("name") or f"用例 {index}"),
            args=[str(a) for a in args],
            stdin=str(raw.get("stdin") or ""),
            expect_contains=_strs(raw.get("expect_contains")),
            expect_not_contains=_strs(raw.get("expect_not_contains")),
            expect_exit_code=exit_code,
        )


def value_present(text: str, needle: str) -> bool:
    """needle 是否作为一个「独立的值」出现在 text 中（不是朴素子串匹配）。

    例：needle="1" 不应匹配 "11" / "19" / "29" 里的那个 1。
    否则 LLM 写「输出不应出现 1」这类用例时，会把 11、13、19、29 全部误判为违规，
    导致流水线对着一份正确的程序反复「修复」。
    """
    if not needle:
        return False
    first, last = needle[0], needle[-1]
    # 数字用 \\d 边界，字母/下划线用 \\w 边界，其它符号不做边界限制
    left = r"(?<!\d)" if first.isdigit() else (r"(?<!\w)" if first.isalnum() else "")
    right = r"(?!\d)" if last.isdigit() else (r"(?!\w)" if last.isalnum() else "")
    return re.search(left + re.escape(needle) + right, text) is not None


def extract_json(text: str) -> dict[str, Any] | None:
    """从 LLM 回复中提取 JSON 对象（容忍 ```json 包裹与前后说明文字）。"""
    if not text:
        return None
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    candidates = [b.strip() for b in fenced] + [text.strip()]
    decoder = json.JSONDecoder()
    for cand in candidates:
        if not cand:
            continue
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
        # 兜底：从文本里扫第一个能解析的 JSON 对象
        for i, ch in enumerate(cand):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(cand[i:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def parse_cases(text: str) -> list[Case]:
    """把 LLM 输出的测试规格文本解析成用例列表（解析不出来返回空列表）。"""
    data = extract_json(text)
    if not isinstance(data, dict):
        return []
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        return []
    cases: list[Case] = []
    for i, raw in enumerate(raw_cases[:MAX_CASES], 1):
        if isinstance(raw, dict):
            cases.append(Case.from_dict(raw, i))
    return cases


def run_cases(
    sandbox: Sandbox,
    filename: str,
    cases: list[Case],
) -> dict[str, Any]:
    """编译一次、逐条跑用例，返回与 TestAgent 其它策略一致的 result dict。

    返回 {"passed", "summary", "output", "returncode", "cases_total", "cases_passed"}。
    """
    if not cases:
        return {
            "passed": False,
            "summary": "未解析出任何测试用例",
            "output": "",
            "returncode": -1,
            "cases_total": 0,
            "cases_passed": 0,
        }

    start = time.time()
    lines: list[str] = []
    passed_n = 0
    failure_seen = False

    # 先编译一次（编译型语言），避免每条用例都重新编译
    build = sandbox.build_file(filename)
    if build is not None and not build.ok:
        out = f"[编译失败]\n{build.stderr or build.stdout or build.error}"
        return {
            "passed": False,
            "summary": "编译失败，无法运行测试",
            "output": out[:4000],
            "returncode": build.returncode,
            "cases_total": len(cases),
            "cases_passed": 0,
        }

    for i, case in enumerate(cases, 1):
        res = sandbox.exec_file(filename, case.args, case.stdin or None)
        problems: list[str] = []

        if res.timed_out:
            problems.append("运行超时")
        elif res.error:
            problems.append(f"启动失败：{res.error}")
        else:
            stdout = res.stdout or ""
            if res.returncode != case.expect_exit_code:
                problems.append(f"退出码 {res.returncode}，期望 {case.expect_exit_code}")
            # expect_contains 用子串匹配（宽松，宁漏报不误报）；
            # expect_not_contains 用独立值匹配（避免 "1" 命中 "11" 这类误报）。
            for want in case.expect_contains:
                if want not in stdout:
                    problems.append(f"输出中缺少 {want!r}")
            for bad in case.expect_not_contains:
                if value_present(stdout, bad):
                    problems.append(f"输出中不应出现 {bad!r}")

        ok = not problems
        if ok:
            passed_n += 1
        else:
            failure_seen = True

        lines.append(f"[用例 {i}/{len(cases)}] {case.name} — {'通过' if ok else '失败'}")
        if case.args:
            lines.append(f"    参数: {case.args}")
        if case.stdin:
            lines.append(f"    stdin: {case.stdin[:100]!r}")
        if not ok:
            for p in problems:
                lines.append(f"    问题: {p}")
            lines.append(f"    期望输出包含: {case.expect_contains}")
            lines.append(f"    实际 stdout: {(res.stdout or '').strip()[:300] or '(空)'}")
            if res.stderr:
                lines.append(f"    实际 stderr: {res.stderr.strip()[:300]}")

    failed_n = len(cases) - passed_n
    duration = time.time() - start
    summary = f"{passed_n} passed, {failed_n} failed in {duration:.2f}s"

    return {
        "passed": not failure_seen,
        "summary": summary,
        "output": "\n".join(lines)[:4000],
        "returncode": 0 if not failure_seen else 1,
        "cases_total": len(cases),
        "cases_passed": passed_n,
    }
