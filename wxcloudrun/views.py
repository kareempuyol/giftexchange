import os
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from hashlib import sha256

from flask import Blueprint, render_template, request, send_from_directory

from wxcloudrun.auth import check_password, hash_password, sign_token, verify_token
from wxcloudrun.database import DB
from wxcloudrun.response import fail, ok


api = Blueprint("api", __name__, url_prefix="/api")
site = Blueprint("site", __name__)

SETTING_DEFINITIONS = {
    "site_name": {"label": "Site name", "default": "Gift Exchange", "type": "text"},
    "registration_enabled": {"label": "Allow registration", "default": "true", "type": "boolean"},
    "shipment_tracking_enabled": {"label": "Enable shipment tracking", "default": "false", "type": "boolean"},
    "tracking_provider": {"label": "Tracking provider", "default": "kdniao", "type": "select"},
    "kdniao_ebusiness_id": {"label": "KDNiao business ID", "default": "", "type": "secret"},
    "kdniao_app_key": {"label": "KDNiao app key", "default": "", "type": "secret"},
    "cors_origin": {"label": "CORS origin", "default": "*", "type": "text"},
    "password_reset_enabled": {"label": "Enable password reset", "default": "false", "type": "boolean"},
    "app_base_url": {"label": "App base URL", "default": "", "type": "text"},
    "smtp_host": {"label": "SMTP host", "default": "", "type": "text"},
    "smtp_port": {"label": "SMTP port", "default": "587", "type": "text"},
    "smtp_use_tls": {"label": "SMTP TLS", "default": "true", "type": "boolean"},
    "smtp_username": {"label": "SMTP username", "default": "", "type": "text"},
    "smtp_password": {"label": "SMTP password", "default": "", "type": "secret"},
    "smtp_sender": {"label": "Sender email", "default": "", "type": "text"},
}


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
        "isAdmin": is_user_admin(row),
        "phone": row.get("phone") or "",
        "address": row.get("address") or "",
        "receiverName": row.get("receiver_name") or "",
        "giftPreference": row.get("gift_preference") or "",
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
        "matchVisibility": row.get("match_visibility") or "private",
        "ownerId": row["creator_id"],
        "ownerName": row.get("owner_username") or "",
        "participantCount": row.get("participant_count") or 0,
        "coverImage": row.get("cover_image") or "",
        "isPublic": bool(row.get("is_public")) if row.get("is_public") is not None else True,
        "maxParticipants": row.get("max_participants"),
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
            return fail("Please sign in first", 401, -2)
        return fn(user, *args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(user, *args, **kwargs):
        with DB() as db:
            row = current_user_row(db, user["userId"])
            if not is_user_admin(row):
                return fail("Admin permission required", 403)
        return fn(user, *args, **kwargs)

    return login_required(wrapper)


def _split_env(name):
    return {item.strip().lower() for item in os.getenv(name, "").split(",") if item.strip()}


def is_user_admin(row):
    if bool(row.get("is_admin")):
        return True
    usernames = _split_env("ADMIN_USERNAMES")
    emails = _split_env("ADMIN_EMAILS")
    return row.get("username", "").lower() in usernames or row.get("email", "").lower() in emails


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
        raise ValueError("Event not found")
    return row


def create_notification(db, user_id, event_id, match_id, type_name, title, message):
    db.execute(
        """
        INSERT INTO notifications (user_id, event_id, match_id, type, title, message)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, event_id, match_id, type_name, title, message),
    )


def current_user_row(db, user_id):
    row = db.get("SELECT * FROM users WHERE id = ?", (user_id,))
    if not row:
        raise ValueError("User not found")
    return row


def participant_rows(db, event_id):
    return db.all(
        """
        SELECT p.id, p.user_id, p.nickname, p.receiver_name, p.phone, p.address,
               p.preference_likes, p.preference_dislikes, p.preference_notes,
               p.created_at, u.username, u.display_name, u.avatar_url
        FROM participants p JOIN users u ON u.id = p.user_id
        WHERE p.event_id = ?
        ORDER BY p.created_at ASC
        """,
        (event_id,),
    )


def participant_payload(user_row, data=None):
    data = data or {}
    return {
        "receiver_name": str(data.get("receiverName") or data.get("receiver_name") or user_row.get("receiver_name") or user_row.get("display_name") or user_row["username"]).strip(),
        "phone": str(data.get("phone") or user_row.get("phone") or "").strip(),
        "address": str(data.get("address") or user_row.get("address") or "").strip(),
        "preference_likes": str(data.get("preferenceLikes") or data.get("preference_likes") or user_row.get("gift_preference") or "").strip(),
        "preference_dislikes": str(data.get("preferenceDislikes") or data.get("preference_dislikes") or "").strip(),
        "preference_notes": str(data.get("preferenceNotes") or data.get("preference_notes") or "").strip(),
    }


def validate_participant_payload(payload):
    if len(payload["receiver_name"]) > 120:
        return "Receiver name is too long"
    if len(payload["phone"]) > 50:
        return "Phone is too long"
    if len(payload["address"]) > 500:
        return "Address is too long"
    if len(payload["preference_likes"]) > 500:
        return "Preference is too long"
    if len(payload["preference_dislikes"]) > 500:
        return "Dislikes is too long"
    if len(payload["preference_notes"]) > 500:
        return "Preference notes is too long"
    return None


def add_participant(db, event_id, user_id, data=None):
    user_row = current_user_row(db, user_id)
    nickname = user_row.get("display_name") or user_row["username"]
    payload = participant_payload(user_row, data)
    error = validate_participant_payload(payload)
    if error:
        raise ValueError(error)
    existing = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event_id, user_id))
    if existing:
        return existing["id"]
    cur = db.execute(
        """
        INSERT INTO participants (
            event_id, user_id, nickname, receiver_name, phone, address,
            preference_likes, preference_dislikes, preference_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            user_id,
            nickname,
            payload["receiver_name"],
            payload["phone"],
            payload["address"],
            payload["preference_likes"],
            payload["preference_dislikes"],
            payload["preference_notes"],
        ),
    )
    db.execute(
        "UPDATE events SET participant_count = participant_count + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (event_id,),
    )
    return cur.lastrowid


def api_shipment(row):
    return {
        "status": row.get("shipment_status") or "pending",
        "carrier": row.get("carrier") or "",
        "trackingNumber": row.get("tracking_number") or "",
        "shippedAt": str(row.get("shipped_at") or ""),
        "trackingUpdatedAt": str(row.get("tracking_updated_at") or ""),
        "trackingSummary": row.get("tracking_summary") or "",
    }


def api_gift_post(row):
    return {
        "receivedAt": str(row.get("received_at") or ""),
        "rating": row.get("gift_rating"),
        "review": row.get("gift_review") or "",
        "photoUrl": row.get("gift_photo_url") or "",
    }


def api_notification(row):
    return {
        "id": row["id"],
        "eventCode": row.get("event_code") or "",
        "matchId": row.get("match_id"),
        "type": row.get("type") or "",
        "title": row.get("title") or "",
        "message": row.get("message") or "",
        "read": bool(row.get("read_at")),
        "createdAt": str(row.get("created_at") or ""),
    }


def api_contact(row):
    return {
        "receiverName": row.get("receiver_name") or "",
        "phone": row.get("phone") or "",
        "address": row.get("address") or "",
    }


def api_preference(row):
    return {
        "likes": row.get("preference_likes") or "",
        "dislikes": row.get("preference_dislikes") or "",
        "notes": row.get("preference_notes") or "",
    }


def setting_value(db, key):
    definition = SETTING_DEFINITIONS[key]
    row = db.get("SELECT value FROM app_settings WHERE key_name = ?", (key,))
    return row["value"] if row and row.get("value") is not None else os.getenv(key.upper(), definition["default"])


def settings_payload(db, include_secrets=False):
    values = {}
    for key, definition in SETTING_DEFINITIONS.items():
        value = setting_value(db, key)
        if definition["type"] == "secret" and value and not include_secrets:
            value = "********"
        values[key] = {"value": value, **definition}
    return values


def save_setting(db, key, value):
    cur = db.execute("UPDATE app_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key_name = ?", (value, key))
    if cur.rowcount == 0:
        db.execute("INSERT INTO app_settings (key_name, value) VALUES (?, ?)", (key, value))


def token_hash(token):
    return sha256(token.encode("utf-8")).hexdigest()


def absolute_app_url(db):
    configured = setting_value(db, "app_base_url").strip().rstrip("/")
    if configured:
        return configured
    return request.host_url.rstrip("/")


def send_reset_email(db, email, reset_url):
    host = setting_value(db, "smtp_host").strip()
    sender = setting_value(db, "smtp_sender").strip() or setting_value(db, "smtp_username").strip()
    if not host or not sender:
        raise RuntimeError("Email service is not configured")

    port = int(setting_value(db, "smtp_port") or 587)
    username = setting_value(db, "smtp_username").strip()
    password = setting_value(db, "smtp_password")
    use_tls = setting_value(db, "smtp_use_tls").lower() == "true"
    site_name = setting_value(db, "site_name")

    message = EmailMessage()
    message["Subject"] = f"{site_name} password reset"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "Use the link below to reset your password. The link expires in 30 minutes.\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )

    with smtplib.SMTP(host, port, timeout=12) as smtp:
        if use_tls:
            smtp.starttls()
        if username or password:
            smtp.login(username, password)
        smtp.send_message(message)


def parse_datetime(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@api.route("/health")
def health():
    return ok({"status": "ok", "timestamp": now_iso()})


@site.route("/api-health")
def platform_health():
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

    with DB() as db:
        row = db.get("SELECT * FROM users WHERE username = ?", (username,))
        if not row or not check_password(password, row["password"]):
            return fail("Invalid username or password", 401)
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


@api.route("/events", methods=["POST"])
@login_required
def create_event(user):
    data = body()
    title = str(data.get("title") or "").strip()
    note = str(data.get("note") or "").strip()
    draw_date = str(data.get("drawDate") or "")
    budget = int(data.get("budget") or 0)
    match_visibility = str(data.get("matchVisibility") or data.get("match_visibility") or "private").strip()
    is_public = bool(data.get("isPublic")) if data.get("isPublic") is not None else True
    max_participants = data.get("maxParticipants")
    cover_image = str(data.get("coverImage") or "").strip()

    if not title:
        return fail("Event title is required")
    if len(title) > 100:
        return fail("Event title is too long")
    if budget < 0:
        return fail("Budget cannot be negative")
    if len(note) > 500:
        return fail("Note is too long")
    if match_visibility not in {"private", "public"}:
        return fail("Invalid match visibility")
    if max_participants is not None:
        try:
            max_participants = int(max_participants)
        except (ValueError, TypeError):
            return fail("Invalid max participants")
        if max_participants < 2:
            return fail("Max participants must be at least 2")
        if max_participants > 999:
            return fail("Max participants is too large")
    if len(cover_image) > 350000:
        return fail("Cover image is too large")

    with DB() as db:
        code = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO events (code, name, description, budget_min, creator_id, sign_up_deadline,
                                match_visibility, is_public, max_participants, cover_image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (code, title, note, budget, user["userId"], draw_date, match_visibility,
             1 if is_public else 0, max_participants, cover_image),
        )
        return ok(api_event(fetch_event(db, code)), "Event created", 201)


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


@api.route("/events/public")
@login_required
def public_events(_user):
    search = str(request.args.get("search", "")).strip() or None
    sort = str(request.args.get("sort", "newest")).strip()
    filter_type = str(request.args.get("filter", "all")).strip()
    try:
        page = max(1, int(request.args.get("page", "1")))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(1, min(50, int(request.args.get("per_page", "20"))))
    except (ValueError, TypeError):
        per_page = 20

    if sort not in ("newest", "hottest"):
        sort = "newest"
    if filter_type not in ("all", "not_full"):
        filter_type = "all"

    with DB() as db:
        conditions = ["e.status = 'open'", "e.is_public = 1"]
        params = []

        if search:
            conditions.append("(e.name LIKE ? OR u.username LIKE ? OR e.code = ?)")
            params.extend([f"%{search}%", f"%{search}%", search])

        if filter_type == "not_full":
            conditions.append("(e.max_participants IS NULL OR e.participant_count < e.max_participants)")

        where = " AND ".join(conditions)
        order = "ORDER BY e.participant_count DESC, e.created_at DESC" if sort == "hottest" else "ORDER BY e.created_at DESC"

        events = db.all(
            f"""
            SELECT e.*, u.username AS owner_username
            FROM events e JOIN users u ON u.id = e.creator_id
            WHERE {where}
            {order}
            LIMIT ? OFFSET ?
            """,
            params + [per_page, (page - 1) * per_page],
        )

        total_row = db.get(
            f"""
            SELECT COUNT(*) AS count
            FROM events e JOIN users u ON u.id = e.creator_id
            WHERE {where}
            """,
            params,
        )
        total = total_row["count"] if total_row else 0

        return ok({
            "events": [api_event(row) for row in events],
            "total": total,
            "page": page,
            "perPage": per_page,
        })


@api.route("/events/<code>")
@login_required
def event_detail(_user, code):
    try:
        with DB() as db:
            return ok(api_event(fetch_event(db, code)))
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>", methods=["PATCH"])
@login_required
def edit_event(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("Only the event creator can edit", 403)

            data = body()
            fields = {}
            params = []

            if "title" in data:
                title = str(data["title"] or "").strip()
                if not title:
                    return fail("Event title cannot be empty")
                if len(title) > 100:
                    return fail("Event title is too long")
                fields["name"] = title
                params.append(title)

            if "coverImage" in data:
                cover = str(data["coverImage"] or "").strip()
                if len(cover) > 350000:
                    return fail("Cover image is too large")
                fields["cover_image"] = cover
                params.append(cover)

            if "drawDate" in data:
                draw = str(data["drawDate"] or "")
                if draw:
                    try:
                        dt = parse_datetime(draw)
                        if dt <= datetime.now(timezone.utc):
                            return fail("Deadline must be in the future")
                    except Exception:
                        return fail("Invalid date format")
                fields["sign_up_deadline"] = draw
                params.append(draw)

            if "maxParticipants" in data:
                max_p = data["maxParticipants"]
                if max_p is not None:
                    try:
                        max_p = int(max_p)
                    except (ValueError, TypeError):
                        return fail("Invalid max participants")
                    if max_p < 2:
                        return fail("Max participants must be at least 2")
                    if max_p > 999:
                        return fail("Max participants is too large")
                    current_count = int(event.get("participant_count") or 0)
                    if max_p < current_count:
                        return fail(f"Cannot set max below current participant count ({current_count})")
                fields["max_participants"] = max_p
                params.append(max_p)

            if "isPublic" in data:
                is_public = bool(data["isPublic"])
                fields["is_public"] = 1 if is_public else 0
                params.append(1 if is_public else 0)

            if not fields:
                return fail("No fields to update")

            assignments = ", ".join(f"{col} = ?" for col in fields)
            params.append(code)
            db.execute(
                f"UPDATE events SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE code = ?",
                params,
            )
            return ok(api_event(fetch_event(db, code)), "Event updated")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>", methods=["DELETE"])
@login_required
def delete_event(user, code):
    with DB() as db:
        event = db.get("SELECT id FROM events WHERE code = ? AND creator_id = ?", (code, user["userId"]))
        if not event:
            return fail("Event not found or no permission", 403)
        db.execute("DELETE FROM events WHERE id = ?", (event["id"],))
        return ok(None, "Event deleted")


@api.route("/events/<code>/join", methods=["POST"])
@login_required
def join_event(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["status"] != "open":
                return fail("Event is closed")
            max_ppl = event.get("max_participants")
            if max_ppl is not None and int(event.get("participant_count") or 0) >= int(max_ppl):
                return fail("Event is full")
            if db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"])):
                return fail("You have already joined this event")
            data = body()
            participant_id = add_participant(db, event["id"], user["userId"], data)
            if data.get("updateProfile"):
                payload = participant_payload(current_user_row(db, user["userId"]), data)
                db.execute(
                    """
                    UPDATE users
                    SET receiver_name = ?, phone = ?, address = ?, gift_preference = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        payload["receiver_name"],
                        payload["phone"],
                        payload["address"],
                        payload["preference_likes"],
                        user["userId"],
                    ),
                )
            user_row = current_user_row(db, user["userId"])
            return ok(
                {"id": participant_id, "eventCode": code, "userName": user_row.get("display_name") or user_row["username"]},
                "Joined event",
                201,
            )
    except ValueError as exc:
        message = str(exc)
        return fail(message, 404 if message == "Event not found" else 400)


@api.route("/events/<code>/leave", methods=["DELETE"])
@login_required
def leave_event(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] == user["userId"]:
                return fail("Creator cannot leave; delete the event instead")
            if event["status"] != "open":
                return fail("Event has already been drawn")
            cur = db.execute("DELETE FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if cur.rowcount == 0:
                return fail("You have not joined this event")
            db.execute(
                "UPDATE events SET participant_count = participant_count - 1, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND participant_count > 0",
                (event["id"],),
            )
            return ok(None, "Left event")
    except ValueError as exc:
        return fail(str(exc), 404)


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
                    "avatarUrl": row.get("avatar_url"),
                    "nickname": row["nickname"],
                    "contactComplete": bool(row.get("receiver_name") and row.get("phone") and row.get("address")),
                    "preferenceComplete": bool(row.get("preference_likes") or row.get("preference_dislikes") or row.get("preference_notes")),
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
                return fail("Only the event creator can draw", 403)
            if event["status"] == "drawn":
                return fail("This event has already been drawn")

            rows = participant_rows(db, event["id"])
            if len(rows) < 2:
                return fail("At least 2 people are required to draw")
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
                matches.append(
                    {
                        "id": cur.lastrowid,
                        "giverId": giver["id"],
                        "giverName": giver.get("display_name") or giver["nickname"] or giver["username"],
                        "receiverId": receiver["id"],
                        "receiverName": receiver.get("display_name") or receiver["nickname"] or receiver["username"],
                    }
                )
            db.execute("UPDATE events SET status = 'drawn', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event["id"],))
            return ok(matches, "Draw complete")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/matches")
@login_required
def event_matches(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["status"] != "drawn":
                return ok([])
            participant = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            is_creator = event["creator_id"] == user["userId"]
            is_public = (event.get("match_visibility") or "private") == "public"
            if not is_creator and (not is_public or not participant):
                return fail("Match list is private", 403)

            rows = db.all(
                """
                SELECT m.id,
                       gp.user_id AS giver_user_id, gu.username AS giver_username, gu.display_name AS giver_display_name,
                       rp.user_id AS receiver_user_id, ru.username AS receiver_username, ru.display_name AS receiver_display_name
                FROM matches m
                JOIN participants gp ON gp.id = m.giver_id
                JOIN users gu ON gu.id = gp.user_id
                JOIN participants rp ON rp.id = m.receiver_id
                JOIN users ru ON ru.id = rp.user_id
                WHERE m.event_id = ?
                ORDER BY gp.created_at ASC
                """,
                (event["id"],),
            )
            return ok(
                [
                    {
                        "id": row["id"],
                        "giverId": row["giver_user_id"],
                        "giverName": row.get("giver_display_name") or row["giver_username"],
                        "receiverId": row["receiver_user_id"],
                        "receiverName": row.get("receiver_display_name") or row["receiver_username"],
                    }
                    for row in rows
                ]
            )
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/dashboard")
@login_required
def event_dashboard(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("Only the event creator can view dashboard", 403)
            participants_data = participant_rows(db, event["id"])
            rows = db.all(
                """
                SELECT p.id AS participant_id, m.id AS match_id, m.shipment_status, m.tracking_number,
                       m.received_at, m.gift_rating, m.gift_review, m.gift_photo_url
                FROM participants p
                LEFT JOIN matches m ON m.receiver_id = p.id AND m.event_id = ?
                WHERE p.event_id = ?
                """,
                (event["id"], event["id"]),
            )
            match_by_participant = {row["participant_id"]: row for row in rows}
            data = []
            for row in participants_data:
                match_row = match_by_participant.get(row["id"]) or {}
                data.append(
                    {
                        "participantId": row["id"],
                        "userId": row["user_id"],
                        "displayName": row.get("display_name") or row["nickname"] or row["username"],
                        "avatarUrl": row.get("avatar_url"),
                        "contactComplete": bool(row.get("receiver_name") and row.get("phone") and row.get("address")),
                        "preferenceComplete": bool(row.get("preference_likes") or row.get("preference_dislikes") or row.get("preference_notes")),
                        "hasMatch": bool(match_row.get("match_id")),
                        "shipmentStatus": match_row.get("shipment_status") or "pending",
                        "hasTracking": bool(match_row.get("tracking_number")),
                        "received": bool(match_row.get("received_at")),
                        "postedGift": bool(match_row.get("gift_rating") or match_row.get("gift_review") or match_row.get("gift_photo_url")),
                    }
                )
            return ok({"participants": data, "count": len(data)})
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
                SELECT m.id, m.note, m.shipment_status, m.carrier, m.tracking_number,
                       m.shipped_at, m.tracking_updated_at, m.tracking_summary,
                       m.received_at, m.gift_rating, m.gift_review, m.gift_photo_url,
                       p.receiver_name, p.phone, p.address,
                       p.preference_likes, p.preference_dislikes, p.preference_notes,
                       p.user_id AS receiver_user_id, u.username, u.display_name
                FROM matches m
                JOIN participants p ON p.id = m.receiver_id
                JOIN users u ON u.id = p.user_id
                WHERE m.event_id = ? AND m.giver_id = ?
                """,
                (event["id"], me["id"]),
            )
            if not row:
                return ok(None)
            return ok(
                {
                    "matchId": row["id"],
                    "receiverId": row["receiver_user_id"],
                    "receiverName": row["username"],
                    "receiverDisplayName": row.get("display_name") or row["username"],
                    "note": row.get("note") or "",
                    "shipment": api_shipment(row),
                    "giftPost": api_gift_post(row),
                    "contact": api_contact(row),
                    "preference": api_preference(row),
                }
            )
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/received-gift")
@login_required
def received_gift(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return ok(None)
            row = db.get(
                """
                SELECT m.id, m.note, m.shipment_status, m.carrier, m.tracking_number,
                       m.shipped_at, m.tracking_updated_at, m.tracking_summary,
                       m.received_at, m.gift_rating, m.gift_review, m.gift_photo_url,
                       p.user_id AS giver_user_id, u.username, u.display_name
                FROM matches m
                JOIN participants p ON p.id = m.giver_id
                JOIN users u ON u.id = p.user_id
                WHERE m.event_id = ? AND m.receiver_id = ?
                """,
                (event["id"], me["id"]),
            )
            if not row:
                return ok(None)
            return ok(
                {
                    "matchId": row["id"],
                    "giverId": row["giver_user_id"],
                    "giverName": row["username"],
                    "giverDisplayName": row.get("display_name") or row["username"],
                    "note": row.get("note") or "",
                    "shipment": api_shipment(row),
                    "giftPost": api_gift_post(row),
                }
            )
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/received-gift", methods=["PUT"])
@login_required
def update_received_gift(user, code):
    data = body()
    match_id = data.get("matchId")
    rating = data.get("rating")
    review = str(data.get("review") or "").strip()
    photo_url = str(data.get("photoUrl") or data.get("photo_url") or "").strip()

    if not match_id:
        return fail("matchId is required")
    try:
        rating_value = int(rating)
    except Exception:
        return fail("Rating is required")
    if rating_value < 1 or rating_value > 5:
        return fail("Rating must be 1-5")
    if len(review) > 500:
        return fail("Review is too long")
    if len(photo_url) > 350000:
        return fail("Photo is too large")

    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return fail("You are not a participant of this event", 403)
            cur = db.execute(
                """
                UPDATE matches
                SET received_at = COALESCE(received_at, CURRENT_TIMESTAMP),
                    gift_rating = ?, gift_review = ?, gift_photo_url = ?
                WHERE id = ? AND event_id = ? AND receiver_id = ?
                """,
                (rating_value, review, photo_url, match_id, event["id"], me["id"]),
            )
            if cur.rowcount == 0:
                return fail("Match not found")
            row = db.get(
                """
                SELECT m.*, giver.user_id AS giver_user_id, receiver.user_id AS receiver_user_id,
                       ru.display_name AS receiver_display_name, ru.username AS receiver_username
                FROM matches m
                JOIN participants giver ON giver.id = m.giver_id
                JOIN participants receiver ON receiver.id = m.receiver_id
                JOIN users ru ON ru.id = receiver.user_id
                WHERE m.id = ?
                """,
                (match_id,),
            )
            create_notification(
                db,
                row["giver_user_id"],
                event["id"],
                row["id"],
                "gift_posted",
                f"{row.get('receiver_display_name') or row.get('receiver_username')} 已晒礼物",
                "TA 已收到你的礼物，并完成了晒图评价。",
            )
            return ok(api_gift_post(row), "Gift post saved")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/gift-wall")
@login_required
def gift_wall(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            participant = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            is_creator = event["creator_id"] == user["userId"]
            if not is_creator and not participant:
                return fail("No permission", 403)
            counts = db.get(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN received_at IS NOT NULL AND gift_photo_url IS NOT NULL AND gift_photo_url <> '' THEN 1 ELSE 0 END) AS posted
                FROM matches
                WHERE event_id = ?
                """,
                (event["id"],),
            )
            total = int(counts.get("total") or 0)
            posted = int(counts.get("posted") or 0)
            unlocked = total > 0 and total == posted
            rows = []
            if unlocked:
                rows = db.all(
                    """
                    SELECT m.id, m.received_at, m.gift_rating, m.gift_review, m.gift_photo_url,
                           gu.username AS giver_username, gu.display_name AS giver_display_name,
                           ru.username AS receiver_username, ru.display_name AS receiver_display_name
                    FROM matches m
                    JOIN participants gp ON gp.id = m.giver_id
                    JOIN participants rp ON rp.id = m.receiver_id
                    JOIN users gu ON gu.id = gp.user_id
                    JOIN users ru ON ru.id = rp.user_id
                    WHERE m.event_id = ?
                    ORDER BY m.received_at DESC
                    """,
                    (event["id"],),
                )
            return ok(
                {
                    "unlocked": unlocked,
                    "posted": posted,
                    "total": total,
                    "items": [
                        {
                            "matchId": row["id"],
                            "giverName": row.get("giver_display_name") or row["giver_username"],
                            "receiverName": row.get("receiver_display_name") or row["receiver_username"],
                            "giftPost": api_gift_post(row),
                        }
                        for row in rows
                    ],
                }
            )
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/note", methods=["PUT"])
@login_required
def update_note(user, code):
    data = body()
    match_id = data.get("matchId")
    note = str(data.get("note") or "")
    if not match_id:
        return fail("matchId is required")
    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return fail("You are not a participant of this event", 403)
            cur = db.execute("UPDATE matches SET note = ? WHERE id = ? AND giver_id = ?", (note, match_id, me["id"]))
            if cur.rowcount == 0:
                return fail("Match not found")
            return ok(None, "Note saved")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/shipment", methods=["PUT"])
@login_required
def update_shipment(user, code):
    data = body()
    match_id = data.get("matchId")
    carrier = str(data.get("carrier") or "").strip()
    tracking_number = str(data.get("trackingNumber") or data.get("tracking_number") or "").strip()
    status = str(data.get("status") or "").strip() or ("shipped" if tracking_number else "pending")

    if status not in {"pending", "shipped", "delivered"}:
        return fail("Invalid shipment status")
    if not match_id:
        return fail("matchId is required")
    if status != "pending" and not tracking_number:
        return fail("Tracking number is required")
    if len(carrier) > 80:
        return fail("Carrier is too long")
    if len(tracking_number) > 120:
        return fail("Tracking number is too long")

    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return fail("You are not a participant of this event", 403)
            old_row = db.get(
                """
                SELECT carrier, tracking_number
                FROM matches
                WHERE id = ? AND event_id = ? AND giver_id = ?
                """,
                (match_id, event["id"], me["id"]),
            )
            if not old_row:
                return fail("Match not found")
            shipment_changed = (old_row.get("carrier") or "") != carrier or (old_row.get("tracking_number") or "") != tracking_number

            cur = db.execute(
                """
                UPDATE matches
                SET shipment_status = ?, carrier = ?, tracking_number = ?,
                    shipped_at = CASE
                        WHEN ? = 'pending' THEN NULL
                        ELSE COALESCE(shipped_at, CURRENT_TIMESTAMP)
                    END,
                    tracking_updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND event_id = ? AND giver_id = ?
                """,
                (status, carrier, tracking_number, status, match_id, event["id"], me["id"]),
            )
            if cur.rowcount == 0:
                return fail("Match not found")

            row = db.get(
                """
                SELECT m.*, receiver.user_id AS receiver_user_id, gu.display_name AS giver_display_name, gu.username AS giver_username
                FROM matches m
                JOIN participants giver ON giver.id = m.giver_id
                JOIN participants receiver ON receiver.id = m.receiver_id
                JOIN users gu ON gu.id = giver.user_id
                WHERE m.id = ?
                """,
                (match_id,),
            )
            if status != "pending" and shipment_changed:
                create_notification(
                    db,
                    row["receiver_user_id"],
                    event["id"],
                    row["id"],
                    "shipment_sent",
                    "你的礼物已发货",
                    f"{row.get('giver_display_name') or row.get('giver_username')} 已填写快递信息，请留意收件。",
                )
            return ok(api_shipment(row), "Shipment saved")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/notifications")
@login_required
def notifications(user):
    with DB() as db:
        rows = db.all(
            """
            SELECT n.*, e.code AS event_code
            FROM notifications n
            LEFT JOIN events e ON e.id = n.event_id
            WHERE n.user_id = ?
            ORDER BY n.created_at DESC
            LIMIT 50
            """,
            (user["userId"],),
        )
        unread = db.get("SELECT COUNT(*) AS count FROM notifications WHERE user_id = ? AND read_at IS NULL", (user["userId"],))["count"]
        return ok({"items": [api_notification(row) for row in rows], "unread": unread})


@api.route("/notifications/read", methods=["POST"])
@login_required
def read_notifications(user):
    data = body()
    ids = data.get("ids") or []
    with DB() as db:
        if ids:
            for item_id in ids:
                db.execute(
                    "UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP) WHERE id = ? AND user_id = ?",
                    (item_id, user["userId"]),
                )
        else:
            db.execute(
                "UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP) WHERE user_id = ?",
                (user["userId"],),
            )
        return ok(None, "Notifications marked read")
