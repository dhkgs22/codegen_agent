"""命令行运行器：python -m app.cli "任务描述"

示例：
    python -m app.cli "写一个计算斐波那契数列前 N 项的程序"
    python -m app.cli --provider fake --rounds 2 "写一个 hello world"
"""
from __future__ import annotations

import argparse
import json
import sys

from .agents import Coordinator
from .events import EV_CODE, EV_DOC, EV_FAIL, EV_FIX, EV_LOG, EV_MSG, EV_RUN, EV_START, EV_TEST
from .llm import build_client


def _print_event(kind: str, message: str, data: dict) -> None:
    tag = {
        EV_START: "[任务开始]",
        EV_CODE: "[生成代码]",
        EV_RUN: "[运行]",
        EV_FIX: "[修复]",
        EV_DOC: "[文档]",
        EV_TEST: "[测试]",
        EV_MSG: "[协作]",
        EV_FAIL: "[失败]",
        EV_LOG: "[日志]",
    }.get(kind, f"[{kind}]")
    print(f"\n{tag} {message}")
    if kind == EV_CODE and data.get("code"):
        print("```python")
        print(data["code"])
        print("```")
    elif kind == EV_RUN:
        if data.get("stderr"):
            print(f"  stderr:\n{data['stderr']}")
        if data.get("stdout"):
            print(f"  stdout:\n{data['stdout']}")
    elif kind == EV_FIX and data.get("code"):
        print("修复后代码：")
        print(data["code"])
    elif kind == EV_DOC and data.get("readme"):
        print(data["readme"])
    elif kind == EV_TEST:
        status = "✅ 通过" if data.get("passed") else "⚠️ 未通过"
        print(f"  {status}  {data.get('summary', '')}")
    elif kind == EV_MSG:
        print(f"  🔁 {message}")


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，无法输出 emoji/中文，重配置为 UTF-8
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="多智能体代码助手 CLI")
    parser.add_argument(
        "task",
        nargs="?",
        default="写一个计算斐波那契数列前 N 项的程序",
        help="用自然语言描述要生成的任务",
    )
    parser.add_argument("--provider", default=None, help="llm 提供方: deepseek / fake")
    parser.add_argument("--rounds", type=int, default=None, help="最大修复轮次")
    parser.add_argument("--no-tests", action="store_true", help="不自动生成并运行测试")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    parser.add_argument("--workspace", default=None, help="指定工作目录（默认临时）")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="演示模式：用脚本化响应跑通完整流程（不消耗 token）",
    )
    args = parser.parse_args(argv)

    try:
        if args.demo:
            from .llm import FakeClient

            bad_code = (
                "```python\n"
                "import sys\n"
                "n = int(sys.argv[1]) if len(sys.argv) > 1 else 5\n"
                "print(undefined_func(n))\n"
                "```"
            )
            good_code = (
                "```python\n"
                "import sys\n"
                "def fib(n):\n"
                "    a, b = 0, 1\n"
                "    for _ in range(n):\n"
                "        a, b = b, a + b\n"
                "    return a\n"
                "n = int(sys.argv[1]) if len(sys.argv) > 1 else 10\n"
                "print([fib(i) for i in range(n)])\n"
                "```"
            )
            readme = (
                "# 斐波那契数列计算器\n\n"
                "输入 n，输出前 n 项斐波那契数列。\n\n"
                "## 用法\n\n```bash\npython main.py 10\n```\n"
            )
            test_code = (
                "```python\n"
                "import subprocess, sys, pathlib\n"
                "def run(*a):\n"
                "    return subprocess.run([sys.executable, 'main.py', *a], capture_output=True, text=True, cwd=pathlib.Path(__file__).parent)\n"
                "def test_contains_fib21():\n"
                "    assert '21' in run('8').stdout\n"
                "def test_contains_zero():\n"
                "    assert '0' in run('1').stdout\n"
                "```"
            )
            llm = FakeClient(responses=[bad_code, good_code, readme, test_code])
            if args.task in ("", "demo"):
                args.task = "写一个计算斐波那契数列前 N 项的程序"
        else:
            llm = build_client(args.provider)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    coordinator = Coordinator(
        llm=llm,
        max_rounds=args.rounds,
        workspace=args.workspace,
        keep_workspace=bool(args.workspace),
        enable_tests=not args.no_tests,
    )

    if not args.json:
        coordinator.bus.subscribe(lambda e: _print_event(e.kind, e.message, e.data))
    else:
        coordinator.bus.subscribe(lambda e: print(json.dumps(e.to_dict(), ensure_ascii=False), flush=True))

    result = coordinator.run(args.task)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False))
        return 0 if result.success else 1

    print("\n" + "=" * 50)
    if result.success:
        print(f"✅ 成功！用了 {result.rounds_used} 轮，耗时 {result.duration_s:.1f}s")
        print(f"产出文件：{result.files}")
        print(f"最终输出：{result.final_output[:500]}")
    else:
        print(f"❌ 失败：{result.error}")
    print(f"workspace：{result.workspace}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
