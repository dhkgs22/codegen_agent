"""Streamlit Web 界面：输入任务 → 选择语言 → 实时查看 Agent 工作过程 → 展示结果。

启动（后端先跑）：
    uvicorn app.main:app --port 8000
    streamlit run ui/streamlit_app.py
"""
from __future__ import annotations

import json

import httpx
import streamlit as st

API_BASE = st.sidebar.text_input("后端地址", value="http://127.0.0.1:8000")

# 语言列表优先从后端拿（含本机工具链可用性），拿不到就用静态列表兜底
_FALLBACK_LANGS = [
    {"key": "python", "display": "Python", "entry": "main.py", "available": True},
    {"key": "c", "display": "C", "entry": "main.c", "available": True},
    {"key": "cpp", "display": "C++", "entry": "main.cpp", "available": True},
    {"key": "go", "display": "Go", "entry": "main.go", "available": True},
    {"key": "java", "display": "Java", "entry": "Main.java", "available": True},
]


@st.cache_data(ttl=60, show_spinner=False)
def fetch_languages(api_base: str) -> list[dict]:
    try:
        resp = httpx.get(f"{api_base}/api/languages", timeout=5)
        resp.raise_for_status()
        return resp.json().get("languages", _FALLBACK_LANGS)
    except Exception:  # noqa: BLE001
        return _FALLBACK_LANGS


LANGS = fetch_languages(API_BASE)
_LABELS = [
    f"{row['display']}" + ("" if row.get("available", True) else "（本机缺少工具链）")
    for row in LANGS
]
_pick = st.sidebar.selectbox("目标语言", range(len(LANGS)), format_func=lambda i: _LABELS[i])
LANG = LANGS[_pick]

MAX_ROUNDS = st.sidebar.slider("最大修复轮次", 1, 6, 3)
PROVIDER = st.sidebar.selectbox("LLM 提供方", ["deepseek", "fake"], index=0)

st.title("🤖 多智能体代码助手（项目 I）")
st.caption(
    "Coordinator → Code Agent → Debug Agent(循环修复) → Doc Agent → Test Agent"
    "　｜　支持 Python / C / C++ / Go / Java"
)

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
    "test": "🧪",
    "msg": "🔁",
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
    if not LANG.get("available", True):
        st.warning(
            f"本机缺少 {', '.join(LANG.get('missing', []))}，无法编译/运行 "
            f"{LANG['display']} 代码，请先安装对应工具链。"
        )
        return

    container = st.container()

    try:
        with httpx.stream(
            "GET",
            f"{API_BASE}/api/run/stream",
            params={
                "task": TASK,
                "provider": PROVIDER,
                "max_rounds": MAX_ROUNDS,
                "language": LANG["key"],
            },
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
                        st.code(data["code"], language=data.get("fence", "python"))
                elif kind == "run":
                    with container.expander(f"运行输出（第 {data.get('round', '?')} 轮）"):
                        if data.get("stdout"):
                            st.text(f"stdout:\n{data['stdout']}")
                        if data.get("stderr"):
                            st.text(f"stderr:\n{data['stderr']}")
                elif kind == "fix":
                    with container.expander("修复后的代码"):
                        st.code(data["code"], language=data.get("fence", "python"))
                elif kind == "doc" and data.get("readme"):
                    with container.expander("README.md"):
                        st.markdown(data["readme"])
                elif kind == "test":
                    status = "✅ 通过" if data.get("passed") else "⚠️ 未通过"
                    with container.expander(f"Test Agent 测试：{status}"):
                        if data.get("summary"):
                            st.text(data["summary"])
                        if data.get("output"):
                            st.text(data["output"])
                elif kind == "msg":
                    container.markdown(f"🔁 **协作消息** {message}")
                elif kind in ("done", "fail"):
                    container.success(message) if kind == "done" else container.error(message)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 500 and "DEEPSEEK_API_KEY" in e.response.text:
            st.error("未配置 DeepSeek API Key。请先复制 .env.example 为 .env 并填入你的 key。")
        elif e.response.status_code == 400:
            st.error(f"请求参数有误：{e.response.text}")
        else:
            st.error(f"请求失败：{e}")
    except Exception as e:  # noqa: BLE001
        st.error(f"连接失败：{e}。请确认后端已启动（uvicorn app.main:app --port 8000）")


if __name__ == "__main__":
    main()
