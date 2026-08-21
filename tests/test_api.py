"""FastAPI 端点的集成测试（使用 FakeClient 注入）。"""
import sys
from unittest.mock import patch

GOOD_CODE = '```python\nimport sys\nn = int(sys.argv[1])\nprint(n * 2)\n```'


def test_health():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_run_sync_with_fake():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        with patch("app.main.build_client") as mock_build:
            from app.llm import FakeClient

            fake = FakeClient(responses=[GOOD_CODE, "# README"])
            mock_build.return_value = fake
            resp = client.post(
                "/api/run",
                json={"task": "写一个把数字翻倍的程序", "provider": "fake"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "main.py" in body["files"]
        assert "README.md" in body["files"]


def test_run_stream_sse():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        with patch("app.main.build_client") as mock_build:
            from app.llm import FakeClient

            fake = FakeClient(responses=[GOOD_CODE, "# README"])
            mock_build.return_value = fake
            resp = client.get(
                "/api/run/stream",
                params={"task": "写一个把数字翻倍的程序", "provider": "fake"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        text = resp.text
        assert "data: " in text
        assert '"kind": "done"' in text or '"kind": "fail"' in text
        assert '"kind": "start"' in text


def test_run_missing_task():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/api/run", json={})
        assert resp.status_code == 422
