# 项目 I：Code/Debug/Doc 多智能体代码助手

> 2026 暑期 AI Agent 成长实践 · 项目预研文档（W4）

## 1. 项目定位

一个「会自己写代码、自己跑、自己修、自己写文档」的多智能体系统：
用户用自然语言描述一个 Python 小任务 → 系统自动生成代码、在沙箱中运行、
失败则自动修复（最多 N 轮），成功后自动生成 README 文档。

对应评分表「综合 9-10」档：多 Agent 编排（Coordinator / Code / Debug / Doc）+ Harness + CI/CD。

## 2. 目标架构

```
┌─────────────────────────────────────────────────────────┐
│  用户 (Streamlit Web 界面  /  CLI / REST API / SSE)        │
└───────────────────────────┬─────────────────────────────┘
                            │ 任务描述
                            ▼
                  ┌─────────────────────┐
                  │  Coordinator 编排器  │  ← 总控：调度各 Agent，维护事件流
                  └──────┬──────────────┘
                         │
        ┌────────────────┼───────────────────┐
        ▼                ▼                   ▼
  ┌──────────┐    ┌───────────┐       ┌───────────┐
  │ Code     │    │ Debug     │       │ Doc       │
  │ Agent    │    │ Agent     │       │ Agent     │
  │ 生成代码  │    │ 运行+修复  │       │ 生成README│
  └────┬─────┘    └─────┬─────┘       └─────┬─────┘
       │                │                   │
       ▼                ▼                   ▼
  ┌──────────────────────────┐        ┌───────────┐
  │  Sandbox 沙箱             │        │ workspace │
  │  subprocess 隔离执行       │        │ (代码仓库) │
  │  + 超时保护               │        └───────────┘
  └──────────────────────────┘
```

- **Coordinator**：解析任务 → 调 Code Agent → 循环调 Debug Agent → 成功后调 Doc Agent；发布事件流（供 Web/SSE/CLI 实时显示）。
- **Code Agent**：用 LLM 生成任务对应的 Python 代码，写入 workspace。
- **Debug Agent**：在沙箱中运行代码，若失败，把报错喂回 LLM 修复，循环至多 N 次。
- **Doc Agent**：运行通过后，生成 README.md（功能说明 + 用法 + 示例输出）。
- **LLM 抽象层**：默认 DeepSeek API（OpenAI 兼容），接口可换 Claude 等。
- **事件流**：每个阶段的关键输出以结构化事件发出，前端实时渲染。

## 3. 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 后端 API | FastAPI + Uvicorn | REST + SSE 流式 |
| Web 界面 | Streamlit | 快速搭建，输入任务 + 实时看进度 |
| 命令行 | Click（或 argparse） | `python -m app.cli "..."` |
| LLM | DeepSeek API（OpenAI 兼容）| provider 抽象，可切 Claude |
| 沙箱 | subprocess + tempfile | 隔离执行，超时保护 |
| 测试 | pytest | 含 FakeLLM 端到端测试 |
| CI | GitHub Actions | push 触发 pytest |

## 4. 数据流（一次完整运行）

1. 用户提交任务，如「写一个计算斐波那契数列前 N 项的程序」。
2. Coordinator 发出 `start` 事件，调 Code Agent。
3. Code Agent 返回代码，写入 `workspace/main.py`，发出 `code` 事件。
4. Debug Agent 用沙箱运行 `main.py`：
   - 成功 → 跳 6。
   - 失败（语法错/运行时错/超时）→ 将报错喂回 LLM 生成修复代码，回合 +1，回到 4。
5. 超过最大修复轮次仍未通过 → 标记失败，发出 `fail` 事件，终止。
6. Doc Agent 依据最终代码生成 `README.md`，发出 `doc` 事件。
7. Coordinator 发出 `done` 事件，返回结果（成功与否、产出的文件、事件列表）。

## 5. MVP 范围（W5，一周可完成）

- [x] LLM provider 抽象（DeepSeek / Fake）
- [x] Sandbox 沙箱执行 + 超时保护
- [x] Code / Debug / Doc 三 Agent
- [x] Coordinator 编排 + 事件流
- [x] CLI：`python -m app.cli "任务"`
- [x] pytest 端到端测试（FakeLLM，不花 token）
- [ ] FastAPI + SSE
- [ ] Streamlit 界面
- [ ] GitHub Actions CI
- [ ] Bug 轮次修复 + 超时强化

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| LLM 生成代码质量不稳定 | Debug Agent 自动修复 + 沙箱跑通才算过 |
| 无限循环/超时 | 沙箱强制 timeout，超时算失败并提示 |
| 缺 API key | .env 配置；测试用 FakeLLM 不依赖 key |
| 跑太久 | 每个 LLM 调用设超时，最大修复轮次限制 |
