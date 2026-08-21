"""app.agents 包：Code / Debug / Doc 三个 Agent 与 Coordinator 编排器。"""
from .code_agent import CodeAgent
from .coordinator import Coordinator, PipelineResult
from .debug_agent import DebugAgent
from .doc_agent import DocAgent

__all__ = ["CodeAgent", "DebugAgent", "DocAgent", "Coordinator", "PipelineResult"]
