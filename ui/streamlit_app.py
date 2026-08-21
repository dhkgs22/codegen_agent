"""Streamlit Web 界面：输入任务 → 实时查看 Agent 工作过程 → 展示结果。

启动（后端先跑）：
    uvicorn app.main:app --port 8000
    streamlit run ui/streamlit_app.py
"""
from __future__ import annotations

import json

import httpx
import streamlit as st

API_BASE = st.sidebar.text_input("后端地址", value="http://127.0.0.1:8000")
MAX_ROUNDS = st.sidebar.slider("最大修复轮次", 1, 6, 3)
PROVIDER = st.sidebar.selectbox("LLM 提供方", ["deepseek", "fake"], index=0)

st.title("🤖 多智能体代码助手（项目 I）")
st.caption("Coordinator → Code Agent → Debug Agent(循环修复) → Doc Agent")

TASK = st.text_area(
    "任务描述",
    placeholder="例：写一个计算斐波那契数列前 N 项的程序",
    height=100,
)

KIND_EMOJI = {
    "start": "🚀",
    "code": "📝",
    "run": "🏃",
    "fix": "🔧",
    "doc": "📄",
    "done": "✅",
    "fail": "❌",
    "error": "💥",
    "log": "💬",
}


def main() -> None:
    if not st.button("▶️ 开始生成", type="primary"):
        return
    if not TASK.strip():
        st.warning("请先输入任务描述")
        return

    container = st.container()
    state = st.session_state.setdefault("code_display", {"code": "", "readme": ""})

    try:
        with httpx.stream(
            "GET",
            f"{API_BASE}/api/run/stream",
            params={"task": TASK, "provider": PROVIDER, "max_rounds": MAX_ROUNDS},
            timeout=300,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[len("data: "):])
                kind, agent, message, data = (
                    payload.get("kind", ""),
                    payload.get("agent", ""),
                    payload.get("message", ""),
                    payload.get("data", {}),
                )
                emoji = KIND_EMOJI.get(kind, "•")
                container.markdown(f"**{emoji} [{agent}]** {message}")
                if kind == "code" and data.get("code"):
                    with container.expander("生成的代码", expanded=True):
                        st.code(data["code"], language="python")
                elif kind == "run":
                    with container.expander(f"运行输出（第 {data.get('round', '?')} 轮）"):
                        if data.get("stdout"):
                            st.text(f"stdout:\n{data['stdout']}")
                        if data.get("stderr"):
                            st.text(f"stderr:\n{data['stderr']}")
                elif kind == "fix":
                    with container.expander("修复后的代码"):
                        st.code(data["code"], language="python")
                elif kind == "doc" and data.get("readme"):
                    with container.expander("README.md"):
                        st.markdown(data["readme"])
                elif kind in ("done", "fail"):
                    container.success(message) if kind == "done" else container.error(message)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 500 and "DEEPSEEK_API_KEY" in e.response.text:
            st.error("未配置 DeepSeek API Key。请先复制 .env.example 为 .env 并填入你的 key。")
        else:
            st.error(f"请求失败：{e}")
    except Exception as e:  # noqa: BLE001
        st.error(f"连接失败：{e}。请确认后端已启动（uvicorn app.main:app --port 8000）")


if __name__ == "__main__":
    main()
