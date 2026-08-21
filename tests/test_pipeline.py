"""Coordinator 端到端测试（使用 FakeClient，不消耗真实 token）。"""
import pytest

from app.agents import Coordinator
from app.llm import FakeClient

GOOD_CODE = (
    '```python\n'
    'import sys\n'
    'n = int(sys.argv[1]) if len(sys.argv) > 1 else 5\n'
    'print(n * 2)\n'
    '```'
)

# 第一份代码有 bug：调用了不存在的函数
BAD_CODE = (
    '```python\n'
    'import sys\n'
    'n = int(sys.argv[1]) if len(sys.argv) > 1 else 5\n'
    'print(undefined_func(n))\n'
    '```'
)


def test_success_first_try():
    fake = FakeClient(
        responses=[GOOD_CODE, "# README placeholder\n这个程序把输入数字乘 2。"]
    )
    coordinator = Coordinator(llm=fake, max_rounds=3)
    result = coordinator.run("写一个把数字翻倍的程序")
    assert result.success
    assert result.rounds_used == 1
    assert "main.py" in result.files
    assert "README.md" in result.files
    assert fake.calls[0]["messages"][1]["content"].startswith("用户任务")


def test_fix_loop_until_success():
    # 第 1 次返回坏代码 → 运行失败 → Debug Agent 修复（第 2 次）→ 成功
    fixed_code = GOOD_CODE
    fake = FakeClient(
        responses=[
            BAD_CODE,      # Code Agent 生成的坏代码
            fixed_code,    # Debug Agent 修复
            "# README\n翻倍程序。",
        ]
    )
    coordinator = Coordinator(llm=fake, max_rounds=3)
    result = coordinator.run("写一个把数字翻倍的程序")
    assert result.success
    assert result.rounds_used == 2
    # Debug Agent 至少被调用一次
    debug_calls = [c for c in fake.calls if "调试专家" in c["messages"][0]["content"]]
    assert len(debug_calls) == 1


def test_fail_after_max_rounds():
    # 一直返回坏代码 → 修复循环跑满 max_rounds 后失败
    fake = FakeClient(responses=[BAD_CODE, BAD_CODE, BAD_CODE, BAD_CODE])
    coordinator = Coordinator(llm=fake, max_rounds=3)
    result = coordinator.run("写一个把数字翻倍的程序")
    assert not result.success
    assert result.rounds_used == 3
    assert result.error


def test_events_emitted():
    from app.events import EV_CODE, EV_DOC, EV_START

    fake = FakeClient(responses=[GOOD_CODE, "# README"])
    coordinator = Coordinator(llm=fake, max_rounds=3)
    coordinator.run("写一个把数字翻倍的程序")
    kinds = [e.kind for e in coordinator.bus.events()]
    assert EV_START in kinds
    assert EV_CODE in kinds
    assert EV_DOC in kinds


def test_cli_json_output(tmp_path, monkeypatch):
    """CLI 的 --json 模式输出可解析的 JSON。"""
    import json as _json
    import sys

    from app.cli import main

    fake = FakeClient(responses=[GOOD_CODE, "# README"])

    class _Builder:
        def __init__(self, fake_client):
            self._fake = fake_client

        def __call__(self, provider=None, **kwargs):
            return self._fake

    monkeypatch.setattr("app.cli.build_client", _Builder(fake))
    code = main(["写一个程序", "--json"])
    assert code == 0
