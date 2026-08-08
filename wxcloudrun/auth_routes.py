"""认证与账户路由（auth/*、profile、admin/settings、登录限速）。"""
import secrets
from datetime import datetime, timedelta, timezone

from flask import request

from wxcloudrun.auth import check_password, hash_password, sign_token
from wxcloudrun.database import DB
from wxcloudrun.helpers import (
    SETTING_DEFINITIONS,
    _split_env,
    absolute_app_url,
    admin_required,
    api,
    body,
    clear_login_attempts,
    current_user_row,
    fail,
    login_required,
    ok,
    parse_datetime,
    public_user,
    rate_limit_login,
    record_failed_login,
    save_setting,
    send_reset_email,
    setting_value,
    settings_payload,
    token_hash,
)


@api.route("/auth/register", methods=["POST"])
def register():
    data = body()
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")

    if not username or not email or not password:
        return fail("Username, email and password are required")
    if len(username) < 2 or len(username) > 50:
        return fail("Username length must be 2-50 characters")
    if "@" not in email or "." not in email or len(email) > 254:
        return fail("Invalid email")
    if len(password) < 6 or len(password) > 128:
        return fail("Password length must be 6-128 characters")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return fail("Password must contain letters and numbers")

    with DB() as db:
        user_count = db.get("SELECT COUNT(*) AS count FROM users")["count"]
        registration_enabled = setting_value(db, "registration_enabled").lower() == "true"
        is_first_user = int(user_count) == 0
        if not registration_enabled and not is_first_user:
            return fail("Registration is closed", 403)

        conflicts = []
        if db.get("SELECT id FROM users WHERE username = ?", (username,)):
            conflicts.append("username")
        if db.get("SELECT id FROM users WHERE email = ?", (email,)):
            conflicts.append("email")
        if conflicts:
            return fail(" and ".join(conflicts) + " already exists", 409)

        admin_by_env = username.lower() in _split_env("ADMIN_USERNAMES") or email.lower() in _split_env("ADMIN_EMAILS")
        is_admin = 1 if is_first_user or admin_by_env else 0
        cur = db.execute(
            "INSERT INTO users (username, email, password, display_name, is_admin) VALUES (?, ?, ?, ?, ?)",
            (username, email, hash_password(password), username, is_admin),
        )
        user_id = cur.lastrowid
        row = current_user_row(db, user_id)
        return ok({"token": sign_token(user_id), "user": public_user(row)}, "Registered", 201)


@api.route("/auth/login", methods=["POST"])
def login():
    data = body()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        return fail("Username and password are required")

    # 登录限速：按 IP+用户名 双重限制，防暴力破解
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    check, retry_after = rate_limit_login(client_ip, username)
    if not check:
        return fail(f"登录尝试过于频繁，请 {retry_after} 秒后再试", 429, headers={"Retry-After": str(retry_after)})

    with DB() as db:
        row = db.get("SELECT * FROM users WHERE username = ?", (username,))
        if not row or not check_password(password, row["password"]):
            record_failed_login(client_ip, username)
            return fail("Invalid username or password", 401)
        clear_login_attempts(client_ip, username)
        return ok({"token": sign_token(row["id"]), "user": public_user(row)}, "Signed in")


@api.route("/auth/forgot-password", methods=["POST"])
def forgot_password():
    data = body()
    email = str(data.get("email") or "").strip().lower()
    generic = ok(None, "If the email exists, a reset link will be sent")
    if not email:
        return generic

    with DB() as db:
        if setting_value(db, "password_reset_enabled").lower() != "true":
            return fail("Password reset is not enabled", 403)

        row = db.get("SELECT id, email FROM users WHERE email = ?", (email,))
        if not row:
            return generic

        raw_token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(minutes=30)
        db.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (row["id"], token_hash(raw_token), expires.isoformat()),
        )
        reset_url = f"{absolute_app_url(db)}/reset-password?token={raw_token}"
        try:
            send_reset_email(db, row["email"], reset_url)
        except Exception:
            db.conn.rollback()
            return fail("Email service is unavailable", 503)
        return generic


@api.route("/auth/reset-password", methods=["POST"])
def reset_password():
    data = body()
    raw_token = str(data.get("token") or "").strip()
    password = str(data.get("password") or "")
    if not raw_token or not password:
        return fail("Token and password are required")
    if len(password) < 6 or len(password) > 128:
        return fail("Password length must be 6-128 characters")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return fail("Password must contain letters and numbers")

    with DB() as db:
        row = db.get(
            """
            SELECT id, user_id, expires_at, used_at
            FROM password_reset_tokens
            WHERE token_hash = ?
            """,
            (token_hash(raw_token),),
        )
        if not row or row.get("used_at"):
            return fail("Reset link is invalid or expired", 400)
        expires_at = parse_datetime(row["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            return fail("Reset link is invalid or expired", 400)
        db.execute("UPDATE users SET password = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (hash_password(password), row["user_id"]))
        db.execute("UPDATE password_reset_tokens SET used_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
        return ok(None, "Password updated")


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
        return fail("Display name is too long")
    if len(fields["phone"]) > 50:
        return fail("Phone is too long")
    if len(fields["address"]) > 500:
        return fail("Address is too long")

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
        return fail("Old and new password are required")
    if len(new_password) < 6 or len(new_password) > 128:
        return fail("New password length must be 6-128 characters")
    if not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
        return fail("New password must contain letters and numbers")

    with DB() as db:
        row = db.get("SELECT * FROM users WHERE id = ?", (user["userId"],))
        if not row:
            return fail("User not found", 404)
        if not check_password(old_password, row["password"]):
            return fail("Old password is incorrect", 400)
        db.execute("UPDATE users SET password = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                   (hash_password(new_password), user["userId"]))
        return ok(None, "Password changed")


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
