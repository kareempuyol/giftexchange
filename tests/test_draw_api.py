"""抽签 API 集成测试（R4）：幂等 409、互避无解友好错误、状态/旧数据不变。

使用临时 SQLite 库 + Flask test client 走真实 HTTP 层验证 /api/events/<code>/draw。
"""
import os
import tempfile
import threading

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量。

    与其他测试文件共存：wxcloudrun 的 app 可能在收集阶段已被导入（如
    tests/test_notify.py 模块级导入），因此不能依赖 create_app 的副作用，
    这里显式调用 init_schema()；teardown 恢复 DB_PATH/JWT_SECRET，避免污染
    后续测试文件的数据库指向。
    """
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_r4_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-r4"
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()  # 幂等：CREATE TABLE IF NOT EXISTS，落在临时库
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
        # 治愈同仓其他测试文件的临时库：tests/test_notify.py 在模块级设置 DB_PATH
        # 但依赖“首次 import wxcloudrun 时建表”；若被 test_draw.py 的模块级 import
        # 抢先，其临时库无 schema。这里对临时目录下的库补一次幂等 init_schema
        # （绝不触碰开发库 data/gift_exchange.db，因为该路径不在临时目录下）。
        if saved_db and saved_db.startswith(tempfile.gettempdir()):
            try:
                from wxcloudrun.database import init_schema as _heal

                _heal()
            except Exception:
                pass


@pytest.fixture(scope="module")
def client(ctx):
    return ctx.test_client()


def register_and_login(client, name):
    """注册+登录，返回 (auth headers, user_id)。"""
    r = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@test.com", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()
    r = client.post("/api/auth/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}, data["user"]["id"]


def create_event(client, headers, title, excluded=None):
    payload = {"title": title}
    if excluded is not None:
        payload["excludedPairs"] = excluded
    r = client.post("/api/events", json=payload, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["code"]


def join_event(client, headers, code):
    r = client.post(f"/api/events/{code}/join", json={}, headers=headers)
    assert r.status_code == 201, r.get_json()


def event_status(client, headers, code):
    r = client.get(f"/api/events/{code}", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["status"]


def draw(client, headers, code):
    return client.post(f"/api/events/{code}/draw", headers=headers)


class TestDrawApi:
    def test_draw_success_and_second_draw_409(self, client):
        h1, _ = register_and_login(client, "r4_creator_ok")
        h2, _ = register_and_login(client, "r4_user_ok2")
        h3, _ = register_and_login(client, "r4_user_ok3")
        code = create_event(client, h1, "R4 OK event")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)

        r = draw(client, h1, code)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["code"] == 0
        assert len(body["data"]) == 3
        givers = {m["giverId"] for m in body["data"]}
        assert len(givers) == 3, "giver 不能重复"
        assert event_status(client, h1, code) == "drawn"

        # 已抽签再抽：409 幂等保护，且不重复写 matches（仍 3 条）
        r2 = draw(client, h1, code)
        assert r2.status_code == 409, r2.get_json()
        assert "already been drawn" in r2.get_json()["message"]
        rm = client.get(f"/api/events/{code}/matches", headers=h1)
        assert len(rm.get_json()["data"]) == 3

    def test_excluded_unsolvable_three_people(self, client):
        h1, uid1 = register_and_login(client, "r4_creator_excl")
        h2, uid2 = register_and_login(client, "r4_user_ex2")
        h3, _ = register_and_login(client, "r4_user_ex3")
        code = create_event(client, h1, "R4 excl event", excluded=[[uid1, uid2]])
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)

        r = draw(client, h1, code)
        assert r.status_code == 400, r.get_json()
        assert "互避规则太严格" in r.get_json()["message"]
        # 状态不变、无 matches 写入
        assert event_status(client, h1, code) == "open"
        rm = client.get(f"/api/events/{code}/matches", headers=h1)
        assert rm.status_code == 200
        assert rm.get_json()["data"] == []

    def test_two_people_rejected(self, client):
        h1, _ = register_and_login(client, "r4_creator_2p")
        h2, _ = register_and_login(client, "r4_user_2p")
        code = create_event(client, h1, "R4 two people")
        join_event(client, h1, code)
        join_event(client, h2, code)

        r = draw(client, h1, code)
        assert r.status_code == 400, r.get_json()
        assert "至少需要 3 人" in r.get_json()["message"]
        assert event_status(client, h1, code) == "open"

    def test_concurrent_draw_exactly_one_winner(self, ctx):
        # 并发双请求：恰一个 200、一个 409，且 matches 只有一份
        c1 = ctx.test_client()
        h1, _ = register_and_login(c1, "r4_creator_conc")
        h2, _ = register_and_login(c1, "r4_user_c2")
        h3, _ = register_and_login(c1, "r4_user_c3")
        code = create_event(c1, h1, "R4 concurrent")
        join_event(c1, h1, code)
        join_event(c1, h2, code)
        join_event(c1, h3, code)

        barrier = threading.Barrier(2)
        results = {}

        def do_draw(which):
            c = ctx.test_client()
            barrier.wait()  # 尽量同时发起
            r = c.post(f"/api/events/{code}/draw", headers=h1)
            results[which] = (r.status_code, r.get_json())

        threads = [threading.Thread(target=do_draw, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        codes = sorted(results[i][0] for i in range(2))
        assert codes == [200, 409], results
        # matches 只有一份（3 条），状态 drawn
        rm = c1.get(f"/api/events/{code}/matches", headers=h1)
        assert len(rm.get_json()["data"]) == 3
        assert event_status(c1, h1, code) == "drawn"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
