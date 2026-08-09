#!/usr/bin/env python3
"""性能二次复测：造规模数据（50 活动×5 人+100 通知）→ curl 计时 9 接口（5 次中位数）→ 清理。

与轮 2 同法：SQLite 直连造数、curl time_total 计时、测后清理（按 PERF2 前缀标记）。
基线（轮 2 规模·优化后）写入结果 JSON 供报告对比。
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from statistics import median

BASE = "http://127.0.0.1:8080"
DB_PATH = os.path.expanduser("~/giftexchange/data/gift_exchange.db")
MARK = "PERF2"

# 轮 2 基线（PERF_REPORT.md「规模·优化后」列，ms 中位数）
BASELINE = {
    "/api/events/mine": 5.99,
    "/api/events/public": 4.73,
    "/api/events/<code>": 4.29,
    "/api/events/joined": 5.41,
    "/api/events/<code>/gift-wall": 4.53,
    "/api/events/<code>/participants": 4.86,
    "/api/notifications": 5.99,
    "/api/events/<code>/dashboard": 5.70,
    "/api/profile": 5.18,
}

END_POINTS = [
    ("/api/events/mine", "mine"),
    ("/api/events/public", "public"),
    ("/api/events/<code>", "detail"),
    ("/api/events/joined", "joined"),
    ("/api/events/<code>/gift-wall", "gift-wall"),
    ("/api/events/<code>/participants", "participants"),
    ("/api/notifications", "notifications"),
    ("/api/events/<code>/dashboard", "dashboard"),
    ("/api/profile", "profile"),
]


def login_token():
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{BASE}/api/auth/login", "-H", "Content-Type: application/json",
         "-d", json.dumps({"username": "verify_user", "password": "Verify123"})],
        capture_output=True, text=True,
    )
    data = json.loads(r.stdout)
    if data.get("code") != 0:
        raise SystemExit(f"login failed: {r.stdout}")
    return data["data"]["token"]


def db():
    return sqlite3.connect(DB_PATH, timeout=30)


def seed(conn):
    cur = conn.cursor()
    # 组织者 + 4 名新成员（每人可参与多个活动）
    cur.execute("SELECT id FROM users WHERE username = 'verify_user'")
    org = cur.fetchone()
    if not org:
        raise SystemExit("verify_user 不存在")
    org_id = org[0]
    member_ids = []
    for i in range(4):
        uname = f"perf2_member_{i}"
        cur.execute("SELECT id FROM users WHERE username = ?", (uname,))
        row = cur.fetchone()
        if row:
            member_ids.append(row[0])
        else:
            cur.execute(
                "INSERT INTO users (username, email, password, display_name) VALUES (?, ?, ?, ?)",
                (uname, f"{uname}@test.com", "!hashed!", uname),
            )
            member_ids.append(cur.lastrowid)
    event_ids = []
    for i in range(50):
        code = f"perf2-{uuid.uuid4().hex[:10]}"
        cur.execute(
            "INSERT INTO events (code, name, description, budget_min, creator_id, status, sign_up_deadline, participant_count, is_public, archived) "
            "VALUES (?, ?, ?, 50, ?, 'open', '2026-08-20T20:00', 5, 1, 0)",
            (code, f"性能测试活动 {MARK} {i:02d}", f"perf scale seed {MARK}", org_id),
        )
        event_ids.append((cur.lastrowid, code))
    # 参与者：组织者 + 4 成员；环形 matches（每人一个送礼对象）
    for eid, _code in event_ids:
        pids = []
        for uid in [org_id] + member_ids:
            cur.execute(
                "INSERT INTO participants (event_id, user_id, nickname, receiver_name, phone, address, preference_likes) "
                "VALUES (?, ?, ?, ?, '13800138000', '广东省深圳市南山区', '咖啡、书')",
                (eid, uid, f"成员{uid}", f"收件人{uid}"),
            )
            pids.append(cur.lastrowid)
        for k in range(5):
            giver, receiver = pids[k], pids[(k + 1) % 5]
            cur.execute(
                "INSERT INTO matches (event_id, giver_id, receiver_id, shipment_status, note) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (eid, giver, receiver, f"{MARK} 悄悄话"),
            )
    # 100 条通知（verify_user，跨事件）
    for i in range(100):
        eid = event_ids[i % 50][0]
        cur.execute(
            "INSERT INTO notifications (user_id, event_id, type, title, message) "
            "VALUES (?, ?, 'perf_seed', ?, ?)",
            (org_id, eid, f"{MARK} 通知 {i:03d}", f"{MARK} 性能测试通知 {i:03d}"),
        )
    conn.commit()
    print(f"seeded: 50 events, {len(event_ids)} codes, participants 5/event, matches 5/event, 100 notifications")
    return event_ids[0][1]  # 第一个活动短码（uuid code）


def time_curl(token, url):
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{time_total}", "-H", f"Authorization: Bearer {token}", url],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(r.stdout) * 1000  # s → ms
    except ValueError:
        raise SystemExit(f"curl timing failed for {url}: stdout={r.stdout!r} stderr={r.stderr!r}")


def cleanup(conn):
    cur = conn.cursor()
    cur.execute("SELECT id FROM events WHERE name LIKE ?", (f"%{MARK}%",))
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        ph = ",".join("?" for _ in ids)
        cur.execute(f"DELETE FROM matches WHERE event_id IN ({ph})", ids)
        cur.execute(f"DELETE FROM participants WHERE event_id IN ({ph})", ids)
        cur.execute(f"DELETE FROM notifications WHERE event_id IN ({ph})", ids)
        cur.execute(f"DELETE FROM events WHERE id IN ({ph})", ids)
    cur.execute("DELETE FROM notifications WHERE type = 'perf_seed'")
    cur.execute("DELETE FROM users WHERE username LIKE 'perf2_member_%'")
    conn.commit()
    print(f"cleanup: removed {len(ids)} perf events + members + 100 notifications")


def counts(conn):
    cur = conn.cursor()
    return {t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
            ("events", "participants", "matches", "notifications", "users")}


def main():
    token = login_token()
    conn = db()
    before = counts(conn)
    print("before:", before)
    sample_code = seed(conn)
    after_seed = counts(conn)
    print("after seed:", after_seed)
    # 预热 + 计时（5 次取中位数）
    warm = time_curl(token, f"{BASE}/api/events/mine")
    print(f"warm: {warm:.2f}ms")
    results = {}
    for tmpl, label in END_POINTS:
        url = BASE + tmpl.replace("<code>", sample_code)
        times = [time_curl(token, url) for _ in range(5)]
        results[label] = {"url": tmpl, "median_ms": round(median(times), 2), "times": [round(t, 2) for t in times]}
        print(f"{label:14s} median={results[label]['median_ms']:6.2f}ms  all={results[label]['times']}")
    cleanup(conn)
    after = counts(conn)
    print("after cleanup:", after)
    out = {
        "runAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "baselineRound2": BASELINE,
        "results": results,
        "counts": {"before": before, "afterSeed": after_seed, "afterCleanup": after},
    }
    with open(os.path.expanduser("~/giftexchange/.audit/perf2-results.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    conn.close()
    print("saved .audit/perf2-results.json")


if __name__ == "__main__":
    sys.exit(main())
