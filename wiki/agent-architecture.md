# 多智能体架构笔记

> Obsidian 知识库 · W4 预研记录

## 一句话

任务书项目 I：Coordinator 编排三个各司其职的 Agent（Code / Debug / Doc），
让「写代码→运行→修复→文档」全流程自动化。

## 三个 Agent 的分工

| Agent | 职责 | 输入 → 输出 |
|---|---|---|
| Code Agent | 生成初始代码 | 任务描述 → Python 代码 |
| Debug Agent | 运行代码，失败则修复 | 代码 + 报错 → 修复后代码 |
| Doc Agent | 生成文档 | 代码 + 运行结果 → README.md |

## 为什么这样拆（vs 单个 Agent）

1. **职责单一**：每个 Agent 的 prompt 只聚焦一件事，输出质量更稳。
2. **可观测**：中间产物（代码、报错、文档）都是可见的，答辩好讲。
3. **可扩展**：想加「测试 Agent」「审查 Agent」只需新增一个类。

## 关键设计

- **事件流**：所有 Agent 通过 EventBus 发事件，前端/CLI 实时渲染。
- **沙箱隔离**：LLM 生成的代码在 subprocess + 临时目录里跑，带超时。
- **修复循环**：失败 → 喂回 LLM → 重跑，至多 N 轮（默认 3）。
- **LLM 抽象**：DeepSeek / Fake 可切换，测试不花 token。

## 参考

- ReAct / Plan-Execute 模式（Week 3 内容）
- 任务书 5.2 节多智能体架构图
