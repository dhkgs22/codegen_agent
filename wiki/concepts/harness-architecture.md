# Harness 架构：多智能体的统一基础设施

> 任务书 CS 项目「Harness 架构」交付文档 · 对应实现 `app/harness.py`

## 是什么

Harness 是承载所有 Agent 运行的**基础设施层**。它把每个 Agent 都要用的公共设施
（隔离执行、事件流、工具、配置）收口到一个对象里，Agent 不再各自创建资源，
而是统一从 Harness 获取。Coordinator 持有一个 Harness，分发给 Code / Debug /
Doc / Test 四个 Agent。

## 组成

```
┌─────────────────────────────────────────────┐
│                 Harness                      │
│                                              │
│   ┌──────────────┐   ┌──────────────────┐    │
│   │   Sandbox    │   │   EventBus       │    │
│   │ 隔离执行环境  │   │ 事件流实时推送    │    │
│   │ 临时目录/超时 │   │ CLI/SSE/Web 渲染 │    │
│   └──────────────┘   └──────────────────┘    │
│   ┌──────────────┐   ┌──────────────────┐    │
│   │ ToolRegistry │   │    Settings      │    │
│   │ 工具注册表    │   │  API Key/轮次/超时 │   │
│   └──────────────┘   └──────────────────┘    │
└─────────────────────────────────────────────┘
          ▲            ▲           ▲
          │            │           │
   CodeAgent     DebugAgent    Doc/TestAgent
```

- **Sandbox**：subprocess + 临时目录 + 超时保护，强制子进程 UTF-8 输出，
  保证 LLM 生成的任意代码都在隔离环境里安全运行。
- **EventBus**：所有 Agent 通过 `emit` 发布事件（start/code/run/fix/doc/test/msg/done），
  CLI、SSE、Streamlit 实时渲染，让「协作过程可见」。
- **ToolRegistry**：把沙箱能力注册成可调用工具——`run_python`、`read_file`、
  `write_file`、`list_files`。新增工具只需 `register(name, fn, description)`。
- **Settings**：API Key、超时、最大修复轮次等全局配置统一入口。

## Agent 如何接入 Harness

```python
coordinator = Coordinator(llm=llm)     # 内部自动创建 Harness
# 每个 Agent 构造时传入 harness，统一获取基础设施：
code_agent   = CodeAgent(llm, harness=harness)
debug_agent  = DebugAgent(llm, harness=harness, max_rounds=3)
test_agent   = TestAgent(llm, harness=harness)
```

Agent 内通过 `harness.run_file(...)` 执行、`harness.emit(...)` 发布事件。
新增 Agent / 新工具时只需扩展 Harness，其余模块不动。

## 为什么需要 Harness

1. **单一职责**：Agent 专注业务逻辑（生成/修复/文档/测试），不关心资源管理。
2. **可测试**：测试时用 FakeClient + 临时沙箱，不消耗真实 token。
3. **可观测**：事件流贯穿全链路，任何一步都能被前端实时看到。
4. **可扩展**：加一个「审查 Agent」只需新增类 + 注册，Harness 层零改动。

## 与 Sub-Agent 调度、CI/CD 的关系

- **Sub-Agent 调度**：Coordinator 负责任务分解与调度，Test→Debug 通过
  `msg` 协作消息回环（见 `wiki/agent-architecture.md`）。
- **CI/CD**：`.github/workflows/ci.yml` 每次 push 自动跑 pytest，
  验证 Harness 与四个 Agent 的改动不会破坏既有功能。
