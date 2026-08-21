"""沙箱执行器的单元测试。"""
import sys

from app.sandbox import RunResult, Sandbox


def test_run_success():
    with Sandbox() as sb:
        result = sb.run_code('print("hello from sandbox")')
        assert result.ok
        assert "hello from sandbox" in result.stdout


def test_run_syntax_error():
    with Sandbox() as sb:
        result = sb.run_code("if True print('bad')")
        assert not result.ok
        assert result.returncode != 0
        assert "SyntaxError" in result.stderr


def test_run_timeout():
    with Sandbox(timeout=1) as sb:
        result = sb.run_code("while True:\n    pass\n")
        assert result.timed_out
        assert not result.ok


def test_run_file_missing():
    with Sandbox() as sb:
        result = sb.run_file("nope.py")
        assert not result.ok
        assert "不存在" in result.error


def test_write_and_list_files():
    with Sandbox() as sb:
        sb.write_file("main.py", "print(1)")
        sb.write_file("sub/a.txt", "x")
        files = sb.list_files()
        assert "main.py" in files
        assert "sub/a.txt" in files


def test_workspace_is_cleaned():
    sb = Sandbox()
    sb.write_file("main.py", "print(1)")
    path = sb.workspace
    assert path.exists()
    sb.cleanup()
    assert not path.exists()
