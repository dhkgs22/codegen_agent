# 语言档案：多语言支持的设计

> 对应实现 `app/languages.py` · 沙箱 `app/sandbox/runner.py` · 黑盒测试 `app/sandbox/blackbox.py`

## 问题

项目一开始只支持 Python，语言相关的假设散落在各处：

- 沙箱写死 `python main.py`
- Debug Agent 只会解析 Python traceback（`File "x.py", line 5`）
- Test Agent 只会生成 pytest 测试
- 提示词写死「你是一名资深 Python 工程师」
- 入口文件名 `main.py` 出现在 Coordinator、API、CLI、benchmark 里

要支持 C / C++ / Go / Java，如果每加一种语言就在这些地方各打一个 `if`，
就会变成 5 种语言 × 6 个模块 = 30 处分支，无法维护。

## 方案：把「语言相关的一切」抽成一张表

```python
@dataclass(frozen=True)
class Language:
    key: str              # "c"
    display: str          # "C"
    ext: str              # ".c"
    fence: str            # markdown 代码块标记
    entry: str            # 默认入口文件 "main.c"
    compile_tpl: tuple | None   # ("gcc", "-std=c11", "{src}", "-o", "{out}", "-lm")
    run_tpl: tuple              # ("{out}",)
    tools: tuple                # ("gcc",)  ← 本机工具链自检
    test_strategy: str          # "pytest" | "blackbox"
    rules: str                  # Code Agent 的语言特有要求
    debug_rules: str            # Debug Agent 的语言特有要求
    error_parser: str           # "python" | "gcc" | "javac" | "go"
```

所有语言收在 `LANGUAGES` 字典里。**其它模块一律按 key 取档案，不再出现语言判断。**

| key | 语言 | 入口 | 编译 | 运行 | 测试策略 |
|---|---|---|---|---|---|
| python | Python | main.py | — | `python main.py` | pytest |
| c | C | main.c | `gcc -std=c11` | `main.exe` | 黑盒 |
| cpp | C++ | main.cpp | `g++ -std=c++17` | `main.exe` | 黑盒 |
| go | Go | main.go | `go build` | `main.exe` | 黑盒 |
| java | Java | Main.java | `javac -d .` | `java -cp . Main` | 黑盒 |

### 三个容易被忽略的差异点

1. **Java 的入口文件名不是自由选择的**：`public class Main` 必须放在 `Main.java`，
   所以档案里 `entry="Main.java"`，运行命令用 `{stem}` 占位符取类名。
2. **编译产物带平台后缀**：Windows 下 gcc/g++/go 产出 `.exe`，Linux 下没有。
   `artifact_name` 按 `os.name` 决定。
3. **报错格式完全不同**，各自一个正则：

   | 语言 | 报错样例 |
   |---|---|
   | Python | `File "main.py", line 5` + `NameError: ...` |
   | C/C++ | `main.c:7:5: error: expected ';' before '}' token` |
   | Java | `Main.java:5: error: ';' expected` |
   | Go | `./main.go:8:2: undefined: fmtPrintln` |

   链接期错误（`undefined reference to ...`）没有 `file:line` 结构，
   兜底取第一条含 error 关键字的行——比取最后一行（往往是 `collect2` 的总结）有用。

## 沙箱怎么分派

`Sandbox` 按**文件后缀**取档案，调用方不需要说明语言：

```python
sb.write_file("main.c", code)
sb.run_file("main.c")        # → gcc 编译 → 运行 main.exe
```

`RunResult.stage` 区分 `build` / `run` 两个阶段，于是 Debug Agent 能说出
「编译阶段出错」还是「运行阶段出错」，提示词里的诊断信息也更准。

编译产物按**源码内容 hash** 缓存：同一份代码不重复编译，
所以黑盒测试「编译一次、跑 N 条用例」不会触发 N 次 gcc。

## 测试策略：为什么非 Python 用黑盒用例

pytest 只适用于 Python。C/C++/Go/Java 各有测试框架，但：

- JUnit 需要额外的 jar 包，沙箱里未必有；
- C/C++ 没有事实标准，引入 CUnit/GoogleTest 成本很高。

而本项目的测试目标其实很明确——**「程序对给定输入产生正确输出」**，
这正是黑盒测试覆盖的部分。于是：

```
Test Agent 生成语言无关的 JSON 用例集
   → 沙箱编译一次
   → 逐条用 命令行参数/stdin 调用程序，断言 stdout
```

```json
{"cases": [
  {"name": "n=10", "args": ["10"], "expect_contains": ["2", "3", "5", "7"],
   "expect_not_contains": ["9"], "expect_exit_code": 0}
]}
```

好处是所有语言共用同一套机制、不需要额外依赖、且验证的是**真实的编译产物**。
两种策略对外返回同样的结果结构，所以 Coordinator 的 Test→Debug 协作回环
完全不需要知道底层用的是哪种测试。

## 如何新增一种语言

只需在 `LANGUAGES` 加一条档案（以 Rust 为例）：

```python
"rust": Language(
    key="rust", display="Rust", ext=".rs", fence="rust", entry="main.rs",
    compile_tpl=("rustc", "{src}", "-o", "{out}"),
    run_tpl=("{out}",),
    tools=("rustc",),
    rules="3. 只写一个 .rs 文件，用 std::env::args() 读参数并提供默认值……",
    debug_rules="4. 编译报错优先看行号……",
    error_parser="gcc",   # rustc 的报错格式与 gcc 类似
),
```

CLI（`--lang rust`）、API、UI 的语言下拉、benchmark 都会自动识别，**其它文件一行都不用改**。

## 缺工具链怎么办

不静默失败，也不抛异常：

- `python -m app.cli --list-langs` 列出每种语言在本机是否可用、缺哪个可执行文件；
- `GET /api/languages` 给前端同样的信息（UI 会禁用没装工具链的语言）；
- 流水线**启动前**就自检，缺 `gcc` 时直接返回
  「本机缺少 gcc，无法编译/运行 C 代码。请安装后重试，或改用其它语言」，
  而不是让 gcc 的 `FileNotFoundError` 冒到用户面前；
- benchmark 会提前列出「因缺工具链预计会失败」的任务。

## 代价与取舍

- **黑盒测试的覆盖面比单元测试窄**：只能验证输入输出，测不到内部结构。
  对「LLM 生成的单个可执行程序」这个场景是合适的取舍；如果以后要支持多文件项目，
  再考虑引入各语言的原生测试框架。
- **Python 路径完全没动**：pytest 策略、提示词、文件名都保持原样，
  既有 25 个测试全绿，避免「加功能顺手改坏老功能」。
- **`-w` 关掉了 gcc 警告**：避免警告噪音干扰 LLM 修复，代价是看不到潜在问题；
  README 里生成文档时也会说明这一点。
