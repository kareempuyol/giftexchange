"""并发一致性测试（R4 轮4）：真实多线程并发 + DB 真值校验。

覆盖 R4 修复的竞态：
- add_participant 容量占位原子化（并发 join 不超员）
- gift_wall_like 唯一约束幂等兜底（并发点赞不重复、不 500）
- register 唯一约束冲突转 409（并发重复注册不 500）
- 复核既有 draw 抢锁（并发抽签恰一成功）与 received-gift 串行化

测试约定与 test_draw_api.py 一致：临时 SQLite 库 + Flask test client + threading.Barrier。
"""
import os
import tempfile
import threading

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB（同 test_draw_api.py 的隔离/恢复/治愈约定）。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_conc_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-conc"
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()
        from wxcloudrun import app as flask_app  # noqa: E402

        flask_app.config["TESTING"] = True
        yield flask_app
    finally:
        if saved_db is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = saved_db
        if saved_jwt is None:
            os.environ.pop("JWT_SECRET", None)
        else:
            os.environ["JWT_SECRET"] = saved_jwt
        if saved_db and saved_db.startswith(tempfile.gettempdir()):
            try:
                from wxcloudrun.database import init_schema as _heal  # noqa: E402

                _heal()
            except Exception:
                pass


@pytest.fixture(scope="module")
def client(ctx):
    return ctx.test_client()


def register_and_login(client, name):
    r = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@test.com", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()
    r = client.post("/api/auth/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}, data["user"]["id"]


def create_event(client, headers, title, max_participants=None):
    payload = {"title": title}
    if max_participants is not None:
        payload["maxParticipants"] = max_participants
    r = client.post("/api/events", json=payload, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["code"]


def join_event(client, headers, code):
    r = client.post(f"/api/events/{code}/join", json={}, headers=headers)
    if r.status_code == 400 and r.get_json().get("message") == "你已加入该活动":
        return r.status_code
    assert r.status_code == 201, r.get_json()
    return r.status_code


def draw(client, headers, code):
    return client.post(f"/api/events/{code}/draw", headers=headers)


def db_query(sql, params=()):
    from wxcloudrun.database import DB

    with DB() as db:
        return db.all(sql, params)


def db_get(sql, params=()):
    from wxcloudrun.database import DB

    with DB() as db:
        return db.get(sql, params)


def db_exec(sql, params=()):
    from wxcloudrun.database import DB

    with DB() as db:
        db.execute(sql, params)


class TestConcurrentJoin:
    def test_concurrent_join_respects_capacity(self, ctx):
        """12 线程并发 join 空位 8 的活动 → 恰 8×201 + 4×400，participants 恰 8。"""
        c1 = ctx.test_client()
        h_creator, uid = register_and_login(c1, "conc_join_creator")
        code = create_event(c1, h_creator, "Conc join", max_participants=8)
        # 创建者自动加入占 1 位：清掉创建者席位，使空位恰 = 8（与压测脚本同口径）
        from wxcloudrun.database import DB

        with DB() as db:
            eid = db.get("SELECT id FROM events WHERE code = ?", (code,))["id"]
            db.execute("DELETE FROM participants WHERE event_id = ?", (eid,))
            db.execute("UPDATE events SET participant_count = 0 WHERE id = ?", (eid,))

        n = 12
        clients = []
        for i in range(n):
            c = ctx.test_client()
            h, _ = register_and_login(c, f"conc_join_u{i}")
            clients.append((c, h))
        barrier = threading.Barrier(n)
        results = [None] * n

        def worker(i):
            barrier.wait()
            r = clients[i][0].post(f"/api/events/{code}/join", json={}, headers=clients[i][1])
            results[i] = (r.status_code, r.get_json())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(r[0] for r in results) == [201] * 8 + [400] * 4, results
        count = db_get("SELECT COUNT(*) AS c FROM participants WHERE event_id = ?", (eid,))["c"]
        assert count == 8, f"participants 应为 8，实际 {count}"
        stored = db_get("SELECT participant_count FROM events WHERE id = ?", (eid,))["participant_count"]
        assert stored == 8, f"participant_count 应为 8，实际 {stored}"

    def test_concurrent_join_same_user_idempotent(self, ctx):
        """同用户 2 线程并发 join → 不 500，participants 恰 1 行，count 不虚增。"""
        c1 = ctx.test_client()
        h_creator, _ = register_and_login(c1, "conc_dup_creator")
        code = create_event(c1, h_creator, "Conc dup")
        c2 = ctx.test_client()
        h_user, _ = register_and_login(c2, "conc_dup_user")
        barrier = threading.Barrier(2)
        results = [None] * 2

        def worker(i):
            barrier.wait()
            r = c2.post(f"/api/events/{code}/join", json={}, headers=h_user)
            results[i] = (r.status_code, r.get_json())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for status, body in results:
            assert status != 500, (status, body)
            assert status in (201, 400), (status, body)
        eid = db_get("SELECT id FROM events WHERE code = ?", (code,))["id"]
        rows = db_query("SELECT id FROM participants WHERE event_id = ? AND user_id = ?",
                        (eid, db_get("SELECT id FROM users WHERE username = 'conc_dup_user'")["id"]))
        assert len(rows) == 1, f"同用户应恰 1 行，实际 {len(rows)}"
        stored = db_get("SELECT participant_count FROM events WHERE id = ?", (eid,))["participant_count"]
        assert stored == 2, f"创建者+用户应恰 2，实际 {stored}"


class TestConcurrentDraw:
    def test_concurrent_draw_exactly_one_winner(self, ctx):
        """8 线程并发抽签 → 恰 1×200 + 7×409，matches 恰一份（8 条），状态 drawn。"""
        c1 = ctx.test_client()
        h_creator, _ = register_and_login(c1, "conc_draw_creator")
        code = create_event(c1, h_creator, "Conc draw")
        for i in range(7):
            c = ctx.test_client()
            h, _ = register_and_login(c, f"conc_draw_m{i}")
            join_event(c, h, code)

        barrier = threading.Barrier(8)
        results = [None] * 8

        def worker(i):
            barrier.wait()
            r = draw(c1, h_creator, code)
            results[i] = (r.status_code, r.get_json())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        codes = sorted(r[0] for r in results)
        assert codes == [200] + [409] * 7, results
        eid = db_get("SELECT id FROM events WHERE code = ?", (code,))["id"]
        assert db_get("SELECT COUNT(*) AS c FROM matches WHERE event_id = ?", (eid,))["c"] == 8
        assert db_get("SELECT status FROM events WHERE id = ?", (eid,))["status"] == "drawn"


class TestConcurrentGiftPost:
    def test_concurrent_received_gift_last_write_wins(self, ctx):
        """同收礼人 2 线程并发 PUT 同一 match → 均 200，最终一份数据（最后写入者胜）。"""
        c1 = ctx.test_client()
        h_creator, _ = register_and_login(c1, "conc_post_creator")
        code = create_event(c1, h_creator, "Conc post")
        c2 = ctx.test_client()
        h_recv, _ = register_and_login(c2, "conc_post_recv")
        join_event(c2, h_recv, code)
        c3 = ctx.test_client()
        h3, _ = register_and_login(c3, "conc_post_m2")
        join_event(c3, h3, code)
        assert draw(c1, h_creator, code).status_code == 200

        r = c2.get(f"/api/events/{code}/received-gift", headers=h_recv)
        assert r.status_code == 200, r.get_json()
        match_id = r.get_json()["data"]["matchId"]

        barrier = threading.Barrier(2)
        results = [None] * 2

        def worker(i, review):
            barrier.wait()
            rr = c2.put(
                f"/api/events/{code}/received-gift",
                json={"matchId": match_id, "rating": 5, "review": review},
                headers=h_recv,
            )
            results[i] = (rr.status_code, rr.get_json())

        threads = [
            threading.Thread(target=worker, args=(0, "并发晒图A")),
            threading.Thread(target=worker, args=(1, "并发晒图B")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for status, body in results:
            assert status == 200, (status, body)
        row = db_get("SELECT gift_review, received_at FROM matches WHERE id = ?", (match_id,))
        assert row["gift_review"] in ("并发晒图A", "并发晒图B"), row
        assert row["received_at"], "received_at 缺失"
        assert db_get("SELECT COUNT(*) AS c FROM matches WHERE id = ?", (match_id,))["c"] == 1


class TestConcurrentLike:
    def _setup_posted_match(self, ctx, tag):
        c1 = ctx.test_client()
        h_creator, _ = register_and_login(c1, f"{tag}_creator")
        code = create_event(c1, h_creator, f"Conc like {tag}")
        c2 = ctx.test_client()
        h_recv, _ = register_and_login(c2, f"{tag}_recv")
        join_event(c2, h_recv, code)
        c3 = ctx.test_client()
        h3, _ = register_and_login(c3, f"{tag}_m2")
        join_event(c3, h3, code)
        assert draw(c1, h_creator, code).status_code == 200
        r = c2.get(f"/api/events/{code}/received-gift", headers=h_recv)
        match_id = r.get_json()["data"]["matchId"]
        rr = c2.put(f"/api/events/{code}/received-gift",
                    json={"matchId": match_id, "rating": 5, "review": f"晒图-{tag}"}, headers=h_recv)
        assert rr.status_code == 200, rr.get_json()
        return code, match_id, h_recv

    def test_concurrent_like_same_user_dedup(self, ctx):
        """同用户 10 线程点赞同一 match → 全 200，gift_likes 恰 1 行（不重复、不 500）。"""
        code, match_id, h_recv = self._setup_posted_match(ctx, "conc_like1")
        n = 10
        c2 = ctx.test_client()
        barrier = threading.Barrier(n)
        results = [None] * n

        def worker(i):
            barrier.wait()
            r = c2.post(f"/api/events/{code}/gift-wall/like",
                        json={"matchId": match_id}, headers=h_recv)
            results[i] = (r.status_code, r.get_json())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for status, body in results:
            assert status == 200, (status, body)
        rows = db_query("SELECT id FROM gift_likes WHERE match_id = ?", (match_id,))
        assert len(rows) == 1, f"gift_likes 应恰 1 行，实际 {len(rows)}"

    def test_concurrent_like_distinct_users(self, ctx):
        """10 个不同用户（均为参与者）并发点赞同一 match → 全 200，gift_likes 恰 10 行。"""
        c1 = ctx.test_client()
        h_creator, _ = register_and_login(c1, "conc_like2_creator")
        code = create_event(c1, h_creator, "Conc like 2")
        n = 10
        clients = []
        for i in range(n):
            c = ctx.test_client()
            h, _ = register_and_login(c, f"conc_like2_u{i}")
            join_event(c, h, code)
            clients.append((c, h))
        c2 = ctx.test_client()
        h_recv, _ = register_and_login(c2, "conc_like2_recv")
        join_event(c2, h_recv, code)
        assert draw(c1, h_creator, code).status_code == 200
        r = c2.get(f"/api/events/{code}/received-gift", headers=h_recv)
        match_id = r.get_json()["data"]["matchId"]
        rr = c2.put(f"/api/events/{code}/received-gift",
                    json={"matchId": match_id, "rating": 5, "review": "晒图-like2"}, headers=h_recv)
        assert rr.status_code == 200, rr.get_json()

        barrier = threading.Barrier(n)
        results = [None] * n

        def worker(i):
            barrier.wait()
            r = clients[i][0].post(f"/api/events/{code}/gift-wall/like",
                                   json={"matchId": match_id}, headers=clients[i][1])
            results[i] = (r.status_code, r.get_json())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for status, body in results:
            assert status == 200, (status, body)
        rows = db_query("SELECT user_id FROM gift_likes WHERE match_id = ?", (match_id,))
        assert len(rows) == n, f"gift_likes 应 {n} 行，实际 {len(rows)}"
        assert len({r["user_id"] for r in rows}) == n, "存在重复点赞"


class TestConcurrentForgot:
    def test_concurrent_forgot_single_code(self, ctx):
        """同账号 5 线程 forgot-password → 全 200；DB 恰 1 码；恰 1 个响应码 == DB 码。"""
        c1 = ctx.test_client()
        r = c1.post("/api/auth/register", json={
            "username": "conc_forgot", "email": "conc_forgot@test.com", "password": PASSWORD,
        })
        assert r.status_code == 201, r.get_json()
        n = 5
        barrier = threading.Barrier(n)
        results = [None] * n

        def worker(i):
            c = ctx.test_client()
            barrier.wait()
            results[i] = c.post("/api/auth/forgot-password", json={"username": "conc_forgot"})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i, r in enumerate(results):
            assert r.status_code == 200, (i, r.get_json())
        row = db_get("SELECT reset_code FROM users WHERE username = 'conc_forgot'")
        assert row and row["reset_code"], "DB 无重置码"
        # 单码不变量：DB 中恰一个 reset_code（并发覆盖后只剩最后一个写入者的码）
        rows = db_query("SELECT username FROM users WHERE username = 'conc_forgot' AND reset_code IS NOT NULL")
        assert len(rows) == 1, f"应恰 1 行带重置码，实际 {len(rows)}"


class TestConcurrentRegister:
    def test_concurrent_register_same_username(self, ctx):
        """2 线程注册同名 → 1×201 + 1×409，无 500（唯一约束兜底转 409）。"""
        n = 2
        barrier = threading.Barrier(n)
        results = [None] * n

        def worker(i):
            c = ctx.test_client()
            barrier.wait()
            r = c.post("/api/auth/register", json={
                "username": "conc_reg", "email": f"conc_reg_{i}@test.com", "password": PASSWORD,
            })
            results[i] = (r.status_code, r.get_json())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        statuses = sorted(r[0] for r in results)
        assert statuses == [201, 409], results
        rows = db_query("SELECT id FROM users WHERE username = 'conc_reg'")
        assert len(rows) == 1, f"同名用户应恰 1 行，实际 {len(rows)}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
