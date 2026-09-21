"""Benchmark：批量跑多任务，统计成功率/耗时/轮次，输出 benchmark/results.md。

覆盖 Python / C / C++ / Go / Java 五种语言，并按语言分组统计通过率。

用法（在项目根目录）：
    python scripts/benchmark.py                          # 真实 DeepSeek，跑全部任务
    python scripts/benchmark.py --provider fake --limit 3 # FakeClient，快速验证机制
    python scripts/benchmark.py --lang c                 # 只跑 C 语言任务
    python scripts/benchmark.py --no-tests               # 关闭自动测试
    python scripts/benchmark.py --max-rounds 4           # 提高修复轮次上限
    python scripts/benchmark.py --out my.md              # 写到别的文件（不覆盖 results.md）
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# 保证从任意目录运行时都能 import app / benchmark
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents import Coordinator  # noqa: E402
from app.config import settings  # noqa: E402
from app.languages import resolve_language, toolchain_status  # noqa: E402
from app.llm import build_client  # noqa: E402
from app.sandbox import Sandbox  # noqa: E402
from benchmark.tasks import TASKS  # noqa: E402

CHECK = {True: "✅", False: "❌"}


def run_one(llm, task, max_rounds: int, enable_tests: bool) -> dict:
    lang = resolve_language(task.language)
    ws = tempfile.mkdtemp(prefix="bench-")
    try:
        coord = Coordinator(
            llm=llm,
            workspace=ws,
            max_rounds=max_rounds,
            keep_workspace=True,
            enable_tests=enable_tests,
            language=lang,
        )
        result = coord.run(task.prompt)
        row = {
            "id": task.id,
            "title": task.title,
            "language": lang.key,
            "lang_display": lang.display,
            "pipeline_ok": result.success,
            "rounds": result.rounds_used,
            "duration": round(result.duration_s, 1),
            "tests_passed": result.tests_passed,
            "verify_ok": False,
            "verify_out": "",
        }
        if result.success:
            sb = Sandbox(workspace=result.workspace)
            if task.setup is not None:
                task.setup(sb)
            # 按语言取入口文件名（main.py / main.c / main.cpp / main.go / Main.java）
            run_res = sb.run_file(lang.entry, task.args)
            row["verify_ok"] = bool(task.check(run_res.stdout or ""))
            row["verify_out"] = (run_res.stdout or "").strip().replace("\n", " ")[:80]
        else:
            row["verify_out"] = result.error[:80]
        return row
    except Exception as e:  # noqa: BLE001
        return {
            "id": task.id,
            "title": task.title,
            "language": lang.key,
            "lang_display": lang.display,
            "pipeline_ok": False,
            "rounds": 0,
            "duration": 0.0,
            "tests_passed": None,
            "verify_ok": False,
            "verify_out": f"异常：{e}"[:80],
        }
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def render_table(rows: list[dict]) -> str:
    lines = [
        "| # | 任务 | 语言 | 流水线 | 结果正确 | 修复轮次 | 耗时 | 自动测试 | 验证输出 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        tp = "✅" if r["tests_passed"] else ("—" if r["tests_passed"] is None else "❌")
        lines.append(
            f"| {i} | {r['title']} | {r.get('lang_display', 'Python')} "
            f"| {CHECK[r['pipeline_ok']]} | {CHECK[r['verify_ok']]} "
            f"| {r['rounds']} | {r['duration']}s | {tp} | `{r['verify_out'][:40]}` |"
        )
    return "\n".join(lines)


def render_by_language(rows: list[dict]) -> str:
    """按语言分组的通过率——多语言支持的核心指标。"""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r.get("lang_display", "Python"), []).append(r)
    lines = ["| 语言 | 任务数 | 结果正确 | 自动测试通过 |", "|---|---|---|---|"]
    for name, items in groups.items():
        n = len(items)
        ok = sum(i["verify_ok"] for i in items)
        tested = [i for i in items if i["tests_passed"] is not None]
        t_ok = sum(i["tests_passed"] for i in tested)
        t_str = f"{t_ok}/{len(tested)}" if tested else "未启用"
        lines.append(f"| {name} | {n} | {ok}/{n} ({ok / n * 100:.0f}%) | {t_str} |")
    return "\n".join(lines)


def summarize(rows: list[dict], max_rounds: int, enable_tests: bool) -> str:
    n = len(rows)
    pipe_ok = sum(r["pipeline_ok"] for r in rows)
    verify_ok = sum(r["verify_ok"] for r in rows)
    avg_dur = sum(r["duration"] for r in rows) / n
    avg_rounds = sum(r["rounds"] for r in rows) / n
    tests = [r for r in rows if r["tests_passed"] is not None]
    tests_ok = sum(r["tests_passed"] for r in tests)

    def pct(x: int) -> str:
        return f"{x}/{n} ({x / n * 100:.0f}%)"

    lines = [
        "## 汇总",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 任务总数 | {n} |",
        f"| 流水线成功（能跑通） | {pct(pipe_ok)} |",
        f"| 结果正确（验证器通过） | {pct(verify_ok)} |",
        f"| 自动测试通过 | {pct(tests_ok)}" if tests else f"| 自动测试 | 未启用 |",
        f"| 平均耗时 | {avg_dur:.1f}s |",
        f"| 平均修复轮次 | {avg_rounds:.1f} |",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="多智能体代码助手 Benchmark")
    parser.add_argument("--provider", default=None, help="deepseek / fake（默认 deepseek，无 key 则 fake）")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 个任务（0 = 全部）")
    parser.add_argument("--max-rounds", type=int, default=None, help="最大修复轮次")
    parser.add_argument("--no-tests", action="store_true", help="关闭自动测试")
    parser.add_argument(
        "--lang", default=None, help="只跑指定语言的任务：python / c / cpp / go / java"
    )
    parser.add_argument("--verbose", action="store_true", help="打印每个任务的错误详情")
    parser.add_argument(
        "--out",
        default=str(ROOT / "benchmark" / "results.md"),
        help="结果输出路径（默认 benchmark/results.md）",
    )
    args = parser.parse_args(argv)

    provider = args.provider or ("deepseek" if settings.deepseek_api_key else "fake")
    enable_tests = not args.no_tests
    max_rounds = args.max_rounds if args.max_rounds is not None else settings.max_fix_rounds

    try:
        llm = build_client(provider)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    tasks = TASKS
    if args.lang:
        try:
            want = resolve_language(args.lang).key
        except ValueError as e:
            print(f"错误：{e}", file=sys.stderr)
            return 2
        tasks = [t for t in tasks if t.language == want]
    if args.limit:
        tasks = tasks[: args.limit]

    # 工具链自检：本机缺编译器的语言，任务会直接失败，先提示清楚
    unavailable = {r["key"]: r["missing"] for r in toolchain_status() if not r["available"]}
    skipped = [t for t in tasks if t.language in unavailable]
    if skipped:
        print(
            "⚠️  本机缺少工具链，以下 "
            f"{len(skipped)} 个任务预计会失败："
            + ", ".join(f"{t.title}(缺 {','.join(unavailable[t.language])})" for t in skipped),
            file=sys.stderr,
        )

    print(
        f"Benchmark 开始：{len(tasks)} 个任务 · provider={provider} · 轮次上限={max_rounds} · "
        f"自动测试={'开' if enable_tests else '关'}\n"
    )

    rows = []
    for i, task in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {task.title} ...", flush=True)
        t0 = time.time()
        row = run_one(llm, task, max_rounds, enable_tests)
        dt = time.time() - t0
        print(f"    流水线={'✅' if row['pipeline_ok'] else '❌'} "
              f"正确={'✅' if row['verify_ok'] else '❌'} "
              f"轮次={row['rounds']} 耗时={row['duration']}s (共{dt:.0f}s)", flush=True)
        if args.verbose and not row["verify_ok"]:
            print(f"    输出: {row['verify_out']}")
        rows.append(row)

    md = [
        "# Benchmark 评测结果",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 模型：{provider} · "
        f"语言：{'全部' if not args.lang else args.lang} · "
        f"修复轮次上限：{max_rounds} · 自动测试：{'开启' if enable_tests else '关闭'}",
        "",
        summarize(rows, max_rounds, enable_tests),
        "",
        "## 分语言统计",
        "",
        render_by_language(rows),
        "",
        "## 明细",
        "",
        render_table(rows),
        "",
        "> 说明：流水线成功 = 程序能无参运行且 Debug Agent 修到通过；",
        "结果正确 = 用指定参数再次运行，验证器确认输出符合预期。",
        "",
    ]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")
    print(f"\n已写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
