#!/usr/bin/env python3
"""login_required 开销测量（I18N2 轮，任务 B-1）。

拆解 login_required 的三个成本项（均为每次认证请求支付）：
  1. verify_token        —— JWT 解析 + HMAC-SHA256 验签（纯 CPU，无 IO）
  2. with DB() as db     —— 新建 SQLite 连接 + WAL/busy_timeout PRAGMA
  3. SELECT deactivated FROM users WHERE id = ?  —— 单列主键查询（真实 DB）

分母：完整认证请求（Flask test client 走真实路由 /auth/me、/profile、/events，
含 before/after_request 全生命周期，不含网络）。

输出：各项 median / p95 / p99（µs 与 ms），以及 login_required 占完整请求的百分比。
结论判据（任务书）：占比 < 5% → 保持每请求查库现状（安全 > 微优化）。
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.expanduser("~/giftexchange"))
os.environ.setdefault("DB_PATH", os.path.expanduser("~/giftexchange/data/gift_exchange.db"))

from wxcloudrun.auth import sign_token, verify_token  # noqa: E402
from wxcloudrun.database import DB  # noqa: E402

N = 3000  # 单项基准次数
REQ_N = 200  # 完整请求次数（含真实路由，少些避免拖长）


def pct(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(p / 100 * len(sorted_vals)))
    return sorted_vals[idx]


def bench(fn, n=N):
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1e6)  # µs
    return out


def main():
    results = {}

    # 0) 准备：真实用户 token + 用户 id
    with DB() as db:
        row = db.get("SELECT id, username, deactivated FROM users WHERE username = ?", ("verify_user",))
        if not row:
            raise SystemExit("verify_user 不存在，无法测量（先用 seed/注册造号）")
        user_id = row["id"]
    token = sign_token(user_id)
    assert verify_token(token) == {"userId": user_id}, "token 自检失败"

    # 1) JWT 验签（纯 CPU）
    jwt_vals = bench(lambda: verify_token(token))
    results["verify_token_us"] = {
        "median": round(statistics.median(jwt_vals), 2),
        "p95": round(pct(sorted(jwt_vals), 95), 2),
        "p99": round(pct(sorted(jwt_vals), 99), 2),
    }

    # 2) DB 连接建立（open + 2×PRAGMA + close）—— login_required 每次请求的固定开销
    def open_db():
        with DB() as db:
            pass
    db_open_vals = bench(open_db)
    results["db_connect_us"] = {
        "median": round(statistics.median(db_open_vals), 2),
        "p95": round(pct(sorted(db_open_vals), 95), 2),
        "p99": round(pct(sorted(db_open_vals), 99), 2),
    }

    # 3) 单列主键查询（在新建连接里执行，与 login_required 完全一致）
    def query_deactivated():
        with DB() as db:
            db.get("SELECT deactivated FROM users WHERE id = ?", (user_id,))
    query_vals = bench(query_deactivated)
    results["deactivated_query_us"] = {
        "median": round(statistics.median(query_vals), 2),
        "p95": round(pct(sorted(query_vals), 95), 2),
        "p99": round(pct(sorted(query_vals), 99), 2),
    }

    # 4) login_required 合计（同一次测量内累加，避免不同批次基准偏差）
    def login_required_cost():
        user = verify_token(token)
        with DB() as db:
            r = db.get("SELECT deactivated FROM users WHERE id = ?", (user["userId"],))
        assert r is not None and not r["deactivated"]
    lr_vals = bench(login_required_cost)
    results["login_required_total_us"] = {
        "median": round(statistics.median(lr_vals), 2),
        "p95": round(pct(sorted(lr_vals), 95), 2),
        "p99": round(pct(sorted(lr_vals), 99), 2),
    }

    # 5) 完整认证请求（真实路由 + 全生命周期）
    from wxcloudrun import app  # noqa: E402  (create_app 已在模块级执行)

    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}
    with DB() as db:
        ev = db.get("SELECT code FROM events ORDER BY id DESC LIMIT 1")
    if not ev:
        raise SystemExit("无活动数据，无法测量重接口")
    detail_path = f"/events/{ev['code']}"
    dashboard_path = f"/events/{ev['code']}/dashboard"
    req_samples = {}  # path -> list[µs]
    for path in ("/auth/me", "/profile", "/events", detail_path, dashboard_path):
        vals = []
        for _ in range(REQ_N):
            t0 = time.perf_counter()
            resp = client.get(path, headers=headers)
            assert resp.status_code == 200, f"{path} → {resp.status_code}"
            vals.append((time.perf_counter() - t0) * 1e6)
        req_samples[path] = vals
    for path, vals in req_samples.items():
        results[f"request_{path}_us"] = {
            "median": round(statistics.median(vals), 2),
            "p95": round(pct(sorted(vals), 95), 2),
            "p99": round(pct(sorted(vals), 99), 2),
        }

    # 6) 占比：login_required / 完整请求（各分位点对齐计算）
    shares = {}
    lr_med = results["login_required_total_us"]["median"]
    lr_p99 = results["login_required_total_us"]["p99"]
    for path in req_samples:
        med = results[f"request_{path}_us"]["median"]
        p99 = results[f"request_{path}_us"]["p99"]
        shares[path] = {"median_pct": round(lr_med / med * 100, 2), "p99_pct": round(lr_p99 / p99 * 100, 2)}
    results["login_required_share_pct"] = shares

    print(json.dumps(results, ensure_ascii=False, indent=2))
    with open(os.path.expanduser("~/.cache/login_required_bench.json"), "w") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print("\nsaved ~/.cache/login_required_bench.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
