# 🤖 多智能体代码助手（项目 I）

> 2026 暑期 AI Agent 成长实践 · 项目 I：Coordinator + Code/Debug/Doc 多智能体系统

输入一句自然语言，系统自动帮你：**写代码 → 沙箱运行 → 失败自动修复（循环）→ 生成 README**。

## ✨ 特性

- **Coordinator 编排**：总控调度，全流程事件流实时可见
- **Code Agent**：根据任务生成可运行的 Python 程序
- **Debug Agent**：沙箱隔离运行，失败则把报错喂回 LLM 自动修复（至多 N 轮）
- **Doc Agent**：运行通过后自动生成 README.md
- **LLM 抽象层**：默认 DeepSeek，接口可换 Claude（OpenAI 兼容）
- **三种使用方式**：CLI / FastAPI+SSE / Streamlit Web

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

使用 FakeClient 模拟 LLM，覆盖：沙箱运行、代码提取、修复循环、失败终止、CLI JSON、API。

## 🗂 目录结构

```
app/
  cli.py            # 命令行入口
  main.py           # FastAPI（REST + SSE）
  config.py         # 配置
  events.py         # 事件模型 + EventBus
  llm/client.py     # LLM 抽象（DeepSeek / Fake）
  sandbox/runner.py # 沙箱执行（隔离 + 超时）
  agents/           # Code / Debug / Doc Agent + Coordinator
ui/streamlit_app.py # Web 界面
tests/              # pytest 测试
plan.md             # 项目预研文档
```

## 🔮 后续规划（W6-W7）

- [ ] GitHub Actions CI（push 触发 pytest）
- [ ] WebSocket 实时推送（目前用 SSE）
- [ ] Bug 轮次修复数 / 成功率的 benchmark 统计
- [ ] 支持多文件项目 + 第三方依赖安装沙箱

## 📄 License

本项目使用 [MIT License](LICENSE)。
