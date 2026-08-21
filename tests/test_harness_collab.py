"""Harness 基础设施层 + Test→Debug 协作回环的测试。"""
import pytest

from app.agents import Coordinator, TestAgent
from app.agents.debug_agent import DebugAgent
from app.harness import Harness
from app.llm import FakeClient
from app.sandbox import Sandbox

# 可运行的「翻倍」程序：n=5 → 输出 10
GOOD = (
    "```python\n"
    "import sys\n"
    "n = int(sys.argv[1]) if len(sys.argv) > 1 else 5\n"
    "print(n * 2)\n"
    "```"
)
# 满足 GOOD 的测试：断言 run('5') 输出含 "10"
PASS_TEST = (
    "```python\n"
    "import subprocess, sys, pathlib\n"
    "def run(*a):\n"
    '    return subprocess.run([sys.executable, "main.py", *a], capture_output=True, text=True, cwd=pathlib.Path(__file__).parent)\n'
    "def test_double():\n"
    '    assert "10" in run("5").stdout\n'
    "```"
)


def test_harness_provides_sandbox_bus_tools():
    h = Harness()
    assert h.sandbox is not None
    names = [t["name"] for t in h.tools.list_tools()]
    assert "run_python" in names
    assert "read_file" in names
    assert "write_file" in names
    # 通过工具注册表调用沙箱能力
    h.tools.call("write_file", filename="x.txt", content="hi")
    assert h.tools.call("read_file", filename="x.txt") == "hi"
    assert h.list_files() == ["x.txt"]
    with pytest.raises(KeyError):
        h.tools.call("no_such_tool")


def test_agents_share_harness_resources():
    h = Harness()
    dbg = DebugAgent(FakeClient(["```python\nprint(1)\n```"]), harness=h)
    assert dbg.sandbox is h.sandbox
    assert dbg.bus is h.bus


def test_debug_fix_tests_prompt_contains_failure():
    fake = FakeClient(["```python\nprint('ok')\n```"])
    dbg = DebugAgent(fake, Sandbox())
    dbg.fix_tests("翻倍任务", GOOD, "1 failed ... assert '99' not in stdout")
    msg = fake.calls[0]["messages"][1]["content"]
    assert "测试" in msg or "pytest" in msg
    assert "assert" in msg


def test_test_agent_rerun_after_fix():
    main_code = 'import sys\nn = int(sys.argv[1]) if len(sys.argv) > 1 else 5\nprint(n * 2)\n'
    sb = Sandbox()
    sb.write_file("main.py", main_code)
    fake = FakeClient([PASS_TEST])
    ta = TestAgent(fake, sb)
    info = ta.generate_tests("double", main_code)
    assert info["passed"] is True
    # rerun 不重新生成测试，直接复测同一份 test_main.py
    info2 = ta.rerun()
    assert info2["passed"] is True
    assert len(fake.calls) == 1  # 只有生成测试调了一次 LLM


def test_test_debug_collab_loop_repairs():
    """Test 发现 bug → 协作消息 → Debug 修复 → 复测通过。"""
    # 第一次生成的测试断言 '99'，但 main 输出 10 → 失败
    FAIL_TEST = PASS_TEST.replace('assert "10" in run("5").stdout', 'assert "99" in run("5").stdout')
    # Debug 修复后：n=5 输出 99（n*20-1），满足 '99' 断言
    FIXED = (
        "```python\n"
        "import sys\n"
        "n = int(sys.argv[1]) if len(sys.argv) > 1 else 5\n"
        "print(n * 20 - 1)\n"
        "```"
    )
    # LLM 调用序列：Code=GOOD, Doc=readme, Test=FAIL_TEST, Debug修复=FIXED
    fake = FakeClient([GOOD, "# README", FAIL_TEST, FIXED])
    coord = Coordinator(
        llm=fake,
        max_rounds=3,
        enable_tests=True,
        max_test_rounds=2,
        keep_workspace=True,  # 保留沙箱以便断言复测后的文件
    )
    result = coord.run("写一个把数字翻倍的程序")
    assert result.success
    assert result.tests_passed is True
    assert result.test_rounds_used == 2
    # 协作消息已发出，且目标指向 DebugAgent
    msg_events = [e for e in coord.bus.events() if e.kind == "msg"]
    assert msg_events, "应产生 Test→Debug 协作消息事件"
    assert "DebugAgent" in msg_events[0].data.get("target", "")
    # 复测用的是同一份 test_main.py（测试文件本身未变）
    assert coord.sandbox.read_file("test_main.py").count("99") >= 1
