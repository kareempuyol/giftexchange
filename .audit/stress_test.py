#!/usr/bin/env python3
"""并发与压力验证（hackathon 轮4）：真实 HTTP 并发压测 + DB 真值一致性校验。

场景（默认 20 轮重复，失败即记录复现步骤）：
  1. 并发抽签    8 线程 POST /events/<code>/draw（同一创建者）
                 → 恰 1×200 + 7×409；DB matches 恰一份（8 条）
  2. 并发加入    12 线程 join maxParticipants=8 活动（空位 8）
                 → 恰 8×201 + 4×400（人数已满）；DB participants 恰 8、count 恰 8
  3. 并发晒图    收礼人 + 送礼人同时 PUT /received-gift 同一 match
                 → 无 500；最终 match 一份完整数据
  4. 并发点赞    同用户 10 线程 POST /gift-wall/like 同一 match
                 → 全 200；DB gift_likes 恰 1 行（不重复）
  5. 并发重置码  同账号 5 线程 POST /auth/forgot-password
                 → 全 200；DB 恰 1 个有效码；恰 1 个响应码 == DB 码（新码覆盖旧码）
附加：压测全程 /api/health 可用性 + 延迟监测（>1s 记为阻塞）。

用法：.venv/bin/python .audit/stress_test.py [--rounds 20] [--base http://127.0.0.1:8080]
退出码：0 = 全部通过；1 = 存在失败轮。
"""
import argparse
import http.client
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

BASE = "http://127.0.0.1:8080"
HOST = "127.0.0.1"
PORT = 8080
PASSWORD = "Stress123!"
ROUNDS = 20

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "gift_exchange.db"))


# ---------- HTTP helpers ----------

def _conn():
    return http.client.HTTPConnection(HOST, PORT, timeout=30)


def req(method, path, token=None, body=None):
    """发请求，返回 (status, json)。超时/断连抛异常（调用方按失败处理）。"""
    c = _conn()
    try:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body)
        else:
            payload = None
        c.request(method, path, body=payload, headers=headers)
        r = c.getresponse()
        raw = r.read()
        status = r.status
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            data = {"message": raw.decode("utf-8", "replace")[:200]}
        return status, data
    finally:
        c.close()


def register(username):
    status, body = req("POST", "/api/auth/register", body={
        "username": username, "email": f"{username}@stress.test", "password": PASSWORD,
    })
    assert status == 201, f"register {username} -> {status} {body}"
    return login(username)


def login(username):
    status, body = req("POST", "/api/auth/login", body={"username": username, "password": PASSWORD})
    assert status == 200, f"login {username} -> {status} {body}"
    return body["data"]["token"]


def create_event(token, title, max_participants=None):
    payload = {"title": title}
    if max_participants is not None:
        payload["maxParticipants"] = max_participants
    status, body = req("POST", "/api/events", token=token, body=payload)
    assert status == 201, f"create event -> {status} {body}"
    return body["data"]["code"]


def join(token, code):
    return req("POST", f"/api/events/{code}/join", token=token, body={})


def draw(token, code):
    return req("POST", f"/api/events/{code}/draw", token=token)


# ---------- DB helpers（SQLite 直读真值；WAL 下并发读安全） ----------

def db_conn():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout = 10000")
    return c


def db_one(sql, params=()):
    with db_conn() as c:
        row = c.execute(sql, params).fetchone()
        return dict(row) if row else None


def db_all(sql, params=()):
    with db_conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def db_exec(sql, params=()):
    with db_conn() as c:
        c.execute(sql, params)


def event_id_by_code(code):
    row = db_one("SELECT id FROM events WHERE code = ?", (code,))
    assert row, f"event {code} not in DB"
    return row["id"]


def cleanup(tag):
    """删除本轮压力数据：先活动（级联 participants/matches/likes/notifications）再用户。"""
    db_exec("DELETE FROM events WHERE code LIKE ?", (f"stress_{tag}_%",))
    db_exec("DELETE FROM users WHERE username LIKE ?", (f"stress_{tag}_%",))


# ---------- 场景 ----------

def scenario_draw(tag, token_creator, code, n=8):
    """8 线程同时抽签 → 恰 1×200 + 7×409，matches 恰一份。"""
    barrier = threading.Barrier(n)
    results = [None] * n

    def worker(i):
        barrier.wait()
        results[i] = draw(token_creator, code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(r[0] for r in results)
    assert statuses == [200] + [409] * (n - 1), f"draw 状态分布异常: {statuses}（{results}）"
    eid = event_id_by_code(code)
    match_count = db_one("SELECT COUNT(*) AS c FROM matches WHERE event_id = ?", (eid,))["c"]
    assert match_count == n, f"matches 应为 {n} 条，实际 {match_count}"
    status = db_one("SELECT status FROM events WHERE id = ?", (eid,))["status"]
    assert status == "drawn", f"活动状态应为 drawn，实际 {status}"
    return {"statuses": statuses, "matches": match_count}


def scenario_join(tag, token_creator, n_joiners=12, max_ppl=8):
    """12 线程并发 join 空位 8 的活动 → 恰 8×201 + 4×400，participants 恰 8。"""
    code = create_event(token_creator, f"stress_{tag}_join", max_participants=max_ppl)
    eid = event_id_by_code(code)
    # 创建者自动加入占 1 位：直接清掉创建者席位，使空位 = max_ppl，压力数字精确
    db_exec("DELETE FROM participants WHERE event_id = ?", (eid,))
    db_exec("UPDATE events SET participant_count = 0 WHERE id = ?", (eid,))

    tokens = [register(f"stress_{tag}_join_u{i}") for i in range(n_joiners)]
    barrier = threading.Barrier(n_joiners)
    results = [None] * n_joiners

    def worker(i):
        barrier.wait()
        results[i] = join(tokens[i], code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_joiners)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(r[0] for r in results)
    assert statuses == [201] * max_ppl + [400] * (n_joiners - max_ppl), f"join 状态分布异常: {statuses}（{results}）"
    count = db_one("SELECT COUNT(*) AS c FROM participants WHERE event_id = ?", (eid,))["c"]
    assert count == max_ppl, f"participants 应为 {max_ppl}，实际 {count}"
    stored = db_one("SELECT participant_count FROM events WHERE id = ?", (eid,))["participant_count"]
    assert stored == max_ppl, f"events.participant_count 应为 {max_ppl}，实际 {stored}"
    return {"statuses": statuses, "participants": count}


def _draw_event_with_matches(tag, token_creator):
    """建 3 人活动并抽签，返回 (code, matches: [{id, giver_user, receiver_user}])。"""
    code = create_event(token_creator, f"stress_{tag}_gift")
    t1 = register(f"stress_{tag}_gift_m1")
    t2 = register(f"stress_{tag}_gift_m2")
    join(t1, code)
    join(t2, code)
    status, body = draw(token_creator, code)
    assert status == 200, f"draw -> {status} {body}"
    eid = event_id_by_code(code)
    rows = db_all(
        """
        SELECT m.id, g.user_id AS giver_user, r.user_id AS receiver_user
        FROM matches m
        JOIN participants g ON g.id = m.giver_id
        JOIN participants r ON r.id = m.receiver_id
        WHERE m.event_id = ?
        """,
        (eid,),
    )
    return code, rows


def login_user_for(tag, user_id):
    """按 user_id 找回本轮压测用户 token（用户是 register 创建的，密码统一）。"""
    row = db_one("SELECT username FROM users WHERE id = ?", (user_id,))
    assert row and row["username"].startswith(f"stress_{tag}_"), f"非压测用户 {row}"
    return login(row["username"])


def scenario_received_gift(tag, token_creator):
    """收礼人 + 送礼人同时 PUT 同一 match → 无 500，最终一份数据。"""
    code, matches = _draw_event_with_matches(tag, token_creator)
    m = matches[0]
    t_recv = login_user_for(tag, m["receiver_user"])
    t_giver = login_user_for(tag, m["giver_user"])

    barrier = threading.Barrier(2)
    results = [None, None]

    def recv_put():
        barrier.wait()
        results[0] = req(
            "PUT", f"/api/events/{code}/received-gift", token=t_recv,
            body={"matchId": m["id"], "rating": 5, "review": f"并发晒图A-{tag}"},
        )

    def giver_put():
        barrier.wait()
        results[1] = req(
            "PUT", f"/api/events/{code}/received-gift", token=t_giver,
            body={"matchId": m["id"], "rating": 4, "review": f"并发晒图B-{tag}"},
        )

    threads = [threading.Thread(target=recv_put), threading.Thread(target=giver_put)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i, r in enumerate(results):
        assert r[0] != 500, f"received-gift 并发出现 500: {r}"
    statuses = sorted(r[0] for r in results)
    assert statuses == [200, 400], f"状态分布异常: {statuses}（{results}）"
    row = db_one(
        "SELECT gift_review, gift_rating, received_at FROM matches WHERE id = ?", (m["id"],)
    )
    assert row["gift_review"], "最终数据缺失 review"
    assert row["gift_rating"] is not None and 1 <= row["gift_rating"] <= 5
    assert row["received_at"], "最终数据缺失 received_at"

    # 同收礼人并发双 PUT：均 200，最终单值（最后写入者胜）
    barrier2 = threading.Barrier(2)
    results2 = [None, None]

    def recv_put_a():
        barrier2.wait()
        results2[0] = req(
            "PUT", f"/api/events/{code}/received-gift", token=t_recv,
            body={"matchId": m["id"], "rating": 5, "review": f"并发晒图A2-{tag}"},
        )

    def recv_put_b():
        barrier2.wait()
        results2[1] = req(
            "PUT", f"/api/events/{code}/received-gift", token=t_recv,
            body={"matchId": m["id"], "rating": 3, "review": f"并发晒图B2-{tag}"},
        )

    threads2 = [threading.Thread(target=recv_put_a), threading.Thread(target=recv_put_b)]
    for t in threads2:
        t.start()
    for t in threads2:
        t.join()
    for r in results2:
        assert r[0] == 200, f"同收礼人并发 PUT 非 200: {r}"
    final = db_one("SELECT gift_review FROM matches WHERE id = ?", (m["id"],))["gift_review"]
    assert final in (f"并发晒图A2-{tag}", f"并发晒图B2-{tag}"), f"最终 review 异常: {final!r}"
    review_count = db_one("SELECT COUNT(*) AS c FROM matches WHERE id = ?", (m["id"],))["c"]
    assert review_count == 1, "match 行数异常"
    return {"statuses": statuses, "finalReview": final}


def scenario_like(tag, token_creator, n_threads=10):
    """同用户 10 线程点赞同一 match → 全 200，gift_likes 恰 1 行。"""
    code, matches = _draw_event_with_matches(tag, token_creator)
    m = matches[0]
    t_user = login_user_for(tag, m["receiver_user"])
    # 先晒图（真实流程：礼物墙解锁后点赞；点赞权限本身 = 参与者即可）
    req("PUT", f"/api/events/{code}/received-gift", token=t_user,
        body={"matchId": m["id"], "rating": 5, "review": f"晒图-{tag}"})

    barrier = threading.Barrier(n_threads)
    results = [None] * n_threads

    def worker(i):
        barrier.wait()
        results[i] = req("POST", f"/api/events/{code}/gift-wall/like", token=t_user,
                         body={"matchId": m["id"]})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(r[0] for r in results)
    assert statuses == [200] * n_threads, f"like 状态分布异常: {statuses}（{results}）"
    like_count = db_one("SELECT COUNT(*) AS c FROM gift_likes WHERE match_id = ?", (m["id"],))["c"]
    assert like_count == 1, f"gift_likes 应恰 1 行，实际 {like_count}"
    return {"statuses": statuses, "likes": like_count}


def scenario_forgot(tag):
    """并发重置码：
    A) 同账号 5 线程 forgot-password → 全 200；DB 恰 1 个有效码；恰 1 个响应码 == DB 码
       （新码覆盖旧码逻辑）。
    B) 独立用户 1 次 forgot → 用 DB 真值码 reset-password → 成功、旧码清空、旧密码失效、
       新密码可登录（端到端验证「单码有效」）。
    注：forgot 与 reset 共用 IP+账号 5 次/小时限速窗口，A 的 5 次已耗尽预算，
    因此 B 用独立账号验证 reset 语义（不触发限速）。
    """
    username = f"stress_{tag}_forgot"
    register(username)
    n = 5
    barrier = threading.Barrier(n)
    results = [None] * n

    def worker(i):
        barrier.wait()
        results[i] = req("POST", "/api/auth/forgot-password", body={"username": username})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = [r[0] for r in results]
    assert statuses == [200] * n, f"forgot 状态分布异常: {statuses}（{results}）"
    row = db_one("SELECT reset_code, reset_code_expires_at FROM users WHERE username = ?", (username,))
    assert row and row["reset_code"], "DB 无重置码"
    assert len(row["reset_code"]) == 6 and row["reset_code"].isdigit(), f"码格式异常 {row['reset_code']!r}"
    resp_codes = [r[1]["data"]["code"] for r in results if r[1] and r[1].get("data")]
    matches = [c for c in resp_codes if c == row["reset_code"]]
    assert len(matches) == 1, f"应恰 1 个响应码 == DB 码，实际 {len(matches)}（响应 {resp_codes}，DB {row['reset_code']}）"

    # B) 端到端：独立用户单次 forgot → DB 码可重置密码
    u2 = f"stress_{tag}_reset_user"
    register(u2)
    s, _ = req("POST", "/api/auth/forgot-password", body={"username": u2})
    assert s == 200, f"forgot(u2) -> {s}"
    code2 = db_one("SELECT reset_code FROM users WHERE username = ?", (u2,))["reset_code"]
    new_pw = f"NewPass{tag}!1a"
    status, body = req("POST", "/api/auth/reset-password",
                       body={"username": u2, "code": code2, "newPassword": new_pw})
    assert status == 200, f"reset-password -> {status} {body}"
    cleared = db_one("SELECT reset_code FROM users WHERE username = ?", (u2,))["reset_code"]
    assert cleared is None, f"重置后 reset_code 应为空，实际 {cleared!r}"
    s_old, _ = req("POST", "/api/auth/login", body={"username": u2, "password": PASSWORD})
    assert s_old == 401, f"旧密码应失效，实际 {s_old}"
    s_new, b_new = req("POST", "/api/auth/login", body={"username": u2, "password": new_pw})
    assert s_new == 200, f"新密码登录失败 {s_new} {b_new}"
    return {"statuses": statuses, "singleCode": True}


# ---------- 健康监测 ----------

class HealthMonitor:
    def __init__(self, interval=0.1):
        self.latencies = []
        self.failures = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, args=(interval,), daemon=True)

    def _run(self, interval):
        while not self._stop.is_set():
            t0 = time.perf_counter()
            try:
                c = _conn()
                c.request("GET", "/api/health")
                r = c.getresponse()
                r.read()
                c.close()
                if r.status != 200:
                    self.failures += 1
            except Exception:
                self.failures += 1
            self.latencies.append((time.perf_counter() - t0) * 1000)
            self._stop.wait(interval)

    def start(self):
        self._t.start()

    def stop(self):
        self._stop.set()
        self._t.join(timeout=10)

    def stats(self):
        lat = sorted(self.latencies)
        if not lat:
            return {}
        n = len(lat)
        return {
            "samples": n,
            "failures": self.failures,
            "p50_ms": lat[n // 2],
            "p95_ms": lat[int(n * 0.95)],
            "p99_ms": lat[int(n * 0.99)],
            "max_ms": lat[-1],
        }


# ---------- 主流程 ----------

def main():
    global ROUNDS, BASE, HOST, PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    args = ap.parse_args()
    ROUNDS = args.rounds
    BASE = args.base.rstrip("/")
    u = urlparse(BASE)
    HOST, PORT = u.hostname, u.port

    # 服务连通性预检
    status, body = req("GET", "/api/health")
    assert status == 200, f"服务不可用: {status} {body}"

    monitor = HealthMonitor()
    monitor.start()

    # 每场景: list[round_result]
    results = {"draw": [], "join": [], "received_gift": [], "like": [], "forgot": []}
    failures = []

    for rnd in range(1, ROUNDS + 1):
        tag = f"r{rnd}_{uuid.uuid4().hex[:4]}"
        try:
            # 场景 1：并发抽签（创建者 + 7 成员 = 8 参与者）
            c_token = register(f"stress_{tag}_draw_c")
            code = create_event(c_token, f"stress_{tag}_draw")
            for i in range(7):
                join(register(f"stress_{tag}_draw_m{i}"), code)
            results["draw"].append(scenario_draw(tag, c_token, code))
            cleanup(tag)

            # 场景 2：并发加入
            c_token = register(f"stress_{tag}_join_c")
            results["join"].append(scenario_join(tag, c_token))
            cleanup(tag)

            # 场景 3：并发晒图
            c_token = register(f"stress_{tag}_gift_c")
            results["received_gift"].append(scenario_received_gift(tag, c_token))
            cleanup(tag)

            # 场景 4：并发点赞
            c_token = register(f"stress_{tag}_like_c")
            results["like"].append(scenario_like(tag, c_token))
            cleanup(tag)

            # 场景 5：并发重置码
            results["forgot"].append(scenario_forgot(tag))
            cleanup(tag)
        except Exception as exc:
            failures.append({"round": rnd, "tag": tag, "error": repr(exc)})
            try:
                cleanup(tag)
            except Exception:
                pass

    monitor.stop()
    health = monitor.stats()

    print("=" * 72)
    print(f"压力测试结果（{ROUNDS} 轮）")
    print("=" * 72)
    names = {
        "draw": "并发抽签（8线程）",
        "join": "并发加入（12线程/满8）",
        "received_gift": "并发晒图（收礼+送礼同PUT）",
        "like": "并发点赞（同用户10线程）",
        "forgot": "并发重置码（5线程）",
    }
    all_pass = True
    for key, label in names.items():
        rounds = results[key]
        ok_rounds = len(rounds)
        print(f"\n[{label}] 通过 {ok_rounds}/{ROUNDS} 轮")
        if not rounds:
            all_pass = False
            continue
        sample = rounds[0]
        if "statuses" in sample:
            dist = dict(sorted(Counter(sample["statuses"]).items()))
            print(f"  状态分布: {dist}")
        for field in ("participants", "matches", "likes"):
            if field in sample:
                print(f"  {field} 真值: {sample[field]}")
        if "singleCode" in sample:
            print(f"  单码有效: {sample['singleCode']}")

    print(f"\n[健康监测] 采样 {health.get('samples', 0)} 次，失败 {health.get('failures', 0)} 次，"
          f"p50={health.get('p50_ms', 0):.1f}ms p95={health.get('p95_ms', 0):.1f}ms "
          f"p99={health.get('p99_ms', 0):.1f}ms max={health.get('max_ms', 0):.1f}ms")

    if failures:
        all_pass = False
        print("\n[失败记录]")
        for f in failures:
            print(f"  轮次 {f['round']} tag={f['tag']}: {f['error']}")
            print(f"    复现: 以 stress_{f['tag']}_* 前缀重建用户/活动后重跑对应场景")

    print("\n" + ("ALL PASS" if all_pass else "HAS FAILURES"))
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
