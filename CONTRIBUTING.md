# 贡献指南（CONTRIBUTING）

感谢你愿意参与本项目。这里是协作规范，帮助所有人高效、一致地贡献代码。

## 开发环境

- Python 3.10+（本机 3.13.5）
- 虚拟环境：`.venv\Scripts\activate`（Windows）
- 安装依赖：`pip install -r requirements.txt`
  - 若 pip 并发下载失败，请逐个安装：`pip install httpx`、`pip install fastapi`……

## 目录结构

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

## 开发流程

1. **新建分支**：`git checkout -b feature/你的功能名`
   - 禁止直接往 `main` 上提交新功能
2. **小步提交**：功能完成后用清晰的中文 commit message，如
   `feat: 增加 XX 功能` / `fix: 修复 XX 问题`
3. **跑测试**：提交前必须本地通过
   ```bash
   python -m pytest -q
   ```
4. **推送 + PR**：`git push origin 分支名`，然后到 GitHub 上发起 Pull Request
   - 描述清楚改了什么、怎么验证
5. **Code Review**：等至少一个维护者 review 通过再合并

## 代码规范

- 新增功能请配套 **pytest 测试**（用 `FakeClient`，不消耗真实 token）
- 不引入重型第三方依赖；确有需要先在 issue 里讨论
- LLM 相关逻辑一律走 `app/llm/client.py` 的抽象接口，不要直连 API

## 提 Issue

Bug、功能建议请到 GitHub Issues，模板参考：

- **Bug 报告**：复现步骤、期望结果、实际结果、相关报错
- **功能建议**：要解决什么问题、大致怎么做

## License

本项目使用 MIT License，见 [LICENSE](LICENSE)。
