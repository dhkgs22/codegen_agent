# 🤖 多智能体代码助手（项目 I）

> 2026 暑期 AI Agent 成长实践 · 项目 I：Coordinator + Code/Debug/Doc/Test 多智能体系统

输入一句自然语言，系统自动帮你：**写代码 → 沙箱运行 → 失败自动修复（循环）→ 生成 README → 自动测试**。

## ✨ 特性

- **Coordinator 编排**：总控调度，全流程事件流实时可见
- **Code Agent**：根据任务生成可运行的 Python 程序
- **Debug Agent**：沙箱隔离运行，失败则把报错喂回 LLM 自动修复（至多 N 轮）
  - **结构化错误诊断**：解析 traceback 提取错误类型/行号，修复更精准
  - **修复历史记忆**：每轮失败原因累积传入，避免重复踩坑
- **Test Agent**：运行通过后自动生成 pytest 测试并在沙箱中跑通验证
- **Test→Debug 协作回环**：测试失败 → 协作消息反馈给 Debug → 修复 → 复用同一份测试复测
- **Doc Agent**：运行通过后自动生成 README.md
- **Harness 基础设施层**：统一管理沙箱 / 事件流 / 工具注册 / 配置（`app/harness.py`）
- **LLM 抽象层**：默认 DeepSeek，接口可换 Claude（OpenAI 兼容）
- **三种使用方式**：CLI / FastAPI+SSE / Streamlit Web
- **Benchmark 评测**：10 个任务批量跑，输出成功率/耗时/轮次统计

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
# 用真实 DeepSeek
python -m app.cli "写一个计算斐波那契数列前 N 项的程序"

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
| `POST /api/run` | 同步执行流水线，返回完整结果 + 事件流 |
| `GET /api/run/stream?task=...` | SSE 流式执行，事件实时推送 |

## 🧪 测试

```bash
.venv\Scripts\python -m pytest -q
```

使用 FakeClient 模拟 LLM，覆盖：沙箱运行、代码提取、修复循环、失败终止、CLI JSON、API、
traceback 解析、修复历史记忆、Test Agent、Harness 工具注册、Test→Debug 协作回环。

## 📊 Benchmark 评测

```bash
# 真实 DeepSeek，跑全部 10 个任务
python scripts/benchmark.py

# 机制验证（不花 token）
python scripts/benchmark.py --fake --limit 3
```

结果写入 `benchmark/results.md`，统计流水线成功率、结果正确率、平均耗时、平均修复轮次。

## 🗂 目录结构

```
app/
  cli.py            # 命令行入口
  main.py           # FastAPI（REST + SSE）
  config.py         # 配置
  events.py         # 事件模型 + EventBus
  llm/client.py     # LLM 抽象（DeepSeek / Fake）
  harness.py        # Harness 基础设施层（沙箱+事件+工具+配置）
  sandbox/runner.py # 沙箱执行（隔离 + 超时）
  agents/           # Code / Debug / Doc / Test Agent + Coordinator
benchmark/          # 评测任务集（tasks.py）+ 结果（results.md）
scripts/benchmark.py # 批量评测入口
ui/streamlit_app.py # Web 界面
tests/              # pytest 测试
plan.md             # 项目预研文档
```

## 🔮 后续规划

- [x] GitHub Actions CI（push 触发 pytest，全绿）
- [x] 修复成功率 / 耗时的 benchmark 统计（见 `benchmark/results.md`）
- [ ] WebSocket 实时推送（目前用 SSE）
- [ ] 支持多文件项目 + 第三方依赖安装沙箱

## 📄 License

本项目使用 [MIT License](LICENSE)。
