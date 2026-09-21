"""多语言支持测试：语言档案、代码提取、各语言报错解析、编译运行、黑盒测试。

需要真实编译器的用例在缺少工具链时自动跳过（CI 上不必装全套 gcc/go/jdk）。
"""
import shutil

import pytest

from app.agents import CodeAgent, Coordinator
from app.languages import (
    LANGUAGES,
    UnknownLanguageError,
    language_from_filename,
    resolve_language,
    toolchain_status,
)
from app.llm import FakeClient
from app.sandbox import Sandbox
from app.sandbox.blackbox import Case, parse_cases, run_cases, value_present
from app.agents.code_agent import extract_code

HAS_GCC = shutil.which("gcc") is not None
HAS_GPP = shutil.which("g++") is not None
HAS_GO = shutil.which("go") is not None
HAS_JAVAC = shutil.which("javac") is not None and shutil.which("java") is not None


# ---------------------------------------------------------------- 语言档案
def test_registry_has_five_languages():
    assert set(LANGUAGES) == {"python", "c", "cpp", "go", "java"}
    assert LANGUAGES["python"].entry == "main.py"
    assert LANGUAGES["c"].entry == "main.c"
    assert LANGUAGES["cpp"].entry == "main.cpp"
    assert LANGUAGES["go"].entry == "main.go"
    # Java 的类名必须与文件名一致，因此入口固定为 Main.java
    assert LANGUAGES["java"].entry == "Main.java"


def test_resolve_language_aliases_and_errors():
    assert resolve_language(None).key == "python"
    assert resolve_language("").key == "python"
    assert resolve_language("c++").key == "cpp"
    assert resolve_language("golang").key == "go"
    assert resolve_language("Java").key == "java"
    with pytest.raises(UnknownLanguageError):
        resolve_language("klingon")


def test_language_from_filename():
    assert language_from_filename("main.c").key == "c"
    assert language_from_filename("Main.java").key == "java"
    assert language_from_filename("main.go").key == "go"
    # 认不出的后缀回退到默认语言
    assert language_from_filename("data.csv").key == "python"
    assert language_from_filename("data.csv", default="go").key == "go"


def test_artifact_and_commands():
    c = LANGUAGES["c"]
    assert c.needs_build
    # 编译产物按平台带 .exe 后缀
    assert c.artifact_name.startswith("main")
    assert not LANGUAGES["python"].needs_build
    assert LANGUAGES["python"].artifact_name == ""
    # 文档用命令不含临时目录路径
    hint = LANGUAGES["c"].build_hint()
    assert hint.startswith("gcc -std=c11") and "main.c" in hint and "-o main" in hint
    assert "temp" not in hint and "\\" not in hint
    assert LANGUAGES["java"].run_hint() == "java Main"
    assert LANGUAGES["python"].run_hint() == "python main.py"
    assert LANGUAGES["python"].build_hint() == ""


def test_toolchain_status_shape():
    rows = {r["key"]: r for r in toolchain_status()}
    assert set(rows) == set(LANGUAGES)
    assert rows["python"]["available"] is True
    assert rows["python"]["test_strategy"] == "pytest"
    assert rows["go"]["test_strategy"] == "blackbox"


# ---------------------------------------------------------------- 代码提取
def test_extract_code_prefers_matching_language():
    text = (
        "先说明一下思路。\n\n"
        "```python\nprint('这是 Python 片段')\n```\n\n"
        "正式答案：\n\n"
        "```c\nint main(void) { return 0; }\n```\n"
    )
    assert extract_code(text, "c") == "int main(void) { return 0; }"
    assert extract_code(text, "python") == "print('这是 Python 片段')"


def test_extract_code_fallbacks():
    # 没有语言标记 → 取最长代码块
    assert extract_code("```\nshort\n```\n```\nlonger body\n```") == "longer body"
    # 完全没有代码块 → 整段当代码
    assert extract_code("print(1)") == "print(1)"
    assert extract_code("") == ""


def test_code_agent_prompt_is_language_specific():
    fake = FakeClient(["```go\npackage main\nfunc main() {}\n```"])
    agent = CodeAgent(fake)
    code = agent.generate("写个程序", language="go")
    assert code.startswith("package main")
    system = fake.calls[0]["messages"][0]["content"]
    assert "Go 工程师" in system
    assert "```go" in system


# ---------------------------------------------------------------- 报错解析
def test_parse_c_error():
    from app.languages import LANGUAGES as L

    stderr = (
        "main.c: In function 'main':\n"
        "main.c:7:5: error: expected ';' before '}' token\n"
        "     }\n"
        "     ^\n"
    )
    diag = L["c"].parse_error(stderr)
    assert diag["error_type"] == "CompileError"
    assert diag["line_no"] == 7
    assert "expected ';'" in diag["message"]


def test_parse_java_error():
    stderr = "Main.java:5: error: ';' expected\n        int x = 1\n                ^\n1 error\n"
    diag = LANGUAGES["java"].parse_error(stderr)
    assert diag["line_no"] == 5
    assert "';' expected" in diag["message"]


def test_parse_go_error():
    stderr = "# command-line-arguments\n./main.go:8:2: undefined: fmtPrintln\n"
    diag = LANGUAGES["go"].parse_error(stderr)
    assert diag["line_no"] == 8
    assert "undefined" in diag["message"]


def test_parse_linker_error_falls_back_to_error_line():
    stderr = (
        "/tmp/cc1.o:main.c:(.text+0x1a): undefined reference to `foo'\n"
        "collect2: error: ld returned 1 exit status\n"
    )
    diag = LANGUAGES["c"].parse_error(stderr)
    assert "undefined reference" in diag["message"]


def test_python_parser_still_used_for_python():
    diag = LANGUAGES["python"].parse_error('File "main.py", line 3\nNameError: bad\n')
    assert diag["error_type"] == "NameError"
    assert diag["line_no"] == 3


# ---------------------------------------------------------------- 沙箱编译运行
@pytest.mark.skipif(not HAS_GCC, reason="未安装 gcc")
def test_sandbox_runs_c():
    code = (
        "#include <stdio.h>\n#include <stdlib.h>\n"
        "int main(int argc, char** argv) {\n"
        "    int n = argc > 1 ? atoi(argv[1]) : 5;\n"
        '    printf("%d\\n", n * 2);\n'
        "    return 0;\n}\n"
    )
    with Sandbox() as sb:
        sb.write_file("main.c", code)
        res = sb.run_file("main.c", ["7"])
        assert res.ok, res.stderr
        assert res.stdout.strip() == "14"
        assert res.stage == "run"


@pytest.mark.skipif(not HAS_GPP, reason="未安装 g++")
def test_sandbox_runs_cpp():
    code = (
        "#include <iostream>\n#include <string>\n"
        "int main(int argc, char** argv) {\n"
        '    std::string s = argc > 1 ? argv[1] : "ab";\n'
        "    std::cout << s.size() << std::endl;\n"
        "    return 0;\n}\n"
    )
    with Sandbox() as sb:
        sb.write_file("main.cpp", code)
        res = sb.run_file("main.cpp", ["abcd"])
        assert res.ok, res.stderr
        assert res.stdout.strip() == "4"


@pytest.mark.skipif(not HAS_GO, reason="未安装 go")
def test_sandbox_runs_go():
    code = (
        "package main\n\n"
        'import ("fmt"\n"os"\n"strconv")\n\n'
        "func main() {\n"
        "\tn := 5\n"
        "\tif len(os.Args) > 1 {\n\t\tn, _ = strconv.Atoi(os.Args[1])\n\t}\n"
        "\tfmt.Println(n * 2)\n}\n"
    )
    with Sandbox() as sb:
        sb.write_file("main.go", code)
        res = sb.run_file("main.go", ["6"])
        assert res.ok, res.stderr
        assert res.stdout.strip() == "12"


@pytest.mark.skipif(not HAS_JAVAC, reason="未安装 JDK")
def test_sandbox_runs_java():
    code = (
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        int n = args.length > 0 ? Integer.parseInt(args[0]) : 5;\n"
        "        System.out.println(n * 2);\n"
        "    }\n}\n"
    )
    with Sandbox() as sb:
        sb.write_file("Main.java", code)
        res = sb.run_file("Main.java", ["8"])
        assert res.ok, res.stderr
        assert res.stdout.strip() == "16"


@pytest.mark.skipif(not HAS_GCC, reason="未安装 gcc")
def test_compile_error_reports_build_stage():
    with Sandbox() as sb:
        sb.write_file("main.c", "int main(void) { return 0 }")  # 缺分号
        res = sb.run_file("main.c")
        assert not res.ok
        assert res.stage == "build"
        assert "编译" in res.summary


@pytest.mark.skipif(not HAS_GCC, reason="未安装 gcc")
def test_build_is_cached_until_source_changes():
    with Sandbox() as sb:
        sb.write_file("main.c", "int main(void) { return 0; }")
        first = sb.build_file("main.c")
        assert first is not None and first.ok
        second = sb.build_file("main.c")
        assert second is not None and "复用" in second.stdout
        # 改了源码 → 重新编译
        sb.write_file("main.c", "int main(void) { return 1; }")
        third = sb.build_file("main.c")
        assert third is not None and "复用" not in third.stdout


def test_missing_toolchain_gives_actionable_error(monkeypatch):
    """本机没装编译器时，报错要说清缺什么，而不是抛异常。"""
    from app.languages import Language

    monkeypatch.setattr(
        Language, "missing_tools", lambda self: ["gcc"] if self.key == "c" else []
    )
    with Sandbox() as sb:
        sb.write_file("main.c", "int main(void) { return 0; }")
        res = sb.run_file("main.c")
        assert not res.ok
        assert "gcc" in res.error
        assert "C" in res.error


# ---------------------------------------------------------------- 黑盒测试
def test_parse_cases_from_llm_reply():
    reply = (
        "下面是测试用例：\n\n"
        "```json\n"
        '{"cases": [\n'
        '  {"name": "正常", "args": ["5"], "expect_contains": ["10"]},\n'
        '  {"name": "边界", "args": [0], "expect_contains": 0, "expect_not_contains": "99"}\n'
        "]}\n```\n"
    )
    cases = parse_cases(reply)
    assert len(cases) == 2
    assert cases[0].args == ["5"]
    assert cases[0].expect_contains == ["10"]
    # 类型松散也要能容错：数字会被转成字符串，单值会被包成列表
    assert cases[1].args == ["0"]
    assert cases[1].expect_contains == ["0"]
    assert cases[1].expect_not_contains == ["99"]


def test_parse_cases_returns_empty_on_garbage():
    assert parse_cases("我不会写测试") == []
    assert parse_cases("") == []


def test_blackbox_detects_wrong_output():
    cases = [Case(name="翻倍", args=["5"], expect_contains=["10"])]
    with Sandbox() as sb:
        sb.write_file("main.py", "print(11)\n")
        info = run_cases(sb, "main.py", cases)
        assert info["passed"] is False
        assert "1 failed" in info["summary"]
        assert "缺少" in info["output"]


def test_blackbox_passes_on_correct_output():
    cases = [
        Case(name="翻倍", args=["5"], expect_contains=["10"]),
        Case(name="排除错误值", args=["5"], expect_not_contains=["11"]),
    ]
    with Sandbox() as sb:
        sb.write_file("main.py", "import sys\nn=int(sys.argv[1]) if len(sys.argv)>1 else 5\nprint(n*2)\n")
        info = run_cases(sb, "main.py", cases)
        assert info["passed"] is True
        assert info["cases_passed"] == 2
        assert "2 passed" in info["summary"]


def test_blackbox_stdin():
    cases = [Case(name="读标准输入", stdin="7\n", expect_contains=["14"])]
    with Sandbox() as sb:
        sb.write_file("main.py", "print(int(input()) * 2)\n")
        assert run_cases(sb, "main.py", cases)["passed"] is True


def test_value_present_uses_word_boundaries():
    """expect_not_contains 的匹配语义：按独立的值，而不是朴素子串。"""
    assert value_present("2\n3\n5\n11\n19", "1") is False  # 11/19 里的 1 不算
    assert value_present("2\n3\n5\n11\n19", "11") is True
    assert value_present("hello world", "hello") is True
    assert value_present("helloworld", "hello") is False
    assert value_present("max=8 min=2 avg=5.0", "5.0") is True
    assert value_present("", "1") is False
    assert value_present("49\n2", "49") is True


def test_blackbox_not_contains_not_fooled_by_substring():
    """真实踩过的坑：用例写「不应出现 1」，输出里的 11/19/29 不能被误判为违规。

    朴素子串匹配会把这份正确的素数程序判为失败，进而触发一次无意义的
    LLM 修复轮次——这是最贵的误报。
    """
    cases = [
        Case(
            name="n=30 素数",
            args=["30"],
            expect_contains=["2", "29"],
            expect_not_contains=["1", "9", "21", "27", "30"],
        )
    ]
    program = "print('\\n'.join(str(i) for i in [2,3,5,7,11,13,17,19,23,29]))\n"
    with Sandbox() as sb:
        sb.write_file("main.py", program)
        info = run_cases(sb, "main.py", cases)
        assert info["passed"] is True, info["output"]


def test_blackbox_not_contains_still_catches_real_violation():
    """放宽边界不等于放水：真的输出了不该有的值必须判失败。"""
    cases = [Case(name="不该有 49", expect_contains=["2"], expect_not_contains=["49"])]
    with Sandbox() as sb:
        sb.write_file("main.py", "print('2\\n49')\n")
        info = run_cases(sb, "main.py", cases)
        assert info["passed"] is False
        assert "49" in info["output"]


# ---------------------------------------------------------------- 端到端
C_CODE = """```c
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char** argv) {
    int n = argc > 1 ? atoi(argv[1]) : 5;
    printf("%d\\n", n * 2);
    return 0;
}
```"""

C_SPEC = (
    "```json\n"
    '{"cases": [\n'
    '  {"name": "n=5", "args": ["5"], "expect_contains": ["10"]},\n'
    '  {"name": "默认值", "args": [], "expect_contains": ["10"]}\n'
    "]}\n```"
)


@pytest.mark.skipif(not HAS_GCC, reason="未安装 gcc")
def test_coordinator_end_to_end_c_with_blackbox_tests():
    fake = FakeClient([C_CODE, "# README\n翻倍程序（C 语言）。", C_SPEC])
    coord = Coordinator(llm=fake, max_rounds=3, enable_tests=True, language="c", keep_workspace=True)
    result = coord.run("写一个把数字翻倍的程序")

    assert result.success
    assert result.language == "c"
    assert result.filename == "main.c"
    assert "main.c" in result.files
    assert "test_spec.json" in result.files
    assert result.tests_passed is True
    assert result.final_output.strip() == "10"


@pytest.mark.skipif(not HAS_GCC, reason="未安装 gcc")
def test_coordinator_c_fix_loop_repairs_compile_error():
    bad = C_CODE.replace('printf("%d\\n", n * 2);', 'printf("%d\\n", n * 2)')  # 缺分号 → 编译失败
    fake = FakeClient([bad, C_CODE, "# README"])
    coord = Coordinator(llm=fake, max_rounds=3, enable_tests=False, language="c")
    result = coord.run("写一个把数字翻倍的程序")

    assert result.success
    assert result.rounds_used == 2  # 第一次编译失败，修复后第二次通过
    # 修复提示词里带上了编译阶段的结构化诊断
    debug_prompt = [c for c in fake.calls if "调试专家" in c["messages"][0]["content"]][0]
    assert "[错误诊断]（编译阶段）" in debug_prompt["messages"][1]["content"]


@pytest.mark.skipif(not HAS_JAVAC, reason="未安装 JDK")
def test_coordinator_end_to_end_java():
    code = (
        "```java\n"
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        int n = args.length > 0 ? Integer.parseInt(args[0]) : 5;\n"
        "        System.out.println(n * 2);\n"
        "    }\n}\n```"
    )
    spec = (
        "```json\n"
        '{"cases": [{"name": "n=6", "args": ["6"], "expect_contains": ["12"]}]}\n'
        "```"
    )
    fake = FakeClient([code, "# README", spec])
    coord = Coordinator(llm=fake, max_rounds=3, enable_tests=True, language="java")
    result = coord.run("写一个把数字翻倍的程序")

    assert result.success, result.error
    assert result.filename == "Main.java"
    assert result.tests_passed is True


def test_coordinator_rejects_unknown_language():
    from app.languages import UnknownLanguageError

    coord = Coordinator(llm=FakeClient([]), language=None)
    with pytest.raises(UnknownLanguageError):
        coord.run("任务", language="klingon")


@pytest.mark.skipif(not HAS_GO, reason="未安装 go")
def test_coordinator_language_inferred_from_filename():
    """不传 language、只传 main.go 时，语言应由文件后缀推断为 Go。"""
    code = '```go\npackage main\n\nimport "fmt"\n\nfunc main() { fmt.Println(10) }\n```'
    fake = FakeClient([code, "# README"])
    coord = Coordinator(llm=fake, max_rounds=1, enable_tests=False)
    result = coord.run("写个程序", filename="main.go")
    assert result.success, result.error
    assert result.language == "go"
    assert result.filename == "main.go"


def test_unsupported_language_fails_before_running():
    """本机缺工具链时应在启动前就失败，并说清缺什么。"""
    from app.languages import Language

    coord = Coordinator(llm=FakeClient([]), language="go", enable_tests=False)
    original = Language.missing_tools
    Language.missing_tools = lambda self: ["go"] if self.key == "go" else []  # type: ignore[method-assign]
    try:
        result = coord.run("写个程序")
    finally:
        Language.missing_tools = original  # type: ignore[method-assign]
    assert not result.success
    assert "go" in result.error


# ---------------------------------------------------------------- API
def test_api_languages_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/api/languages")
        assert resp.status_code == 200
        body = resp.json()
        keys = {row["key"] for row in body["languages"]}
        assert keys == set(LANGUAGES)
        assert body["default"] == "python"


def test_api_rejects_unknown_language():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/api/run", json={"task": "任务", "language": "klingon"})
        assert resp.status_code == 400
        assert "不支持的语言" in resp.json()["detail"]


def test_cli_list_langs(capsys):
    from app.cli import main

    assert main(["--list-langs"]) == 0
    out = capsys.readouterr().out
    for key in LANGUAGES:
        assert key in out
