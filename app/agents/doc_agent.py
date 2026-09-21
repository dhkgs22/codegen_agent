"""Doc Agent：根据最终代码生成 README.md 文档。"""
from __future__ import annotations

from typing import Any

from ..events import EV_DOC, EV_LOG, EventBus
from ..languages import Language, language_from_filename, resolve_language
from ..llm import LLMClient
from ..sandbox import RunResult

DOC_SYSTEM_PROMPT = """你是一名技术文档工程师。根据用户提供的程序代码和运行结果，编写一份 README.md。

README 需包含：
1. 项目简介（一句话说明这个程序做什么）
2. 运行环境要求（包含编程语言与编译器/解释器版本要求）
3. 编译 / 运行方法（编译命令、运行命令、命令行参数说明 + 示例）
4. 示例输出
5. 可能的问题与说明

用 Markdown 格式输出，直接给出 README 内容，不要用代码块包裹整个文档。"""


class DocAgent:
    def __init__(
        self,
        llm: LLMClient,
        bus: EventBus | None = None,
        harness: Any | None = None,
        language: str | Language | None = None,
    ) -> None:
        # 优先使用 Harness 提供的基础设施（事件总线、沙箱、工具）
        self.llm = llm
        if harness is not None:
            bus = harness.bus
            if language is None:
                language = harness.language
        self.bus = bus or EventBus()
        self.language: Language = (
            language if isinstance(language, Language) else resolve_language(language)
        )

    def _lang(self, language: str | Language | None, filename: str) -> Language:
        if isinstance(language, Language):
            return language
        if language is not None:
            return resolve_language(language)
        return language_from_filename(filename, default=self.language.key)

    def write_readme(
        self,
        task: str,
        code: str,
        run_result: RunResult,
        filename: str = "main.py",
        language: str | Language | None = None,
    ) -> str:
        """生成 README 内容，返回 markdown 字符串。"""
        lang = self._lang(language, filename)
        build_hint = lang.build_hint(filename)
        cmd_lines = []
        if build_hint:
            cmd_lines.append(f"编译命令：{build_hint}")
        cmd_lines.append(f"运行命令：{lang.run_hint(filename)}")
        cmd_text = "\n".join(cmd_lines)

        user_prompt = f"""程序说明：
{task}

程序语言：{lang.display}
程序文件 `{filename}` 内容：
```{lang.fence}
{code}
```

该程序的构建 / 运行方式（README 里请按此如实写）：
{cmd_text}

运行结果（exit code={run_result.returncode}）：
[stdout]
{run_result.stdout or '(无)'}
[/stdout]

请生成 README.md。"""
        self.bus.emit(EV_LOG, agent="DocAgent", message="DocAgent 正在编写 README 文档")
        readme = self.llm.chat(
            [
                {"role": "system", "content": DOC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
        readme = readme.strip()
        # 去掉可能的整段包裹
        if readme.startswith("```") and readme.endswith("```"):
            readme = readme[3:-3].strip()
        self.bus.emit(
            EV_DOC,
            agent="DocAgent",
            message="DocAgent 已生成 README",
            data={"readme": readme, "language": lang.key},
        )
        return readme
