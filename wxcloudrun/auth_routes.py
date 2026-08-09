"""认证与账户路由（auth/*、profile、admin/settings、登录限速）。"""
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

from flask import request

from wxcloudrun.auth import check_password, hash_password, sign_token
from wxcloudrun.database import DB, integrity_errors
from wxcloudrun.helpers import (
    SETTING_DEFINITIONS,
    _split_env,
    admin_required,
    api,
    body,
    clear_login_attempts,
    client_ip,
    current_user_row,
    fail,
    log_event,
    login_required,
    ok,
    parse_datetime,
    public_user,
    rate_limit_login,
    record_failed_login,
    save_setting,
    setting_value,
    settings_payload,
)


@api.route("/auth/register", methods=["POST"])
def register():
    data = body()
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")

    if not username or not email or not password:
        return fail("用户名、邮箱和密码为必填项")
    if len(username) < 2 or len(username) > 50:
        return fail("用户名长度需为 2-50 个字符")
    if "@" not in email or "." not in email or len(email) > 254:
        return fail("邮箱格式不正确")
    if len(password) < 6 or len(password) > 128:
        return fail("密码长度需为 6-128 个字符")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return fail("密码必须同时包含字母和数字")

    with DB() as db:
        user_count = db.get("SELECT COUNT(*) AS count FROM users")["count"]
        registration_enabled = setting_value(db, "registration_enabled").lower() == "true"
        is_first_user = int(user_count) == 0
        if not registration_enabled and not is_first_user:
            return fail("注册已关闭", 403)

        conflicts = []
        if db.get("SELECT id FROM users WHERE username = ?", (username,)):
            conflicts.append("username")
        if db.get("SELECT id FROM users WHERE email = ?", (email,)):
            conflicts.append("email")
        if conflicts:
            return fail(" and ".join(conflicts) + " already exists", 409)

        admin_by_env = username.lower() in _split_env("ADMIN_USERNAMES") or email.lower() in _split_env("ADMIN_EMAILS")
        is_admin = 1 if is_first_user or admin_by_env else 0
        try:
            cur = db.execute(
                "INSERT INTO users (username, email, password, display_name, is_admin) VALUES (?, ?, ?, ?, ?)",
                (username, email, hash_password(password), username, is_admin),
            )
        except integrity_errors():
            # 并发重复注册：另一请求已插入同 username/email（SELECT 预检存在竞态窗口），
            # 落库后按唯一约束真值重查冲突字段，转 409（不吞成 500）
            conflicts = []
            if db.get("SELECT id FROM users WHERE username = ?", (username,)):
                conflicts.append("username")
            if db.get("SELECT id FROM users WHERE email = ?", (email,)):
                conflicts.append("email")
            return fail(" and ".join(conflicts) + " already exists", 409)
        user_id = cur.lastrowid
        row = current_user_row(db, user_id)
        return ok({"token": sign_token(user_id), "user": public_user(row)}, "Registered", 201)


@api.route("/auth/login", methods=["POST"])
def login():
    data = body()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        return fail("用户名和密码为必填项")

    # 登录限速：按 IP+用户名 双重限制，防暴力破解（IP 取真实客户端 IP，防 XFF 伪造）
    ip = client_ip()
    check, retry_after = rate_limit_login(ip, username)
    if not check:
        return fail(f"登录尝试过于频繁，请 {retry_after} 秒后再试", 429, headers={"Retry-After": str(retry_after)})

    with DB() as db:
        row = db.get("SELECT * FROM users WHERE username = ?", (username,))
        if not row:
            record_failed_login(ip, username)
            return fail("用户名或密码错误", 401)
        if row.get("deactivated"):
            return fail("账号已注销", 401)
        if not check_password(password, row["password"]):
            record_failed_login(ip, username)
            return fail("用户名或密码错误", 401)
        clear_login_attempts(ip, username)
        return ok({"token": sign_token(row["id"]), "user": public_user(row)}, "Signed in")


# ===== 找回密码限速（内存滑动窗口：IP+用户名 每小时最多 5 次）=====
_FORGOT_WINDOW_SECONDS = 60 * 60
_FORGOT_MAX_PER_KEY = 5
_forgot_attempts = {}  # (client_ip, account) -> [timestamp, ...]


def _forgot_rate_limited(client_ip, account):
    """检查并记录一次请求。返回 True 表示超过限速应拒绝（429）。"""
    now = time.time()
    stamps = _forgot_attempts.setdefault((client_ip, account), [])
    stamps[:] = [t for t in stamps if now - t < _FORGOT_WINDOW_SECONDS]
    if len(stamps) >= _FORGOT_MAX_PER_KEY:
        return True
    stamps.append(now)
    return False


@api.route("/auth/forgot-password", methods=["POST"])
def forgot_password():
    """生成 6 位数字重置码（15 分钟有效，单用户单码，新码覆盖旧码）。

    安全（P0 修复）：重置码绝不默认返回给请求方（否则任意人可重置他人密码）。
    - 默认（生产）：响应不含 code，应由邮件/短信通道异步下发；当前无通道时
      服务端 log_event 记录 code 供运维取用，前端提示「重置码已发送」。
    - 演示模式：显式设置环境变量 RESET_CODE_IN_RESPONSE=1 时响应才返回 code
      （仅限本地演示，上线不得开启）。
    - 账号不存在统一返回 200（无 code），不泄露账号是否注册（防枚举）。
    """
    data = body()
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    if not username and not email:
        return fail("用户名或邮箱不能为空")

    account = username or email
    ip = client_ip()
    if _forgot_rate_limited(ip, account):
        return fail("请求过于频繁，请 1 小时后再试", 429)

    demo_mode = os.getenv("RESET_CODE_IN_RESPONSE", "0").strip().lower() in ("1", "true", "yes")
    with DB() as db:
        if username:
            row = db.get("SELECT id FROM users WHERE username = ?", (username,))
        else:
            row = db.get("SELECT id FROM users WHERE email = ?", (email,))
        if not row:
            # 统一 200（无 code）：防账号枚举（原 404 会暴露账号是否注册）
            log_event("password_reset_unknown", account=account)
            return ok({"expiresIn": 15 * 60}, "重置码已发送")

        code = f"{secrets.randbelow(10**6):06d}"
        expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.execute(
            "UPDATE users SET reset_code = ?, reset_code_expires_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (code, expires.isoformat(), row["id"]),
        )
        log_event("password_reset_code_issued", user_id=row["id"])
        payload = {"expiresIn": 15 * 60}
        if demo_mode:
            payload["code"] = code
        return ok(payload, "重置码已生成")


@api.route("/auth/reset-password", methods=["POST"])
def reset_password():
    data = body()
    username = str(data.get("username") or "").strip()
    code = str(data.get("code") or "").strip()
    new_password = str(data.get("newPassword") or "")
    if not username or not code or not new_password:
        return fail("用户名、重置码和新密码均为必填")
    if len(code) != 6 or not code.isdigit():
        return fail("重置码无效，请检查后重试", 400)
    if len(new_password) < 6 or len(new_password) > 128:
        return fail("新密码长度需为 6-128 位")
    if not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
        return fail("新密码需包含字母和数字")

    # 防暴力猜码：与 forgot 共用 IP+账号 限速窗口（6 位码 100 万组合，无限速可几分钟内爆破）
    ip = client_ip()
    if _forgot_rate_limited(ip, username):
        return fail("尝试过于频繁，请 1 小时后再试", 429)

    with DB() as db:
        row = db.get("SELECT id, reset_code, reset_code_expires_at FROM users WHERE username = ?", (username,))
        if not row or not row.get("reset_code") or row["reset_code"] != code:
            return fail("重置码错误或已失效，请重新获取", 400)
        expires_at = parse_datetime(row["reset_code_expires_at"])
        if expires_at < datetime.now(timezone.utc):
            return fail("重置码已过期，请重新获取", 400)
        db.execute(
            "UPDATE users SET password = ?, reset_code = NULL, reset_code_expires_at = NULL, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (hash_password(new_password), row["id"]),
        )
        return ok(None, "密码重置成功，请用新密码登录")


@api.route("/auth/me")
@login_required
def me(user):
    with DB() as db:
        try:
            return ok(public_user(current_user_row(db, user["userId"])))
        except ValueError as exc:
            return fail(str(exc), 404)


@api.route("/profile")
@login_required
def get_profile(user):
    with DB() as db:
        try:
            return ok(public_user(current_user_row(db, user["userId"])))
        except ValueError as exc:
            return fail(str(exc), 404)


@api.route("/profile", methods=["PUT"])
@login_required
def update_profile(user):
    data = body()
    fields = {
        "display_name": str(data.get("displayName") or data.get("display_name") or "").strip(),
        "avatar_url": str(data.get("avatarUrl") or data.get("avatar_url") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "address": str(data.get("address") or "").strip(),
        "receiver_name": str(data.get("receiverName") or data.get("receiver_name") or "").strip(),
        "gift_preference": str(data.get("giftPreference") or data.get("gift_preference") or "").strip(),
    }
    if len(fields["display_name"]) > 120:
        return fail("昵称过长")
    if len(fields["phone"]) > 50:
        return fail("手机号过长")
    if len(fields["address"]) > 500:
        return fail("地址过长")

    with DB() as db:
        db.execute(
            """
            UPDATE users
            SET display_name = ?, avatar_url = ?, phone = ?, address = ?,
                receiver_name = ?, gift_preference = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                fields["display_name"],
                fields["avatar_url"],
                fields["phone"],
                fields["address"],
                fields["receiver_name"],
                fields["gift_preference"],
                user["userId"],
            ),
        )
        return ok(public_user(current_user_row(db, user["userId"])), "Profile saved")


@api.route("/profile/password", methods=["PUT"])
@login_required
def change_password(user):
    """修改密码：验证旧密码 → 设置新密码（沿用注册的强度规则）"""
    data = body()
    old_password = str(data.get("oldPassword") or "")
    new_password = str(data.get("newPassword") or "")
    if not old_password or not new_password:
        return fail("旧密码和新密码为必填项")
    if len(new_password) < 6 or len(new_password) > 128:
        return fail("新密码长度需为 6-128 个字符")
    if not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
        return fail("新密码必须同时包含字母和数字")

    with DB() as db:
        row = db.get("SELECT * FROM users WHERE id = ?", (user["userId"],))
        if not row:
            return fail("用户不存在", 404)
        if not check_password(old_password, row["password"]):
            return fail("旧密码不正确", 400)
        db.execute("UPDATE users SET password = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                   (hash_password(new_password), user["userId"]))
        return ok(None, "Password changed")


@api.route("/auth/deactivate", methods=["POST"])
@login_required
def deactivate_account(user):
    """注销账号：验证密码 → 匿名化用户（释放原名/邮箱，密码置随机串）→ 标记 deactivated。

    不物理删除（保留活动/礼物墙数据完整性）；login_required 对 deactivated 用户一律 401，
    已签发 JWT 立即失效，登录接口同样拒绝。
    """
    data = body()
    password = str(data.get("password") or "")
    if not password:
        return fail("Password is required", 400)

    with DB() as db:
        row = current_user_row(db, user["userId"])
        if row.get("deactivated"):
            return fail("账号已注销", 400)
        if not check_password(password, row["password"]):
            return fail("Password is incorrect", 400)
        user_id = row["id"]
        db.execute(
            """
            UPDATE users
            SET username = ?, email = ?, password = ?, display_name = ?,
                deactivated = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                f"deleted_{user_id}",
                f"deleted_{user_id}@deleted.local",
                hash_password(secrets.token_urlsafe(24)),
                "已注销用户",
                user_id,
            ),
        )
        return ok(None, "账号已注销")


@api.route("/auth/export-data")
@login_required
def export_data(user):
    """导出我的数据：个人资料 + 我创建/参与的活动 + 我的晒图记录。

    只读查询；各类数据量过大时截断到最近 100 条。
    """
    with DB() as db:
        row = current_user_row(db, user["userId"])
        profile = {
            "username": row["username"],
            "email": row["email"],
            "displayName": row.get("display_name") or row["username"],
            "phone": row.get("phone") or "",
            "address": row.get("address") or "",
            "preference": row.get("gift_preference") or "",
        }
        created_events = db.all(
            """
            SELECT name AS title, status, created_at AS date
            FROM events
            WHERE creator_id = ?
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (user["userId"],),
        )
        joined_events = db.all(
            """
            SELECT e.name AS title, e.status, p.created_at AS date
            FROM participants p
            JOIN events e ON e.id = p.event_id
            WHERE p.user_id = ?
            ORDER BY p.created_at DESC
            LIMIT 100
            """,
            (user["userId"],),
        )
        gift_posts = db.all(
            """
            SELECT e.name AS event_title, m.gift_rating AS rating,
                   m.gift_review AS review, m.received_at AS date
            FROM matches m
            JOIN participants p ON p.id = m.receiver_id
            JOIN events e ON e.id = m.event_id
            WHERE p.user_id = ?
              AND (m.gift_review IS NOT NULL AND m.gift_review != ''
                   OR m.gift_rating IS NOT NULL
                   OR m.gift_photo_url IS NOT NULL AND m.gift_photo_url != '')
            ORDER BY m.received_at DESC
            LIMIT 100
            """,
            (user["userId"],),
        )
        return ok({
            "profile": profile,
            "createdEvents": created_events,
            "joinedEvents": joined_events,
            "giftPosts": gift_posts,
        })


@api.route("/admin/settings")
@admin_required
def admin_settings(_user):
    with DB() as db:
        return ok(settings_payload(db))


@api.route("/admin/settings", methods=["PUT"])
@admin_required
def update_admin_settings(_user):
    data = body()
    with DB() as db:
        for key, definition in SETTING_DEFINITIONS.items():
            if key not in data:
                continue
            value = str(data.get(key) or "").strip()
            if definition["type"] == "boolean":
                value = "true" if value.lower() in {"true", "1", "yes", "on"} else "false"
            if definition["type"] == "secret" and (value == "********" or value == ""):
                continue
            if key == "site_name" and len(value) > 80:
                return fail("Site name is too long")
            save_setting(db, key, value)
        return ok(settings_payload(db), "Settings saved")
