# 多智能体架构笔记

> Obsidian 知识库 · 架构演进记录（W4 预研 → W6 强化）

## 一句话

任务书项目 I：Coordinator 编排四个各司其职的 Agent（Code / Debug / Doc / Test），
让「写代码→运行→修复→文档→测试」全流程自动化，Agent 之间通过协作消息互相配合。

## 四个 Agent 的分工

| Agent | 职责 | 输入 → 输出 |
|---|---|---|
| Code Agent | 生成初始代码 | 任务描述 → 目标语言代码（Python/C/C++/Go/Java） |
| Debug Agent | 编译并运行代码，失败则修复；也按测试失败反馈修复 | 代码 + 报错/测试输出 → 修复后代码 |
| Doc Agent | 生成文档 | 代码 + 运行结果 → README.md |
| Test Agent | 自动生成测试并运行；失败时反馈给 Debug | 代码 → 测试（pytest 或黑盒用例）+ 通过/失败 |

## 协作方式：管道式编排 + 协作消息回环

**主流程是管道式**（Coordinator 顺序调度，各 Agent 通过共享文件工件接力）：

```
任务 → Code Agent → [Debug 循环: 运行→失败→修复] → Doc Agent → Test Agent → 完成
```

**协作回环**（Agent 之间的真实消息交互）：Test Agent 测试失败时，通过
`msg` 协作消息反馈给 Debug Agent，Debug 修复后复用同一份测试复测：

```
Test Agent 发现测试失败
   → 🔁 协作消息（TestAgent → DebugAgent）
   → Debug Agent 按测试失败输出修复代码
   → 重新运行 → Test Agent 复测
   → 通过 或 达到最大测试修复轮次
```

这是「一个 Agent 发现问题、交给另一个 Agent 解决」的协作闭环，
也是区别于「单 Agent」或「纯流水线」的关键设计。

## 为什么这样拆（vs 单个 Agent）

1. **职责单一**：每个 Agent 的 prompt 只聚焦一件事，输出质量更稳。
2. **可观测**：中间产物（代码、报错、测试输出）都是可见的，答辩好讲。
3. **可协作**：协作消息让 Test 能驱动 Debug 修复，形成闭环。
4. **可扩展**：想加「审查 Agent」只需新增一个类 + 注册，Harness 零改动。

## 关键设计

- **Harness 基础设施层**：统一管理沙箱、事件总线、工具注册、配置、目标语言
  （详见 `wiki/concepts/harness-architecture.md`，实现 `app/harness.py`）。
- **语言档案（Language Registry）**：把「语言相关的一切」——入口文件名、编译/运行命令、
  编译器报错解析、提示词片段、测试策略——收口到 `app/languages.py` 的 `LANGUAGES` 表。
  四个 Agent 和沙箱都按 key 取档案，没有一处 `if language == "python"`。
  新增一种语言 = 加一条档案（详见 `wiki/concepts/language-registry.md`）。
- **事件流**：所有 Agent 通过 EventBus 发事件，前端/CLI 实时渲染，
  协作消息走 `EV_MSG` 事件。
- **沙箱隔离**：LLM 生成的代码在 subprocess + 临时目录里跑，带超时、强制 UTF-8；
  编译型语言先编译再运行产物，编译失败按「编译阶段」单独诊断。
- **修复循环**：运行失败 → 喂回 LLM → 重跑，至多 N 轮（默认 3）；
  测试失败回环至多 M 轮（默认 2）。
- **修复历史记忆**：每轮失败诊断累积传入下一轮提示词，避免重复踩坑。
- **LLM 抽象**：DeepSeek / Fake 可切换，测试不花 token。

## 参考

- ReAct / Plan-Execute 模式（Week 3 内容）
- 任务书 5.2 节多智能体架构图
- LangGraph workflow / CrewAI sequential 等「Coordinator-Worker」编排范式
