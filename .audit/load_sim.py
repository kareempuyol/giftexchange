#!/usr/bin/env python3
"""真实使用模式负载模拟（hackathon 轮16）。

50 个虚拟用户（线程池，每用户独立 token）像真人一样使用 5 分钟：
  40% 浏览列表/详情  25% 礼物墙/my-match  15% 操作（加入/发货/晒图/点赞）
  10% 通知          10% 混合（创建/抽签/归档）
每步动作之间随机延迟 0.5–3s。

隔离运行：脚本自动拉起独立 Flask 服务（--port，默认 8085），
DB 指向 --db-path（/tmp/load_sim.db，database.py 已支持 DB_PATH 覆盖），
stdout 结构化日志写 --log-file（供 error_500 / request 状态交叉核对）。
跑完自动停服并删除独立 DB（--keep 可保留现场）。

用法：
  .venv/bin/python .audit/load_sim.py --duration 300 --users 50
"""
import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = Path("/tmp/load_sim.db")
DEFAULT_LOG = Path("/tmp/load_sim_server.log")
PASSWORD = "Load1234"  # 满足强度规则：字母+数字，≥6 位

# ---- 行为分布（每用户每步独立抽样）----
GROUP_WEIGHTS = {
    "browse": 40,
    "gift": 25,
    "ops": 15,
    "notify": 10,
    "mixed": 10,
}
SUB_WEIGHTS = {
    "browse": {
        "events.public": 30,
        "events.mine": 20,
        "events.joined": 20,
        "events.detail": 15,
        "events.preview": 5,
        "events.participants": 5,
        "site.config": 5,
    },
    "gift": {
        "events.gift-wall": 40,
        "events.my-match": 30,
        "events.received-gift.get": 20,
        "events.matches": 10,
    },
    "ops": {
        "events.join": 25,
        "events.shipment": 25,
        "events.received-gift.put": 25,
        "events.like": 25,
    },
    "notify": {
        "notifications.list": 45,
        "notifications.read": 25,
        "notifications.prefs.get": 15,
        "notifications.prefs.put": 10,
        "notifications.clear": 5,
    },
    "mixed": {
        "events.create": 25,
        "events.draw": 25,
        "events.archive": 15,
        "events.unarchive": 10,
        "events.leave": 15,
        "events.remind": 5,
        "events.reset-short-code": 5,
    },
}

_stats_lock = threading.Lock()
RECORDS = []  # (group, status, ms)

# 全部虚拟用户（username, token），运行期"创建活动后邀请他人"用
SHARED_USERS = []


def record(group, status, ms, detail=None):
    with _stats_lock:
        RECORDS.append((group, status, ms, detail))


class Api:
    """单连接 HTTP 客户端（每线程一个），带 Bearer token。"""

    def __init__(self, host, port, token=None, xid=None, timeout=10):
        self.host = host
        self.port = port
        self.token = token
        self.xid = xid
        self.timeout = timeout
        self.conn = HTTPConnection(host, port, timeout=timeout)

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.xid:
            h["X-Request-ID"] = self.xid
        return h

    def request(self, method, path, body=None):
        """返回 (status, parsed_json_or_None)。连接异常抛 ConnectionError。"""
        payload = json.dumps(body, ensure_ascii=False) if body is not None else None
        if payload is not None:
            payload = payload.encode("utf-8")
        for attempt in (0, 1):
            try:
                self.conn.request(method, path, body=payload, headers=self._headers())
                resp = self.conn.getresponse()
                data = resp.read()
                status = resp.status
                try:
                    parsed = json.loads(data.decode("utf-8")) if data else None
                except Exception:
                    parsed = None
                if resp.will_close:
                    self.conn.close()
                    self.conn = HTTPConnection(self.host, self.port, timeout=self.timeout)
                return status, parsed
            except Exception:
                # 连接被服务端回收/超时：重建连接重试一次；仍失败抛给调用方
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = HTTPConnection(self.host, self.port, timeout=self.timeout)
                if attempt == 1:
                    raise
        raise ConnectionError("unreachable")  # pragma: no cover


def weighted_choice(rng, table):
    total = sum(table.values())
    x = rng.uniform(0, total)
    acc = 0.0
    for key, w in table.items():
        acc += w
        if x <= acc:
            return key
    return list(table)[-1]


# ================= 服务生命周期 =================

def server_alive(port):
    api = Api("127.0.0.1", port, xid="loadsim-health")
    try:
        status, parsed = api.request("GET", "/api/health")
        return status == 200 and parsed and parsed.get("code") == 0
    except Exception:
        return False
    finally:
        try:
            api.conn.close()
        except Exception:
            pass


def ensure_server(port, db_path, log_file):
    if server_alive(port):
        raise SystemExit(
            f"port {port} 已有服务在跑（可能不是独立 DB）。请换 --port 或先停掉该服务。"
        )
    env = os.environ.copy()
    env["DB_PATH"] = str(db_path)
    env.setdefault("JWT_SECRET", "gift-local-dev-2026")
    env["DEADLINE_SCANNER"] = "0"  # 后台截止扫描与本轮无关，关闭以免日志噪音
    log_fh = open(log_file, "ab")
    proc = subprocess.Popen(
        [sys.executable, "run.py", "127.0.0.1", str(port)],
        cwd=str(ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if server_alive(port):
            return proc
        if proc.poll() is not None:
            raise SystemExit(f"服务进程提前退出 rc={proc.returncode}，看 {log_file}")
        time.sleep(0.5)
    proc.kill()
    raise SystemExit(f"服务 30s 未就绪，看 {log_file}")


def stop_server(proc):
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


# ================= 种子数据 =================

def api_call(api, method, path, body=None):
    """种子阶段的单次调用：失败直接抛异常（种子失败 = 环境问题）。"""
    status, parsed = api.request(method, path, body)
    if status >= 400:
        raise RuntimeError(f"{method} {path} -> {status} {parsed}")
    return parsed["data"]


def seed_users(base, port, n, rng):
    """注册 + 登录 n 个用户，返回 [{'username','email','password','token','uid'}, ...]。"""
    users = []
    for i in range(n):
        username = f"load_{i:02d}_{rng.randint(1000, 9999)}"
        email = f"{username}@example.com"
        anon = Api(base, port, xid=f"loadsim-seed-{i}")
        status, parsed = anon.request(
            "POST", "/api/auth/register",
            {"username": username, "email": email, "password": PASSWORD},
        )
        if status not in (200, 201):
            raise RuntimeError(f"register {username} -> {status} {parsed}")
        token = parsed["data"]["token"]
        uid = parsed["data"]["user"]["id"]
        login = Api(base, port, xid=f"loadsim-seed-{i}")
        status, parsed = login.request(
            "POST", "/api/auth/login", {"username": username, "password": PASSWORD},
        )
        if status != 200:
            raise RuntimeError(f"login {username} -> {status} {parsed}")
        anon.conn.close()
        login.conn.close()
        users.append({"username": username, "email": email, "password": PASSWORD, "token": token, "uid": uid})
    return users


def seed_world(base, port, users, rng):
    """创建 14 个活动：10 个已抽签（含 4 个全员晒图解锁礼物墙）+ 4 个开放（留空位给 join）。

    返回 per-user 初始状态：
      {i: {'drawn': [codes], 'open': [codes], 'created_open': [codes], 'created_drawn': [codes], ...}}
    """
    api_by_user = {i: Api(base, port, token=users[i]["token"], xid=f"loadsim-{users[i]['username']}") for i in range(len(users))}
    state = {
        i: {"drawn": [], "open": [], "created_open": [], "created_drawn": []}
        for i in range(len(users))
    }
    n = len(users)
    drawn_events = []  # (code, creator_idx, member_idxs)
    open_events = []   # (code, creator_idx, member_idxs)

    def create_event(creator_idx, title, max_participants, members):
        api = api_by_user[creator_idx]
        data = api_call(
            api, "POST", "/api/events",
            {
                "title": title,
                "note": "负载模拟种子活动",
                "drawDate": "2026-09-01",
                "budget": rng.choice([50, 100, 200]),
                "maxParticipants": max_participants,
                "isPublic": True,
                "matchVisibility": "private",
            },
        )
        code = data["code"]
        for m in members:
            if m == creator_idx:
                continue
            api_call(api_by_user[m], "POST", f"/api/events/{code}/join", {})
        return code

    # 10 个抽签活动：creator + 3~6 名成员
    for k in range(10):
        creator = k
        pool = [i for i in range(n) if i != creator]
        members = rng.sample(pool, rng.randint(3, 6))
        code = create_event(creator, f"Load 抽签活动 {k:02d}", len(members) + 1, members)
        api_call(api_by_user[creator], "POST", f"/api/events/{code}/draw", {})
        drawn_events.append((code, creator, members))
        state[creator]["created_drawn"].append(code)
        for m in members + [creator]:
            state[m]["drawn"].append(code)

    # 4 个开放活动：creator + 2~3 名成员，上限 8（留空位给运行期 join）
    for k in range(4):
        creator = (len(users) - 4 + k) % len(users)
        pool = [i for i in range(n) if i != creator]
        members = rng.sample(pool, rng.randint(2, 3))
        code = create_event(creator, f"Load 开放活动 {k:02d}", 8, members)
        open_events.append((code, creator, members))
        state[creator]["created_open"].append(code)
        for m in members + [creator]:
            state[m]["open"].append(code)

    # 4 个抽签活动全员晒图 → 礼物墙解锁，like 有目标
    wall_events = drawn_events[:4]
    for code, creator, members in wall_events:
        for m in members + [creator]:
            api = api_by_user[m]
            data = api_call(api, "GET", f"/api/events/{code}/received-gift")
            if data and data.get("matchId"):
                api_call(
                    api, "PUT", f"/api/events/{code}/received-gift",
                    {
                        "matchId": data["matchId"],
                        "rating": rng.randint(3, 5),
                        "review": "礼物很用心，感谢！",
                        "privacy": rng.choice(["photo", "text", "blur"]),
                        "photoUrl": "",
                    },
                )
    # 少数几个 giver 填了物流（发货动作有历史数据可看）
    for code, creator, members in drawn_events[4:7]:
        giver = creator
        api = api_by_user[giver]
        data = api_call(api, "GET", f"/api/events/{code}/my-match")
        if data and data.get("matchId"):
            api_call(
                api, "PUT", f"/api/events/{code}/shipment",
                {
                    "matchId": data["matchId"],
                    "carrier": "顺丰速运",
                    "trackingNumber": f"SF{rng.randint(1000000000, 9999999999)}",
                    "status": "shipped",
                },
            )
    for api in api_by_user.values():
        try:
            api.conn.close()
        except Exception:
            pass
    return state, drawn_events, open_events


# ================= 运行期用户动作 =================

class UserWorker(threading.Thread):
    def __init__(self, idx, user, base, port, world, end_time, rng_seed):
        super().__init__(daemon=True)
        self.idx = idx
        self.user = user
        self.base = base
        self.port = port
        self.rng = random.Random(rng_seed)
        self.end_time = end_time
        # 线程私有状态（种子阶段给的是全量副本，运行期自行维护）
        self.drawn = list(world["state"][idx]["drawn"])
        self.open = list(world["state"][idx]["open"])
        self.created_open = list(world["state"][idx]["created_open"])
        self.created_drawn = list(world["state"][idx]["created_drawn"])
        self.archived = set()
        self.shipped = set()   # (code, matchId)
        self.reviewed = set()  # (code, matchId)
        self.liked = set()     # matchIds
        self.api = Api(base, port, token=user["token"], xid=f"loadsim-{user['username']}")

    # ---- 基础工具 ----
    def call(self, method, path, body=None):
        start = time.perf_counter()
        try:
            status, parsed = self.api.request(method, path, body)
            ms = round((time.perf_counter() - start) * 1000, 2)
            return status, parsed, ms, None
        except Exception as exc:
            ms = round((time.perf_counter() - start) * 1000, 2)
            return -1, None, ms, repr(exc)  # -1 = 网络错误/超时（两次尝试均失败）

    def do(self, group, method, path, body=None):
        result = self.call(method, path, body)
        status, parsed, ms = result[0], result[1], result[2]
        detail = result[3] if len(result) > 3 else None
        record(group, status, ms, detail)
        return status, parsed

    def refresh_lists(self):
        """重建 joined/mine 缓存（我的活动视图刷新）。"""
        status, joined = self.do("events.joined", "GET", "/api/events/joined")
        if status == 200 and joined and joined.get("code") == 0:
            self.drawn = []
            self.open = []
            for item in joined["data"] or []:
                if item.get("status") == "drawn":
                    self.drawn.append(item["code"])
                else:
                    self.open.append(item["code"])
        status, mine = self.do("events.mine", "GET", "/api/events/mine")
        if status == 200 and mine and mine.get("code") == 0:
            self.created_open = []
            self.created_drawn = []
            for item in mine["data"] or []:
                if item.get("status") == "drawn":
                    self.created_drawn.append(item["code"])
                else:
                    self.created_open.append(item["code"])

    # ---- 浏览（40%）----
    def act_browse(self, sub):
        rng = self.rng
        if sub == "events.public":
            params = ""
            if rng.random() < 0.3:
                params = "?search=" + quote(rng.choice(["Load", "礼物", "活动"]))
            elif rng.random() < 0.5:
                params = "?sort=" + rng.choice(["newest", "soonest"])
            self.do("events.public", "GET", "/api/events/public" + params)
        elif sub == "events.mine":
            self.do("events.mine", "GET", "/api/events/mine")
        elif sub == "events.joined":
            self.do("events.joined", "GET", "/api/events/joined")
        elif sub == "events.detail":
            code = rng.choice(self.drawn + self.open) if (self.drawn or self.open) else None
            if code:
                self.do("events.detail", "GET", f"/api/events/{code}")
            else:
                self.act_browse("events.public")
        elif sub == "events.preview":
            code = rng.choice(self.drawn + self.open) if (self.drawn or self.open) else None
            if code:
                self.do("events.preview", "GET", f"/api/events/{code}/preview")
            else:
                self.act_browse("site.config")
        elif sub == "events.participants":
            code = rng.choice(self.drawn + self.open) if (self.drawn or self.open) else None
            if code:
                self.do("events.participants", "GET", f"/api/events/{code}/participants")
            else:
                self.act_browse("events.public")
        else:  # site.config
            self.do("site.config", "GET", "/api/site/config")

    # ---- 礼物墙 / my-match（25%）----
    def act_gift(self, sub):
        rng = self.rng
        if sub == "events.gift-wall":
            if self.drawn:
                code = rng.choice(self.drawn)
                self.do("events.gift-wall", "GET", f"/api/events/{code}/gift-wall")
            else:
                self.act_browse("events.public")
        elif sub == "events.my-match":
            if self.drawn:
                code = rng.choice(self.drawn)
                self.do("events.my-match", "GET", f"/api/events/{code}/my-match")
            else:
                self.act_browse("events.joined")
        elif sub == "events.received-gift.get":
            if self.drawn:
                code = rng.choice(self.drawn)
                self.do("events.received-gift.get", "GET", f"/api/events/{code}/received-gift")
            else:
                self.act_browse("events.joined")
        else:  # events.matches（仅创建者可见）
            code = rng.choice(self.created_drawn) if self.created_drawn else None
            if code:
                self.do("events.matches", "GET", f"/api/events/{code}/matches")
            else:
                self.act_gift("events.gift-wall")

    # ---- 操作（15%）----
    def act_ops(self, sub):
        rng = self.rng
        if sub == "events.join":
            code = rng.choice(self.open) if self.open else None
            if code:
                self.do("events.join", "POST", f"/api/events/{code}/join", {})
            else:
                self.act_browse("events.public")
        elif sub == "events.shipment":
            code = rng.choice(self.drawn) if self.drawn else None
            if not code:
                self.act_browse("events.public")
                return
            status, parsed, _, _ = self.call("GET", f"/api/events/{code}/my-match")
            record("events.my-match", status, 0)
            if status == 200 and parsed and parsed.get("code") == 0 and parsed["data"]:
                match_id = parsed["data"]["matchId"]
                key = (code, match_id)
                if key not in self.shipped and (parsed["data"].get("shipmentState") or "pending") == "pending":
                    self.do(
                        "events.shipment", "PUT", f"/api/events/{code}/shipment",
                        {
                            "matchId": match_id,
                            "carrier": "顺丰速运",
                            "trackingNumber": f"SF{rng.randint(1000000000, 9999999999)}",
                            "status": "shipped",
                        },
                    )
                    self.shipped.add(key)
                else:
                    self.act_gift("events.gift-wall")
            else:
                self.act_gift("events.gift-wall")
        elif sub == "events.received-gift.put":
            code = rng.choice(self.drawn) if self.drawn else None
            if not code:
                self.act_browse("events.public")
                return
            status, parsed, _, _ = self.call("GET", f"/api/events/{code}/received-gift")
            record("events.received-gift.get", status, 0)
            if status == 200 and parsed and parsed.get("code") == 0 and parsed["data"]:
                match_id = parsed["data"]["matchId"]
                key = (code, match_id)
                if key not in self.reviewed:
                    self.do(
                        "events.received-gift.put", "PUT", f"/api/events/{code}/received-gift",
                        {
                            "matchId": match_id,
                            "rating": rng.randint(3, 5),
                            "review": "很棒的礼物，超喜欢！",
                            "privacy": rng.choice(["photo", "text", "blur"]),
                            "photoUrl": "",
                        },
                    )
                    self.reviewed.add(key)
                else:
                    self.act_gift("events.gift-wall")
            else:
                self.act_gift("events.gift-wall")
        else:  # events.like
            code = rng.choice(self.drawn) if self.drawn else None
            if not code:
                self.act_browse("events.public")
                return
            status, parsed, _, _ = self.call("GET", f"/api/events/{code}/gift-wall")
            record("events.gift-wall", status, 0)
            if status == 200 and parsed and parsed.get("code") == 0 and parsed["data"]:
                items = parsed["data"].get("items") or []
                if not items:
                    self.act_gift("events.my-match")
                    return
                item = rng.choice(items)
                mid = item["matchId"]
                if rng.random() < 0.2 and mid in self.liked:
                    self.do("events.like", "DELETE", f"/api/events/{code}/gift-wall/like?matchId={mid}")
                    self.liked.discard(mid)
                elif mid not in self.liked:
                    self.do("events.like", "POST", f"/api/events/{code}/gift-wall/like", {"matchId": mid})
                    self.liked.add(mid)
                else:
                    self.act_gift("events.my-match")
            else:
                self.act_gift("events.my-match")

    # ---- 通知（10%）----
    def act_notify(self, sub):
        rng = self.rng
        if sub == "notifications.list":
            self.do("notifications.list", "GET", "/api/notifications")
        elif sub == "notifications.read":
            self.do("notifications.read", "POST", "/api/notifications/read", {})
        elif sub == "notifications.prefs.get":
            self.do("notifications.prefs.get", "GET", "/api/notifications/preferences")
        elif sub == "notifications.prefs.put":
            self.do(
                "notifications.prefs.put", "PUT", "/api/notifications/preferences",
                {"draw": rng.random() < 0.5, "remind": rng.random() < 0.5},
            )
        else:  # clear
            self.do("notifications.clear", "POST", "/api/notifications/clear", {})

    # ---- 混合（10%：创建/抽签/归档）----
    def act_mixed(self, sub):
        rng = self.rng
        if sub == "events.create":
            code = self._create_event()
            if code:
                self.created_open.append(code)
                self.open.append(code)
                # 邀请 3 个其他用户加入（独立 join 请求，计入 events.join 统计）
                invitees = [u for u in SHARED_USERS if u["username"] != self.user["username"]]
                for u in self.rng.sample(invitees, min(3, len(invitees))):
                    guest = Api(self.base, self.port, token=u["token"], xid=f"loadsim-{u['username']}")
                    try:
                        start = time.perf_counter()
                        try:
                            st, parsed = guest.request("POST", f"/api/events/{code}/join", {})
                            ms = round((time.perf_counter() - start) * 1000, 2)
                            record("events.join", st, ms)
                        except Exception as exc:
                            ms = round((time.perf_counter() - start) * 1000, 2)
                            record("events.join", -1, ms, repr(exc))
                    finally:
                        try:
                            guest.conn.close()
                        except Exception:
                            pass
            else:
                self.act_browse("events.mine")
        elif sub == "events.draw":
            code = rng.choice(self.created_open) if self.created_open else None
            if code:
                status, parsed = self.do("events.draw", "POST", f"/api/events/{code}/draw", {})
                if status == 200 and parsed and parsed.get("code") == 0:
                    self.created_open.remove(code)
                    self.created_drawn.append(code)
                    if code in self.open:
                        self.open.remove(code)
                    self.drawn.append(code)
            else:
                self.act_browse("events.mine")
        elif sub == "events.archive":
            code = rng.choice(self.created_drawn) if self.created_drawn else None
            if code and code not in self.archived:
                self.do("events.archive", "POST", f"/api/events/{code}/archive", {})
                self.archived.add(code)
            else:
                self.act_browse("events.mine")
        elif sub == "events.unarchive":
            code = next(iter(self.archived), None)
            if code:
                self.do("events.unarchive", "POST", f"/api/events/{code}/unarchive", {})
                self.archived.discard(code)
            else:
                self.act_browse("events.mine")
        elif sub == "events.leave":
            candidate = [c for c in self.open if c not in self.created_open]
            code = rng.choice(candidate) if candidate else None
            if code:
                status, parsed = self.do("events.leave", "DELETE", f"/api/events/{code}/leave")
                if status == 200:
                    self.open.remove(code)
            else:
                self.act_browse("events.joined")
        elif sub == "events.remind":
            code = rng.choice(self.created_drawn) if self.created_drawn else None
            if code:
                self.do("events.remind", "POST", f"/api/events/{code}/remind", {})
            else:
                self.act_browse("events.mine")
        else:  # reset-short-code
            code = rng.choice(self.created_drawn + self.created_open) if (self.created_drawn or self.created_open) else None
            if code:
                self.do("events.reset-short-code", "POST", f"/api/events/{code}/reset-short-code", {})
            else:
                self.act_browse("events.mine")

    def _create_event(self):
        rng = self.rng
        status, parsed = self.do("events.create", "POST", "/api/events", {
            "title": f"Load 新活动 {rng.randint(1000, 9999)}",
            "note": "运行期创建",
            "drawDate": "2026-09-15",
            "budget": rng.choice([50, 100, 200]),
            "maxParticipants": 6,
            "isPublic": True,
            "matchVisibility": "private",
        })
        if status == 201 and parsed and parsed.get("code") == 0:
            return parsed["data"]["code"]
        return None

    def step(self):
        rng = self.rng
        group = weighted_choice(rng, GROUP_WEIGHTS)
        sub = weighted_choice(rng, SUB_WEIGHTS[group])
        if group == "browse":
            self.act_browse(sub)
        elif group == "gift":
            self.act_gift(sub)
        elif group == "ops":
            self.act_ops(sub)
        elif group == "notify":
            self.act_notify(sub)
        else:
            self.act_mixed(sub)
        # 周期性刷新个人活动视图（模拟用户回到列表页）
        if rng.random() < 0.08:
            self.refresh_lists()

    def run(self):
        try:
            while time.time() < self.end_time:
                self.step()
                time.sleep(self.rng.uniform(0.5, 3.0))
        finally:
            try:
                self.api.conn.close()
            except Exception:
                pass


# ================= 资源采样 =================

def sample_resources(proc, db_path, interval, stop_event, samples):
    while not stop_event.is_set():
        try:
            out = subprocess.run(
                ["ps", "-p", str(proc.pid), "-o", "rss=,pcpu="],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            rss_kb = pcpu = None
            if out:
                parts = out.split()
                rss_kb = int(parts[0])
                pcpu = float(parts[1])
        except Exception:
            rss_kb = pcpu = None
        try:
            size = db_path.stat().st_size
        except Exception:
            size = None
        wal_count = 0
        wal_size = 0
        for suffix in ("-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                wal_count += 1
                try:
                    wal_size += p.stat().st_size
                except Exception:
                    pass
        samples.append({"t": time.time(), "rss_kb": rss_kb, "pcpu": pcpu, "db_size": size, "wal_count": wal_count, "wal_size": wal_size})
        stop_event.wait(interval)


# ================= 统计 =================

def _pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_vals) else f
    return round(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f), 2)


def analyze(log_file):
    groups = {}
    net_details = []
    for group, status, ms, detail in RECORDS:
        d = groups.setdefault(group, {"n": 0, "lat": [], "codes": {}})
        d["n"] += 1
        d["lat"].append(ms)
        d["codes"][status] = d["codes"].get(status, 0) + 1
        if status == -1 and detail:
            net_details.append((group, detail, ms))

    rows = []
    total = sum(d["n"] for d in groups.values())
    total_2xx = 0
    total_5xx = 0
    total_net = 0
    for group, d in sorted(groups.items(), key=lambda kv: -kv[1]["n"]):
        lat = sorted(d["lat"])
        codes = d["codes"]
        n = d["n"]
        ok2 = sum(c for s, c in codes.items() if 200 <= s < 300)
        bad5 = sum(c for s, c in codes.items() if s >= 500)
        net = codes.get(-1, 0)
        total_2xx += ok2
        total_5xx += bad5
        total_net += net
        rows.append({
            "endpoint": group,
            "n": n,
            "ok": ok2,
            "ok_pct": round(ok2 * 100.0 / n, 1),
            "codes": {str(s): c for s, c in sorted(codes.items())},
            "p50": _pct(lat, 50),
            "p95": _pct(lat, 95),
            "p99": _pct(lat, 99),
            "max": round(max(lat), 2) if lat else None,
            "mean": round(sum(lat) / len(lat), 2) if lat else None,
        })

    # 服务端日志：error_500 事件 + request 日志里的 5xx 交叉核对
    server_errors = {}
    request_5xx = 0
    request_lines = 0
    if Path(log_file).exists():
        for line in Path(log_file).read_text(errors="replace").splitlines():
            if not line.strip().startswith("{"):
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            event = rec.get("event")
            if event == "error_500":
                server_errors["error_500"] = server_errors.get("error_500", 0) + 1
            elif event == "request":
                request_lines += 1
                if int(rec.get("status") or 0) >= 500:
                    request_5xx += 1
            elif event in ("login_failed", "login_success", "draw_success", "event_created", "draw_redraw", "password_reset_code_issued", "password_reset_unknown"):
                server_errors[event] = server_errors.get(event, 0) + 1

    return {
        "summary": {
            "total_requests": total,
            "2xx": total_2xx,
            "2xx_pct": round(total_2xx * 100.0 / total, 2) if total else None,
            "5xx": total_5xx,
            "5xx_pct": round(total_5xx * 100.0 / total, 2) if total else None,
            "network_errors": total_net,
            "4xx": total - total_2xx - total_5xx - total_net,
        },
        "per_endpoint": rows,
        "server_log": {
            "request_log_lines": request_lines,
            "request_5xx": request_5xx,
            "error_500_events": server_errors.get("error_500", 0),
            "business_events": {k: v for k, v in server_errors.items() if k != "error_500"},
        },
        "network_error_details": net_details,
    }


# ================= 主流程 =================

def main():
    ap = argparse.ArgumentParser(description="真实使用模式负载模拟")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--duration", type=float, default=300, help="运行秒数（默认 300 = 5 分钟）")
    ap.add_argument("--port", type=int, default=8085)
    ap.add_argument("--db-path", type=str, default=os.getenv("LOAD_DB_PATH", str(DEFAULT_DB)),
                    help="独立 DB 路径（默认 /tmp/load_sim.db；也读 LOAD_DB_PATH 环境变量）")
    ap.add_argument("--log-file", type=str, default=str(DEFAULT_LOG))
    ap.add_argument("--seed", type=int, default=20260810)
    ap.add_argument("--keep", action="store_true", help="跑完保留服务/DB/日志现场")
    ap.add_argument("--out", type=str, default=str(ROOT / ".audit" / "load_results.json"))
    args = ap.parse_args()

    base = "127.0.0.1"
    db_path = Path(args.db_path)
    log_file = Path(args.log_file)
    # 清理上次残留
    for p in [db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")]:
        if p.exists() and not args.keep:
            p.unlink(missing_ok=True)

    print(f"[load] 启动隔离服务 :{args.port} DB={db_path}")
    proc = ensure_server(args.port, db_path, log_file)
    try:
        rng = random.Random(args.seed)
        print(f"[load] 注册 {args.users} 用户…")
        users = seed_users(base, args.port, args.users, rng)
        global SHARED_USERS
        SHARED_USERS = [{"username": u["username"], "token": u["token"]} for u in users]
        print(f"[load] 播种活动世界…")
        state, drawn_events, open_events = seed_world(base, args.port, users, rng)
        world = {"state": state, "drawn": drawn_events, "open": open_events}
        print(f"[load] 种子完成：{len(drawn_events)} 抽签活动 / {len(open_events)} 开放活动")

        db_before = db_path.stat().st_size if db_path.exists() else 0
        stop = threading.Event()
        samples = []
        sampler = threading.Thread(
            target=sample_resources, args=(proc, db_path, 5, stop, samples), daemon=True
        )
        sampler.start()

        end_time = time.time() + args.duration
        print(f"[load] 开始 {args.duration:.0f}s 负载（{args.users} 用户 × 0.5-3s 节奏）…")
        t0 = time.time()
        workers = [
            UserWorker(i, users[i], base, args.port, world, end_time, args.seed + i * 7919)
            for i in range(args.users)
        ]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        elapsed = time.time() - t0
        stop.set()
        sampler.join(timeout=10)
        db_after = db_path.stat().st_size if db_path.exists() else 0

        print(f"[load] 完成：{elapsed:.1f}s 内 {len(RECORDS)} 个请求")
        results = analyze(args.log_file)
        results["config"] = {
            "users": args.users,
            "duration_s": args.duration,
            "port": args.port,
            "db_path": str(db_path),
            "seed": args.seed,
        }
        results["resources"] = {
            "db_size_before": db_before,
            "db_size_after": db_after,
            "db_growth_bytes": db_after - db_before,
            "samples": samples,
            "rss_kb": {"min": min(s["rss_kb"] for s in samples if s["rss_kb"] is not None),
                       "max": max(s["rss_kb"] for s in samples if s["rss_kb"] is not None),
                       "avg": round(sum(s["rss_kb"] for s in samples if s["rss_kb"] is not None) / max(1, sum(1 for s in samples if s["rss_kb"] is not None)))},
            "pcpu": {"min": min(s["pcpu"] for s in samples if s["pcpu"] is not None),
                     "max": max(s["pcpu"] for s in samples if s["pcpu"] is not None),
                     "avg": round(sum(s["pcpu"] for s in samples if s["pcpu"] is not None) / max(1, sum(1 for s in samples if s["pcpu"] is not None)), 1)},
            "wal_count_max": max((s["wal_count"] for s in samples), default=0),
            "wal_size_max": max((s["wal_size"] for s in samples), default=0),
        }
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2))

        # 控制台摘要
        s = results["summary"]
        print("\n=== 汇总 ===")
        print(f"总请求 {s['total_requests']} | 2xx {s['2xx']} ({s['2xx_pct']}%) | "
              f"4xx {s['4xx']} | 5xx {s['5xx']} | 网络错误 {s['network_errors']}")
        print("=== 端点延迟 TOP（按请求数排序，p50/p95/p99 ms）===")
        for row in results["per_endpoint"]:
            print(f"{row['endpoint']:<26} n={row['n']:<5} ok={row['ok_pct']:>5}% "
                  f"p50={row['p50']:<7} p95={row['p95']:<7} p99={row['p99']:<8} max={row['max']}")
        print(f"=== 服务端日志：error_500={results['server_log']['error_500_events']} "
              f"request_5xx={results['server_log']['request_5xx']} ===")
        print(f"DB 增长 {results['resources']['db_growth_bytes']}B | "
              f"WAL {results['resources']['wal_count_max']} 文件 (max {results['resources']['wal_size_max']}B) | "
              f"RSS {results['resources']['rss_kb']['min']}~{results['resources']['rss_kb']['max']}KB "
              f"| CPU {results['resources']['pcpu']['avg']}% 平均")
        print(f"\n结果 JSON：{args.out}")
    finally:
        if not args.keep:
            stop_server(proc)
            for p in [db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")]:
                p.unlink(missing_ok=True)
            print(f"[load] 已停服并清理独立 DB")


if __name__ == "__main__":
    main()
