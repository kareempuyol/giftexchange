import secrets
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, render_template, request, send_from_directory

from wxcloudrun.auth import check_password, hash_password, sign_token, verify_token
from wxcloudrun.database import DB
from wxcloudrun.response import fail, ok


api = Blueprint("api", __name__, url_prefix="/api")
site = Blueprint("site", __name__)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def body():
    return request.get_json(silent=True) or {}


def public_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "displayName": row.get("display_name") or row["username"],
        "avatarUrl": row.get("avatar_url"),
        "createdAt": str(row.get("created_at") or ""),
    }


def api_event(row):
    return {
        "code": row["code"],
        "title": row["name"],
        "budget": row.get("budget_min") or 0,
        "note": row.get("description") or "",
        "drawDate": row.get("sign_up_deadline") or "",
        "status": row["status"],
        "ownerId": row["creator_id"],
        "ownerName": row.get("owner_username") or "",
        "participantCount": row.get("participant_count") or 0,
        "createdAt": str(row.get("created_at") or ""),
        "updatedAt": str(row.get("updated_at") or ""),
    }


def current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return verify_token(header[7:])


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return fail("请先登录", 401, -2)
        return fn(user, *args, **kwargs)

    return wrapper


def fetch_event(db, code):
    row = db.get(
        """
        SELECT e.*, u.username AS owner_username
        FROM events e JOIN users u ON u.id = e.creator_id
        WHERE e.code = ?
        """,
        (code,),
    )
    if not row:
        raise ValueError("活动不存在")
    return row


@api.route("/health")
def health():
    return ok({"status": "ok", "timestamp": now_iso()})


@site.route("/")
def index():
    return render_template("index.html")


@site.route("/assets/<path:filename>")
def vite_assets(filename):
    return send_from_directory("static/assets", filename)


@site.route("/<path:_path>")
def spa_fallback(_path):
    return render_template("index.html")


@api.route("/auth/register", methods=["POST"])
def register():
    data = body()
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")

    if not username or not email or not password:
        return fail("用户名、邮箱和密码为必填项")
    if len(username) < 2 or len(username) > 50:
        return fail("用户名长度应为 2-50 个字符")
    if "@" not in email or "." not in email or len(email) > 254:
        return fail("邮箱格式不正确")
    if len(password) < 6 or len(password) > 128:
        return fail("密码长度应为 6-128 位")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return fail("密码必须包含字母和数字")

    with DB() as db:
        conflicts = []
        if db.get("SELECT id FROM users WHERE username = ?", (username,)):
            conflicts.append("用户名")
        if db.get("SELECT id FROM users WHERE email = ?", (email,)):
            conflicts.append("邮箱")
        if conflicts:
            return fail("和".join(conflicts) + "已被占用", 409)

        cur = db.execute(
            "INSERT INTO users (username, email, password, display_name) VALUES (?, ?, ?, ?)",
            (username, email, hash_password(password), username),
        )
        user_id = cur.lastrowid
        row = db.get("SELECT * FROM users WHERE id = ?", (user_id,))
        return ok({"token": sign_token(user_id), "user": public_user(row)}, "注册成功", 201)


@api.route("/auth/login", methods=["POST"])
def login():
    data = body()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        return fail("用户名和密码为必填项")

    with DB() as db:
        row = db.get("SELECT * FROM users WHERE username = ?", (username,))
        if not row or not check_password(password, row["password"]):
            return fail("用户名或密码错误", 401)
        return ok({"token": sign_token(row["id"]), "user": public_user(row)}, "登录成功")


@api.route("/auth/me")
@login_required
def me(user):
    with DB() as db:
        row = db.get("SELECT * FROM users WHERE id = ?", (user["userId"],))
        if not row:
            return fail("用户不存在", 404)
        return ok(public_user(row))


@api.route("/events", methods=["POST"])
@login_required
def create_event(user):
    data = body()
    title = str(data.get("title") or "").strip()
    note = str(data.get("note") or "").strip()
    draw_date = str(data.get("drawDate") or "")
    budget = int(data.get("budget") or 0)

    if not title:
        return fail("活动标题为必填项")
    if len(title) > 100:
        return fail("活动标题不能超过 100 个字符")
    if budget < 0:
        return fail("预算不能为负数")
    if len(note) > 500:
        return fail("备注不能超过 500 个字符")

    with DB() as db:
        code = str(uuid.uuid4())
        db.execute(
            "INSERT INTO events (code, name, description, budget_min, creator_id, sign_up_deadline) VALUES (?, ?, ?, ?, ?, ?)",
            (code, title, note, budget, user["userId"], draw_date),
        )
        return ok(api_event(fetch_event(db, code)), "活动创建成功", 201)


@api.route("/events/mine")
@login_required
def my_events(user):
    with DB() as db:
        rows = db.all(
            """
            SELECT e.*, u.username AS owner_username
            FROM events e JOIN users u ON u.id = e.creator_id
            WHERE e.creator_id = ?
            ORDER BY e.created_at DESC
            """,
            (user["userId"],),
        )
        return ok([api_event(row) for row in rows])


@api.route("/events/joined")
@login_required
def joined_events(user):
    with DB() as db:
        rows = db.all(
            """
            SELECT e.*, u.username AS owner_username
            FROM participants p
            JOIN events e ON e.id = p.event_id
            JOIN users u ON u.id = e.creator_id
            WHERE p.user_id = ?
            ORDER BY e.created_at DESC
            """,
            (user["userId"],),
        )
        return ok([api_event(row) for row in rows])


@api.route("/events/<code>")
@login_required
def event_detail(_user, code):
    try:
        with DB() as db:
            return ok(api_event(fetch_event(db, code)))
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>", methods=["DELETE"])
@login_required
def delete_event(user, code):
    with DB() as db:
        event = db.get("SELECT id FROM events WHERE code = ? AND creator_id = ?", (code, user["userId"]))
        if not event:
            return fail("活动不存在或无权删除", 403)
        db.execute("DELETE FROM events WHERE id = ?", (event["id"],))
        return ok(None, "活动已删除")


@api.route("/events/<code>/join", methods=["POST"])
@login_required
def join_event(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] == user["userId"]:
                return fail("你是活动创建者，无需加入")
            if event["status"] != "open":
                return fail("活动已关闭，无法加入")
            if db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"])):
                return fail("你已加入该活动")
            user_row = db.get("SELECT username, display_name FROM users WHERE id = ?", (user["userId"],))
            nickname = user_row.get("display_name") or user_row["username"]
            cur = db.execute(
                "INSERT INTO participants (event_id, user_id, nickname) VALUES (?, ?, ?)",
                (event["id"], user["userId"], nickname),
            )
            db.execute(
                "UPDATE events SET participant_count = participant_count + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (event["id"],),
            )
            return ok({"id": cur.lastrowid, "eventCode": code, "userName": nickname}, "已加入活动", 201)
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/leave", methods=["DELETE"])
@login_required
def leave_event(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["status"] != "open":
                return fail("活动已抽签，无法退出")
            cur = db.execute("DELETE FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if cur.rowcount == 0:
                return fail("你尚未加入该活动")
            db.execute(
                "UPDATE events SET participant_count = participant_count - 1, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND participant_count > 0",
                (event["id"],),
            )
            return ok(None, "已退出活动")
    except ValueError as exc:
        return fail(str(exc), 404)


def participant_rows(db, event_id):
    return db.all(
        """
        SELECT p.id, p.user_id, p.nickname, p.created_at, u.username, u.display_name
        FROM participants p JOIN users u ON u.id = p.user_id
        WHERE p.event_id = ?
        ORDER BY p.created_at ASC
        """,
        (event_id,),
    )


@api.route("/events/<code>/participants")
@login_required
def participants(_user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            rows = participant_rows(db, event["id"])
            data = [
                {
                    "id": row["id"],
                    "userId": row["user_id"],
                    "username": row["username"],
                    "displayName": row.get("display_name") or row["nickname"] or row["username"],
                    "nickname": row["nickname"],
                    "joinedAt": str(row.get("created_at") or ""),
                }
                for row in rows
            ]
            return ok({"participants": data, "count": len(data)})
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/draw", methods=["POST"])
@login_required
def draw(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("仅活动创建者可执行抽签", 403)
            if event["status"] == "drawn":
                return fail("该活动已完成抽签")

            rows = participant_rows(db, event["id"])
            if len(rows) < 2:
                return fail("至少需要 2 人才能抽签")
            shuffled = rows[:]
            secrets.SystemRandom().shuffle(shuffled)
            db.execute("DELETE FROM matches WHERE event_id = ?", (event["id"],))
            matches = []
            for index, giver in enumerate(shuffled):
                receiver = shuffled[(index + 1) % len(shuffled)]
                cur = db.execute(
                    "INSERT INTO matches (event_id, giver_id, receiver_id) VALUES (?, ?, ?)",
                    (event["id"], giver["id"], receiver["id"]),
                )
                matches.append({
                    "id": cur.lastrowid,
                    "giverId": giver["id"],
                    "giverName": giver.get("display_name") or giver["nickname"] or giver["username"],
                    "receiverId": receiver["id"],
                    "receiverName": receiver.get("display_name") or receiver["nickname"] or receiver["username"],
                })
            db.execute("UPDATE events SET status = 'drawn', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event["id"],))
            return ok(matches, "抽签完成")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/my-match")
@login_required
def my_match(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return ok(None)
            row = db.get(
                """
                SELECT m.id, m.note, p.user_id AS receiver_user_id, u.username, u.display_name
                FROM matches m
                JOIN participants p ON p.id = m.receiver_id
                JOIN users u ON u.id = p.user_id
                WHERE m.event_id = ? AND m.giver_id = ?
                """,
                (event["id"], me["id"]),
            )
            if not row:
                return ok(None)
            return ok({
                "matchId": row["id"],
                "receiverId": row["receiver_user_id"],
                "receiverName": row["username"],
                "receiverDisplayName": row.get("display_name") or row["username"],
                "note": row.get("note") or "",
            })
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/note", methods=["PUT"])
@login_required
def update_note(user, code):
    data = body()
    match_id = data.get("matchId")
    note = str(data.get("note") or "")
    if not match_id:
        return fail("缺少 matchId")
    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return fail("你不是该活动的参与者", 403)
            cur = db.execute("UPDATE matches SET note = ? WHERE id = ? AND giver_id = ?", (note, match_id, me["id"]))
            if cur.rowcount == 0:
                return fail("未找到匹配记录")
            return ok(None, "备注已保存")
    except ValueError as exc:
        return fail(str(exc), 404)
