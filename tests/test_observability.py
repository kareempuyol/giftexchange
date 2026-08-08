"""可观测性测试：request_id 回显 + 结构化 JSON 日志 + 漏斗埋点。

注意：wxcloudrun/__init__.py 在 import 时执行 create_app()→init_schema()，
因此必须在 import wxcloudrun 之前设置 DB_PATH，让包初始化/连接落在临时库上，
绝不触碰开发库 ~/giftexchange/data/gift_exchange.db。
（giftexchange logger propagate=False，caplog 收不到 → 用自定义 handler 收集。）
"""
import json
import logging
import os
import tempfile

import pytest

# ---- 包导入前的环境准备（必须在 from wxcloudrun... 之前）----
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="gift_obs_test_"), "test.db")
os.environ["JWT_SECRET"] = "test-secret-obs"
os.environ["DEADLINE_SCANNER"] = "0"
for _k in ("MYSQL_ADDRESS", "MYSQL_HOST", "MYSQL_PORT"):
    os.environ.pop(_k, None)

from wxcloudrun import app as flask_app  # noqa: E402
from wxcloudrun.database import init_schema  # noqa: E402
from wxcloudrun.observability import (  # noqa: E402
    get_request_id,
    log_event,
    make_request_id,
    set_request_id,
    set_user_id,
)

init_schema()  # 幂等：确保本模块临时库有表（包可能已被其他测试模块先导入）

PASSWORD = "Pass123!"


class _CaptureHandler(logging.Handler):
    """收集 giftexchange logger 的输出行（一行一条 JSON）。"""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


@pytest.fixture
def capture():
    logger = logging.getLogger("giftexchange")
    handler = _CaptureHandler()
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _events(capture):
    """capture.lines -> [{event, ...}]（跳过非 JSON 行，防御未来格式变化）"""
    parsed = []
    for line in capture.lines:
        try:
            parsed.append(json.loads(line))
        except (ValueError, TypeError):
            continue
    return parsed


# ---------- request_id ----------

def test_make_request_id_format():
    rid = make_request_id()
    assert isinstance(rid, str)
    assert len(rid) == 12
    assert all(c in "0123456789abcdef" for c in rid)
    assert make_request_id() != rid  # 每次不同


def test_request_id_contextvar():
    set_request_id("ctx-1")
    assert get_request_id() == "ctx-1"


def test_response_echoes_generated_request_id(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid and len(rid) == 12  # 未传时后端生成 12 位并回显


def test_request_ids_unique_per_request(client):
    r1 = client.get("/api/health")
    r2 = client.get("/api/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_client_supplied_request_id_echoed(client):
    r = client.get("/api/health", headers={"X-Request-ID": "my-trace-id-123"})
    assert r.headers.get("X-Request-ID") == "my-trace-id-123"


# ---------- log_event ----------

def test_log_event_outputs_json_line(capture):
    set_request_id("abc123")
    log_event("unit_test", foo="bar", count=3)
    assert len(capture.lines) == 1
    line = json.loads(capture.lines[0])
    assert line["event"] == "unit_test"
    assert line["request_id"] == "abc123"
    assert line["foo"] == "bar"
    assert line["count"] == 3
    assert "ts" in line  # ISO 时间戳


def test_log_event_auto_user_id_from_context(capture):
    set_request_id("req-2")
    set_user_id(42)
    log_event("unit_test")
    line = json.loads(capture.lines[0])
    assert line["user_id"] == "42"


def test_log_event_never_raises_on_unserializable(capture):
    log_event("unit_test", weird=object())  # default=str 兜底，绝不抛异常
    line = json.loads(capture.lines[0])
    assert line["event"] == "unit_test"
    assert line["weird"].startswith("<object object at")


def test_log_event_in_non_request_context_uses_dash(capture):
    set_request_id("")
    log_event("unit_test")
    line = json.loads(capture.lines[0])
    assert line["request_id"] == "-"


# ---------- 请求级日志 ----------

def test_after_request_emits_request_log(client, capture):
    client.get("/api/health")
    events = _events(capture)
    req = [e for e in events if e.get("event") == "request"][-1]
    assert req["method"] == "GET"
    assert req["path"] == "/api/health"
    assert req["status"] == 200
    assert isinstance(req["duration_ms"], (int, float))
    assert len(req["request_id"]) == 12


# ---------- 漏斗埋点（helpers 侧，零路由改动） ----------

def test_login_funnel_events(client, capture):
    name = f"obs_{os.getpid()}"
    r = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@test.local", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()

    r = client.post("/api/auth/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 200, r.get_json()

    r = client.post("/api/auth/login", json={"username": name, "password": "wrong-pass"})
    assert r.status_code == 401, r.get_json()

    events = _events(capture)
    events_by_name = {e["event"] for e in events}
    assert "login_success" in events_by_name
    assert "login_failed" in events_by_name

    success = [e for e in events if e["event"] == "login_success"][-1]
    failed = [e for e in events if e["event"] == "login_failed"][-1]
    assert success["username"] == name
    assert failed["username"] == name
    # 登录请求本身未带 token：不应串上其他请求的 user_id
    assert "user_id" not in success
    assert "user_id" not in failed
