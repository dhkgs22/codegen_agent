"""Benchmark 任务集：10 个从易到难的代码生成任务，每个带验证器。

验证器逻辑：程序跑通流水线（能无参运行）后，再用 task.args 调用一次
main.py，用 task.check(stdout) 判断输出是否正确——流水线成功 ≠ 结果正确。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.sandbox import RunResult, Sandbox


@dataclass
class BenchTask:
    id: str
    title: str
    prompt: str
    args: list[str] = field(default_factory=list)
    check: Callable[[str], bool] = lambda out: bool(out.strip())
    setup: Callable[[Sandbox], None] | None = None
    language: str = "python"  # 目标语言：python / c / cpp / go / java


def _has(*subs: str) -> Callable[[str], bool]:
    return lambda out: all(s in out for s in subs)


def _not_has(*subs: str) -> Callable[[str], bool]:
    def f(out: str) -> bool:
        return all(s not in out for s in subs)

    return f


def _all(*checks: Callable[[str], bool]) -> Callable[[str], bool]:
    def f(out: str) -> bool:
        return all(c(out) for c in checks)

    return f


TASKS: list[BenchTask] = [
    BenchTask(
        id="fib",
        title="斐波那契数列",
        prompt="写一个程序，读取命令行参数 n（正整数，默认 10），输出前 n 个斐波那契数，"
        "用空格分隔（0 1 1 2 3 5 8 13 ...）。",
        args=["8"],
        check=_has("13", "0"),
    ),
    BenchTask(
        id="prime",
        title="素数筛选",
        prompt="写一个程序，输出 1 到 100 之间所有的素数，每行一个。",
        check=_all(_has("97", "2"), _not_has("49")),
    ),
    BenchTask(
        id="sort",
        title="整数排序",
        prompt="写一个程序，读取命令行参数中的若干个整数（空格分隔），"
        "按从小到大排序后用空格分隔输出。",
        args=["5", "3", "8", "1"],
        check=_has("1 3 5 8"),
    ),
    BenchTask(
        id="wordcount",
        title="词频统计",
        prompt="写一个程序，读取命令行参数的一段英文文本，统计每个单词出现次数，"
        "每行输出 `单词: 次数`。",
        args=["hello world hello python hello"],
        check=_has("hello", "3"),
    ),
    BenchTask(
        id="binary_search",
        title="二分查找",
        prompt="写一个程序，读取命令行参数：第一个数是目标值，之后是升序排列的整数序列，"
        "实现二分查找，输出目标值的下标（从 0 开始），找不到输出 -1。",
        args=["7", "1", "3", "5", "7", "9", "11", "13"],
        check=_has("3"),
    ),
    BenchTask(
        id="file_lines",
        title="文件行数统计",
        prompt="写一个程序，读取同目录下 data.txt 的内容，输出文件的总行数（一个数字）。",
        setup=lambda sb: sb.write_file("data.txt", "a\nb\nc\nd\ne\n"),
        check=_has("5"),
    ),
    BenchTask(
        id="calc",
        title="四则运算计算器",
        prompt="写一个四则运算计算器，读取命令行参数中的一个数学表达式（如 3+4*2），"
        "按运算符优先级（先乘除后加减）计算并输出结果。",
        args=["3+4*2"],
        check=_has("11"),
    ),
    BenchTask(
        id="reverse",
        title="字符串反转",
        prompt="写一个程序，读取命令行参数的一个字符串，输出反转后的字符串。",
        args=["abcde"],
        check=_has("edcba"),
    ),
    BenchTask(
        id="bank",
        title="银行账户类",
        prompt="写一个银行账户类 BankAccount，支持 deposit(amount)、withdraw(amount)、"
        "get_balance() 方法。在 main 中演示：开户余额 0，存 100，取 30，打印当前余额。",
        check=_all(_has("70"), _not_has("60")),
    ),
    BenchTask(
        id="stats",
        title="统计最大最小平均",
        prompt="写一个程序，读取命令行参数中的若干个整数（空格分隔），"
        "输出它们的最大值、最小值、平均值，格式为 max=... min=... avg=...（avg 保留一位小数）。",
        args=["3", "7", "2", "8"],
        check=_has("max", "8", "2", "5.0"),
    ),
    # ---- 多语言任务：同一类问题换语言，验证多语言流水线 ----
    BenchTask(
        id="c_prime",
        title="[C] 素数筛选",
        prompt="写一个 C 程序（单个 .c 文件），输出 1 到 100 之间所有的素数，每行一个。",
        language="c",
        check=_all(_has("97", "2"), _not_has("49")),
    ),
    BenchTask(
        id="c_reverse",
        title="[C] 字符串反转",
        prompt="写一个 C 程序（单个 .c 文件），读取命令行参数的一个字符串，输出反转后的字符串。",
        language="c",
        args=["abcde"],
        check=_has("edcba"),
    ),
    BenchTask(
        id="cpp_sort",
        title="[C++] 整数排序",
        prompt="写一个 C++ 程序（单个 .cpp 文件），读取命令行参数中的若干个整数（空格分隔），"
        "按从小到大排序后用空格分隔输出。",
        language="cpp",
        args=["5", "3", "8", "1"],
        check=_has("1 3 5 8"),
    ),
    BenchTask(
        id="cpp_stats",
        title="[C++] 统计最大最小平均",
        prompt="写一个 C++ 程序（单个 .cpp 文件），读取命令行参数中的若干个整数（空格分隔），"
        "输出它们的最大值、最小值、平均值，格式为 max=... min=... avg=...（avg 保留一位小数）。",
        language="cpp",
        args=["3", "7", "2", "8"],
        check=_has("max", "8", "2", "5.0"),
    ),
    BenchTask(
        id="go_fib",
        title="[Go] 斐波那契数列",
        prompt="写一个 Go 程序（单个 .go 文件，package main），读取命令行参数 n（正整数，默认 10），"
        "输出前 n 个斐波那契数，用空格分隔（0 1 1 2 3 5 8 13 ...）。",
        language="go",
        args=["8"],
        check=_has("13", "0"),
    ),
    BenchTask(
        id="go_wordcount",
        title="[Go] 词频统计",
        prompt="写一个 Go 程序（单个 .go 文件，package main），读取命令行参数的一段英文文本，"
        "统计每个单词出现次数，每行输出 `单词: 次数`。",
        language="go",
        args=["hello world hello go hello"],
        check=_has("hello", "3"),
    ),
    BenchTask(
        id="java_bank",
        title="[Java] 银行账户类",
        prompt="写一个 Java 程序（public class Main 放在 Main.java 中），定义银行账户类 BankAccount，"
        "支持 deposit(amount)、withdraw(amount)、get_balance()。在 main 中演示："
        "开户余额 0，存 100，取 30，打印当前余额。",
        language="java",
        check=_all(_has("70"), _not_has("60")),
    ),
    BenchTask(
        id="java_calc",
        title="[Java] 四则运算计算器",
        prompt="写一个 Java 程序（public class Main 放在 Main.java 中），读取命令行参数中的一个数学表达式"
        "（如 3+4*2），按运算符优先级（先乘除后加减）计算并输出结果。",
        language="java",
        args=["3+4*2"],
        check=_has("11"),
    ),
]
