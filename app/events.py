"""统一事件模型：Coordinator 与各 Agent 之间、以及对外（CLI/SSE/Web）传递的事件。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

EventKind = str
# 常用事件类型常量
EV_START = "start"          # 任务开始
EV_CODE = "code"            # Code Agent 生成/更新了代码
EV_RUN = "run"              # 沙箱运行结果（含 stdout/stderr/returncode）
EV_FIX = "fix"              # Debug Agent 修复后的代码
EV_DOC = "doc"              # Doc Agent 生成的文档
EV_DONE = "done"            # 全部完成
EV_FAIL = "fail"            # 失败终止
EV_ERROR = "error"          # 内部错误
EV_LOG = "log"              # 普通日志


@dataclass
class Event:
    kind: EventKind
    agent: str = ""                 # 产生事件的 Agent 名
    message: str = ""               # 人类可读信息
    data: dict[str, Any] = field(default_factory=dict)  # 附加数据（代码、输出等）
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# 事件监听器签名：收到 Event 时被调用（用于实时推送/流式输出）
EventListener = Callable[[Event], None]


class EventBus:
    """简单事件总线：负责记录全部事件，并向监听器实时广播。"""

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._listeners: list[EventListener] = []

    def subscribe(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def emit(
        self,
        kind: EventKind,
        agent: str = "",
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        event = Event(kind=kind, agent=agent, message=message, data=data or {})
        self._events.append(event)
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                # 监听器异常不应中断主流程
                pass

    def events(self) -> list[Event]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
