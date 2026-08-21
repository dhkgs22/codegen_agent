"""app.agents 包：Code / Debug / Doc / Test 四个 Agent 与 Coordinator 编排器。"""
from .code_agent import CodeAgent
from .coordinator import Coordinator, PipelineResult
from .debug_agent import DebugAgent
from .doc_agent import DocAgent
from .test_agent import TestAgent

__all__ = ["CodeAgent", "DebugAgent", "DocAgent", "TestAgent", "Coordinator", "PipelineResult"]
