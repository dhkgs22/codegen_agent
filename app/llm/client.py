"""LLM 客户端抽象层。

支持：
- DeepSeekClient：OpenAI 兼容的 chat/completions 接口
- FakeClient：测试用，返回预设内容，不消耗 token

对外统一接口：
    client.chat(messages: list[dict], **kwargs) -> str
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Iterable

import httpx

from ..config import settings


class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], **kwargs: Any) -> str:
        """发送一轮对话，返回完整回复文本。"""


def _messages_for(system: str, user: str) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


class DeepSeekClient(LLMClient):
    """DeepSeek 官方 API（OpenAI 兼容）。

    支持流式回调：传入 on_delta 可在收到每个 token 时被调用。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key or settings.deepseek_api_key
        self.base_url = base_url or settings.deepseek_base_url
        self.model = model or settings.deepseek_model
        self.timeout = timeout or settings.llm_timeout
        if not self.api_key:
            raise ValueError(
                "未配置 DEEPSEEK_API_KEY。请在项目根目录的 .env 中填入你的 DeepSeek API key。"
            )

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        on_delta: Callable[[str], None] | None = None,
        **_: Any,
    ) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": on_delta is not None,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            if on_delta is None:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""

            # 流式
            with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                parts: list[str] = []
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[len("data: "):]
                    if line.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if delta:
                        parts.append(delta)
                        on_delta(delta)
                return "".join(parts)


class FakeClient(LLMClient):
    """测试用：按预设脚本逐条返回，且可选地为每条标注用时与是否报错。

    Usage:
        fake = FakeClient(responses=["...", "...", "..."])
    """

    def __init__(
        self,
        responses: Iterable[str] = (),
        *,
        on_delta: Callable[[str], None] | None = None,
        delay: float = 0.0,
        raise_on_first: bool = False,
    ) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls: list[dict] = []  # 记录每次调用，便于断言
        self.on_delta = on_delta
        self.delay = delay
        self.raise_on_first = raise_on_first

    def chat(self, messages: list[dict], **kwargs: Any) -> str:
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if self.raise_on_first and self._index == 0:
            self._index += 1
            raise httpx.ConnectError("fake network error")
        if self.delay:
            time.sleep(self.delay)
        if self._index < len(self._responses):
            text = self._responses[self._index]
            self._index += 1
        else:
            text = ""  # 用尽预设时返回空串
        if self.on_delta:
            self.on_delta(text)
        return text


def build_client(provider: str | None = None, **kwargs: Any) -> LLMClient:
    """工厂：'deepseek' 或 None → DeepSeek；'fake' → FakeClient。"""
    provider = (provider or "deepseek").lower()
    if provider == "fake":
        return FakeClient(**kwargs)
    return DeepSeekClient(**kwargs)
