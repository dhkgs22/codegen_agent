"""app.llm 包：LLM 客户端抽象层。"""
from .client import LLMClient, DeepSeekClient, FakeClient, build_client

__all__ = ["LLMClient", "DeepSeekClient", "FakeClient", "build_client"]
