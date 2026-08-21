"""FastAPI 后端：提供 REST 同步执行 + SSE 流式执行端点。

启动：
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agents import Coordinator
from .events import Event, EventBus
from .llm import build_client


class RunRequest(BaseModel):
    task: str = Field(..., description="用自然语言描述任务")
    provider: str | None = None
    max_rounds: int | None = None
    workspace: str | None = None
    filename: str = "main.py"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="多智能体代码助手 API",
    description="Coordinator + Code/Debug/Doc Agent 的代码生成流水线",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_coordinator(req: RunRequest) -> Coordinator:
    try:
        llm = build_client(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return Coordinator(
        llm=llm,
        max_rounds=req.max_rounds,
        workspace=req.workspace,
        keep_workspace=bool(req.workspace),
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/run")
def run(req: RunRequest) -> dict[str, Any]:
    """同步执行：等待完整流水线跑完，返回结果。"""
    coordinator = _build_coordinator(req)
    result = coordinator.run(req.task, filename=req.filename)
    result_dict = result.to_dict()
    # 附带事件流，便于前端一次性渲染
    result_dict["events"] = [e.to_dict() for e in coordinator.bus.events()]
    return result_dict


@app.get("/api/run/stream")
def run_stream(
    task: str = Query(..., description="任务描述"),
    provider: str | None = None,
    max_rounds: int | None = None,
    filename: str = "main.py",
):
    """SSE 流式执行：事件实时推送（data: {json}\\n\\n），结束推 done/fail。"""
    req = RunRequest(task=task, provider=provider, max_rounds=max_rounds, filename=filename)
    try:
        llm = build_client(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    import queue
    import threading

    bus = EventBus()
    coordinator = Coordinator(
        llm=llm,
        bus=bus,
        max_rounds=req.max_rounds,
        workspace=req.workspace,
        keep_workspace=bool(req.workspace),
    )
    q: queue.Queue = queue.Queue()
    bus.subscribe(lambda e: q.put(e))

    def event_gen():
        # 后台线程跑流水线，事件经队列推送给 SSE 客户端
        def worker():
            try:
                coordinator.run(req.task, filename=req.filename)
            except Exception as exc:  # noqa: BLE001
                q.put(
                    Event(
                        kind="error",
                        agent="Coordinator",
                        message=f"流水线异常：{exc}",
                    )
                )
            finally:
                q.put(None)  # 结束标记

        threading.Thread(target=worker, daemon=True).start()
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item.to_dict(), ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
