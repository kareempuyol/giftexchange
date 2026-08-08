"""KDNiao 物流查询封装测试（3s 超时 / 6h 缓存 / 静默降级，wxcloudrun/helpers.py）。

不发起任何真实 HTTP 请求：
- 无配置路径：直接走降级分支（KDNiao not configured）
- 超时/网络异常路径：monkeypatch urllib.request.urlopen 抛 URLError / 任意异常
- 缓存命中路径：注入 fake requester（monkeypatch helpers._kdniao_http_query）统计调用次数
- 成功解析路径：fake urlopen 返回构造的 KDNiao JSON

注意：wxcloudrun/__init__.py 在 import 时执行 create_app()→init_schema()，
因此必须在 import wxcloudrun 之前设置 DB_PATH，让包初始化落在临时库上。
"""
import json
import os
import socket
import tempfile
import urllib.error

import pytest

# ---- 包导入前的环境准备（必须在 from wxcloudrun... 之前）----
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="gift_kdniao_test_"), "test.db")
for _k in ("MYSQL_ADDRESS", "MYSQL_HOST", "MYSQL_PORT"):
    os.environ.pop(_k, None)

from wxcloudrun import helpers  # noqa: E402
from wxcloudrun.database import DB  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """每个测试前：清空缓存 + 清掉 KDNiao 配置（测试用环境变量方式配置）。"""
    helpers._kdniao_cache.clear()
    monkeypatch.delenv("KDNIAO_EBUSINESS_ID", raising=False)
    monkeypatch.delenv("KDNIAO_APP_KEY", raising=False)
    with DB() as db:
        db.execute("DELETE FROM app_settings")
    yield


def configure_kdniao(monkeypatch):
    monkeypatch.setenv("KDNIAO_EBUSINESS_ID", "TEST_EID")
    monkeypatch.setenv("KDNIAO_APP_KEY", "TEST_KEY")


def assert_degraded(result, detail_contains=None):
    success, summary, detail = result
    assert success is False
    assert summary == ""
    if detail_contains:
        assert detail_contains in detail


# ---------- 降级路径 ----------

class TestDegradation:
    def test_no_config_returns_graceful_degradation(self):
        with DB() as db:
            result = helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert_degraded(result, detail_contains="not configured")

    def test_empty_tracking_number_returns_degradation(self, monkeypatch):
        calls = []

        def fake_query(*args):
            calls.append(args)
            return True, "已签收", []

        monkeypatch.setattr(helpers, "_kdniao_http_query", fake_query)
        configure_kdniao(monkeypatch)
        with DB() as db:
            result = helpers.query_kdniao_tracking(db, "SF", "")
        assert_degraded(result)
        assert calls == []  # 空单号根本不发请求

    def test_timeout_returns_degradation(self, monkeypatch):
        def _raise_timeout(*args, **kwargs):
            raise urllib.error.URLError(socket.timeout("timed out"))

        monkeypatch.setattr("urllib.request.urlopen", _raise_timeout)
        configure_kdniao(monkeypatch)
        with DB() as db:
            result = helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert_degraded(result, detail_contains="timed out")

    def test_arbitrary_exception_never_leaks(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("urllib.request.urlopen", _boom)
        configure_kdniao(monkeypatch)
        with DB() as db:
            result = helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert_degraded(result, detail_contains="boom")

    def test_api_error_response_is_degraded_not_exception(self, monkeypatch):
        body = json.dumps({"Success": False, "Reason": "单号不存在"}).encode("utf-8")
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _FakeResp(body))
        configure_kdniao(monkeypatch)
        with DB() as db:
            result = helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert_degraded(result, detail_contains="单号不存在")

    def test_garbage_response_is_degraded_not_exception(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda *a, **k: _FakeResp(b"<html>not json</html>")
        )
        configure_kdniao(monkeypatch)
        with DB() as db:
            result = helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert_degraded(result)


# ---------- 超时参数 ----------

class TestTimeout:
    def test_urlopen_receives_3_second_timeout(self, monkeypatch):
        seen = {}

        def _capture(*args, **kwargs):
            seen["timeout"] = kwargs.get("timeout")
            raise urllib.error.URLError(socket.timeout("timed out"))

        monkeypatch.setattr("urllib.request.urlopen", _capture)
        configure_kdniao(monkeypatch)
        with DB() as db:
            helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert seen.get("timeout") == 3


# ---------- 缓存 ----------

class TestCache:
    def _raw_ok(self):
        # _kdniao_http_query 的契约：返回 KDNiao 原始响应 dict（由 _kdniao_result_to_summary 解析）
        return {"Success": True, "State": "3", "Traces": [{"AcceptStation": "包裹已送达"}]}

    def _parsed_ok(self):
        return (True, "已签收 | 最新：包裹已送达", [{"AcceptStation": "包裹已送达"}])

    def test_cache_hit_does_not_repeat_request(self, monkeypatch):
        calls = []

        def fake_query(eid, app_key, carrier, tracking_number):
            calls.append((carrier, tracking_number))
            return self._raw_ok()

        monkeypatch.setattr(helpers, "_kdniao_http_query", fake_query)
        configure_kdniao(monkeypatch)
        with DB() as db:
            r1 = helpers.query_kdniao_tracking(db, "SF", "SF123456789")
            r2 = helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert r1 == self._parsed_ok()
        assert r2 == self._parsed_ok()
        assert len(calls) == 1  # 缓存命中：只外呼一次

    def test_cache_key_includes_carrier_and_number(self, monkeypatch):
        calls = []

        def fake_query(eid, app_key, carrier, tracking_number):
            calls.append((carrier, tracking_number))
            return self._raw_ok()

        monkeypatch.setattr(helpers, "_kdniao_http_query", fake_query)
        configure_kdniao(monkeypatch)
        with DB() as db:
            helpers.query_kdniao_tracking(db, "SF", "SF123456789")
            helpers.query_kdniao_tracking(db, "YT", "SF123456789")  # 换承运商
            helpers.query_kdniao_tracking(db, "SF", "YT999999")  # 换单号
        assert len(calls) == 3  # (carrier, tracking_number) 二元组构成 key

    def test_failure_is_not_cached(self, monkeypatch):
        calls = []

        def fake_query(eid, app_key, carrier, tracking_number):
            calls.append(1)
            return {"Success": False, "Reason": "KDNiao query failed"}

        monkeypatch.setattr(helpers, "_kdniao_http_query", fake_query)
        configure_kdniao(monkeypatch)
        with DB() as db:
            helpers.query_kdniao_tracking(db, "SF", "SF123456789")
            helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert len(calls) == 2  # 失败不缓存，下次仍重试

    def test_expired_cache_entry_forces_requery(self, monkeypatch):
        calls = []

        def fake_query(eid, app_key, carrier, tracking_number):
            calls.append(1)
            return self._raw_ok()

        monkeypatch.setattr(helpers, "_kdniao_http_query", fake_query)
        configure_kdniao(monkeypatch)
        with DB() as db:
            helpers.query_kdniao_tracking(db, "SF", "SF123456789")
            # 手动把缓存条目改为已过期（提前 TTL+1 秒）
            key = ("SF", "SF123456789")
            with helpers._kdniao_cache_lock:
                entry = helpers._kdniao_cache[key]
                helpers._kdniao_cache[key] = (
                    entry[0] - helpers._KDNIAO_CACHE_TTL_SECONDS - 1,
                    entry[1],
                )
            helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert len(calls) == 2


# ---------- 成功解析 ----------

class _FakeResp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestSuccessParse:
    def test_success_response_builds_summary(self, monkeypatch):
        body = json.dumps(
            {
                "Success": True,
                "State": "3",
                "Traces": [{"AcceptStation": "已签收，签收人：前台"}],
            }
        ).encode("utf-8")
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _FakeResp(body))
        configure_kdniao(monkeypatch)
        with DB() as db:
            success, summary, detail = helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert success is True
        assert "已签收" in summary
        assert "签收人：前台" in summary
        assert detail == [{"AcceptStation": "已签收，签收人：前台"}]

    def test_success_without_traces_still_builds_state_summary(self, monkeypatch):
        body = json.dumps({"Success": True, "State": "2", "Traces": None}).encode("utf-8")
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _FakeResp(body))
        configure_kdniao(monkeypatch)
        with DB() as db:
            success, summary, _detail = helpers.query_kdniao_tracking(db, "SF", "SF123456789")
        assert success is True
        assert summary == "在途中"

    def test_signature_kept_for_caller(self):
        import inspect

        params = list(inspect.signature(helpers.query_kdniao_tracking).parameters)
        assert params == ["db", "carrier", "tracking_number"]
