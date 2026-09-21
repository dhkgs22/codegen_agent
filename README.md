# 🤖 多智能体代码助手（项目 I）

> 2026 暑期 AI Agent 成长实践 · 项目 I：Coordinator + Code/Debug/Doc/Test 多智能体系统

输入一句自然语言，系统自动帮你：**写代码 → 沙箱编译运行 → 失败自动修复（循环）→ 生成 README → 自动测试**。

支持 **Python / C / C++ / Go / Java** 五种语言，一条命令切换。

## ✨ 特性

- **多语言支持**：Python / C / C++ / Go / Java，`--lang` 一行切换
  - 编译型语言自动编译（gcc / g++ / go build / javac）后再运行，产物缓存复用
  - 每种语言的提示词、编译器报错解析、入口文件名都由「语言档案」统一管理
- **Coordinator 编排**：总控调度，全流程事件流实时可见
- **Code Agent**：根据任务生成目标语言的可运行程序
- **Debug Agent**：沙箱隔离运行，失败则把报错喂回 LLM 自动修复（至多 N 轮）
  - **结构化错误诊断**：Python 解析 traceback，C/C++/Go/Java 解析编译器报错（`file:line: error: ...`），提取文件/行号/消息
  - **修复历史记忆**：每轮失败原因累积传入，避免重复踩坑
- **Test Agent**：运行通过后自动生成测试并在沙箱中跑通验证
  - Python → 生成 pytest 测试
  - C/C++/Go/Java → 生成语言无关的**黑盒用例**（参数/stdin → 断言 stdout），编译一次逐条验证
- **Test→Debug 协作回环**：测试失败 → 协作消息反馈给 Debug → 修复 → 复用同一份测试复测
- **Doc Agent**：运行通过后自动生成 README.md（含该语言的编译/运行命令）
- **Harness 基础设施层**：统一管理沙箱 / 事件流 / 工具注册 / 配置 / 目标语言（`app/harness.py`）
- **LLM 抽象层**：默认 DeepSeek，接口可换 Claude（OpenAI 兼容）
- **三种使用方式**：CLI / FastAPI+SSE / Streamlit Web
- **Benchmark 评测**：18 个任务（覆盖 5 种语言）批量跑，输出成功率/耗时/轮次统计

## 🌐 支持的语言

| key | 语言 | 入口文件 | 编译/运行 | 自动测试 |
|---|---|---|---|---|
| `python` | Python | `main.py` | `python main.py` | pytest |
| `c` | C | `main.c` | `gcc -std=c11` | 黑盒用例 |
| `cpp` | C++ | `main.cpp` | `g++ -std=c++17` | 黑盒用例 |
| `go` | Go | `main.go` | `go build` | 黑盒用例 |
| `java` | Java | `Main.java` | `javac` + `java` | 黑盒用例 |

**依赖**：Python 解释器；生成 C 需 `gcc`，C++ 需 `g++`，Go 需 `go`，Java 需 JDK（`javac` + `java`）。
查看本机哪些语言可用：

```bash
python -m app.cli --list-langs
```

新增一种语言只需在 `app/languages.py` 的 `LANGUAGES` 里加一条档案，其它模块无需改动。

## 🚀 快速开始

### 1. 环境

```bash
# 创建虚拟环境并安装依赖（Windows）
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 配置 API Key
copy .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY
```

> 本机如果 pip 并发下载会被断，请逐个安装：`pip install httpx`、`pip install fastapi`……

### 2. 命令行使用

```bash
# 用真实 DeepSeek（默认 Python）
python -m app.cli "写一个计算斐波那契数列前 N 项的程序"

# 换个语言：C / C++ / Go / Java
python -m app.cli --lang c "写一个判断素数的程序"
python -m app.cli --lang cpp "写一个整数排序程序"
python -m app.cli --lang go "写一个词频统计程序"
python -m app.cli --lang java "写一个银行账户类"

# 查看支持的语言 + 本机工具链是否齐全
python -m app.cli --list-langs

# 用 Fake LLM（测试/演示，不花 token）
python -m app.cli --provider fake --rounds 2 "写一个 hello world"

# 输出 JSON 便于程序处理
python -m app.cli "写一个程序" --json

# 不自动生成并运行测试
python -m app.cli "写一个程序" --no-tests
```

### 3. Web 界面（推荐演示方式）

```bash
# 终端 1：起后端
.venv\Scripts\uvicorn app.main:app --port 8000

# 终端 2：起前端
.venv\Scripts\streamlit run ui/streamlit_app.py
```

浏览器打开 Streamlit 页面，输入任务，点「开始生成」，实时观看 Agent 工作过程。

## 🔧 API

| 端点 | 说明 |
|---|---|
| `GET /api/health` | 健康检查 |
| `GET /api/languages` | 支持的语言 + 本机工具链可用性 |
| `POST /api/run` | 同步执行流水线，返回完整结果 + 事件流 |
| `GET /api/run/stream?task=...` | SSE 流式执行，事件实时推送 |

`POST /api/run` 与 SSE 端点都接受 `language` 参数（`python` / `c` / `cpp` / `go` / `java`，默认 `python`）和可选的 `filename`（不给就按语言取默认入口文件）：

```bash
curl -X POST http://127.0.0.1:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"task":"写一个判断素数的程序","language":"c"}'
```

## 🧪 测试

```bash
.venv\Scripts\python -m pytest -q
```

使用 FakeClient 模拟 LLM，覆盖：沙箱运行、代码提取、修复循环、失败终止、CLI JSON、API、
traceback 解析、修复历史记忆、Test Agent、Harness 工具注册、Test→Debug 协作回环，
以及多语言部分（语言档案、各语言报错解析、C/C++/Go/Java 真实编译运行、黑盒测试）。

> 需要编译器的用例在缺工具链时自动跳过（`tests/test_languages.py` 里有 `skipif`），
> 所以本地没装 gcc/go/JDK 也能跑通 CI。

## 📊 Benchmark 评测

```bash
# 真实 DeepSeek，跑全部 18 个任务（覆盖 5 种语言）
python scripts/benchmark.py

# 只跑某个语言
python scripts/benchmark.py --lang c

# 机制验证（不花 token）
python scripts/benchmark.py --fake --limit 3
```

结果写入 `benchmark/results.md`，统计流水线成功率、结果正确率、平均耗时、平均修复轮次，
并**按语言分组**给出通过率。

## 🗂 目录结构

```
app/
  cli.py            # 命令行入口（--lang / --list-langs）
  main.py           # FastAPI（REST + SSE + /api/languages）
  config.py         # 配置
  events.py         # 事件模型 + EventBus
  languages.py      # ★ 语言档案注册表（Python/C/C++/Go/Java 的编译、运行、提示词、报错解析）
  llm/client.py     # LLM 抽象（DeepSeek / Fake）
  harness.py        # Harness 基础设施层（沙箱+事件+工具+配置+语言）
  sandbox/runner.py # 沙箱执行（按后缀分派语言，编译 + 运行 + 超时）
  sandbox/blackbox.py # 黑盒测试运行器（非 Python 语言的测试策略）
  agents/           # Code / Debug / Doc / Test Agent + Coordinator
benchmark/          # 评测任务集（tasks.py，18 个任务）+ 结果（results.md）
scripts/benchmark.py # 批量评测入口
ui/streamlit_app.py # Web 界面
tests/              # pytest 测试（含 test_languages.py）
wiki/               # 架构笔记（含 concepts/language-registry.md 多语言设计）
plan.md             # 项目预研文档
```

## 🔮 后续规划

- [x] GitHub Actions CI（push 触发 pytest，全绿）
- [x] 修复成功率 / 耗时的 benchmark 统计（见 `benchmark/results.md`）
- [x] 多语言支持：Python / C / C++ / Go / Java
- [ ] WebSocket 实时推送（目前用 SSE）
- [ ] 支持多文件项目 + 第三方依赖安装沙箱
- [ ] 更多语言（Rust / TypeScript / Kotlin……只需在 `app/languages.py` 加一条档案）

## 📄 License

本项目使用 [MIT License](LICENSE)。
