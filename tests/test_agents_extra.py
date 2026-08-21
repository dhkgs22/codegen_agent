"""B+C 新增功能的测试：traceback 解析、修复历史记忆、Test Agent。"""
import pytest

from app.agents import Coordinator, TestAgent
from app.agents.debug_agent import DebugAgent, parse_traceback
from app.llm import FakeClient
from app.sandbox import RunResult, Sandbox

TRACEBACK = '''Traceback (most recent call last):
  File "C:\\Users\\x\\main.py", line 5, in <module>
    undefined_func(n)
NameError: name 'undefined_func' is not defined
'''


def test_parse_traceback():
    d = parse_traceback(TRACEBACK)
    assert d["error_type"] == "NameError"
    assert d["line_no"] == 5
    assert "undefined_func" in d["message"]
    assert parse_traceback("") == {"error_type": "", "message": "", "line_no": 0, "file": ""}
    assert parse_traceback("普通错误文本")["error_type"] == ""


def test_debug_prompt_has_diagnosis_and_history():
    fake = FakeClient(responses=['```python\nprint("ok")\n```'])
    dbg = DebugAgent(fake, Sandbox())
    dbg.fix(
        "任务",
        "code",
        RunResult(returncode=1, stderr=TRACEBACK),
        history=[{"round": 1, "error_type": "NameError", "message": "undefined"}],
    )
    msg = fake.calls[0]["messages"][1]["content"]
    assert "[错误诊断]" in msg
    assert "NameError" in msg
    assert "修复历史" in msg
    assert "第 1 轮失败" in msg


def test_test_agent_runs_pytest():
    main_code = 'import sys\nn = int(sys.argv[1]) if len(sys.argv) > 1 else 5\nprint(n * 2)\n'
    test_code = (
        "```python\n"
        "import subprocess, sys, pathlib\n"
        "def run(*a):\n"
        '    return subprocess.run([sys.executable, "main.py", *a], capture_output=True, text=True, cwd=pathlib.Path(__file__).parent)\n'
        "def test_double():\n"
        '    assert "10" in run("5").stdout\n'
        "```"
    )
    sb = Sandbox()
    sb.write_file("main.py", main_code)
    fake = FakeClient(responses=[test_code])
    ta = TestAgent(fake, sb)
    info = ta.generate_tests("double", main_code)
    assert info["passed"] is True
    assert "passed" in info["summary"]
    assert "test_main.py" in sb.list_files()


def test_coordinator_pipeline_with_tests():
    GOOD = (
        "```python\n"
        "import sys\n"
        "n = int(sys.argv[1]) if len(sys.argv) > 1 else 5\n"
        "print(n * 2)\n"
        "```"
    )
    TEST = (
        "```python\n"
        "import subprocess, sys, pathlib\n"
        "def run(*a):\n"
        '    return subprocess.run([sys.executable, "main.py", *a], capture_output=True, text=True, cwd=pathlib.Path(__file__).parent)\n'
        "def test_double():\n"
        '    assert "10" in run("5").stdout\n'
        "```"
    )
    fake = FakeClient(responses=[GOOD, "# README", TEST])
    coord = Coordinator(llm=fake, max_rounds=3, enable_tests=True)
    result = coord.run("写一个把数字翻倍的程序")
    assert result.success
    assert result.tests_passed is True
    assert "test_main.py" in result.files
    assert any(e.kind == "test" for e in coord.bus.events())


def test_coordinator_tests_off_by_default_when_disabled():
    GOOD = "```python\nprint('hi')\n```"
    fake = FakeClient(responses=[GOOD, "# README"])
    coord = Coordinator(llm=fake, max_rounds=3, enable_tests=False)
    result = coord.run("hello")
    assert result.success
    assert result.tests_passed is None
