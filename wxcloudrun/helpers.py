"""共享辅助函数 + Blueprint 定义（Blueprint 拆分重构 R2）。

api / site 两个 Blueprint 在此定义；各路由模块 `from wxcloudrun.helpers import api`
后继续用 @api.route(...) / @site.route(...) 注册路由，__init__.py 只需注册这两个蓝图。
所有跨路由共享的辅助函数（DB 访问、序列化、权限、限速、设置、抽签包装、通知）集中在此。
wxcloudrun/views.py 保留为兼容导入层（import wxcloudrun.views 不报错）。

可观测性：本模块 re-export log_event（wxcloudrun/observability.py），路由模块可直接
`from wxcloudrun.helpers import log_event` 打业务埋点（不改变响应结构/状态码）。
"""
import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Blueprint, request

from wxcloudrun.auth import verify_token
from wxcloudrun.database import DB, integrity_errors
from wxcloudrun.notify import notify
from wxcloudrun.observability import log_event  # 结构化日志：路由模块可直接 from wxcloudrun.helpers import log_event
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
        "shortCode": row.get("short_code") or "",
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
        "excludedPairs": excluded_pairs_list(row.get("excluded_pairs")),
        "archived": bool(row.get("archived")),
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
        # 已注销用户：JWT 仍有效期内也立即失效（账号注销 P0）
        with DB() as db:
            row = db.get("SELECT deactivated FROM users WHERE id = ?", (user["userId"],))
            if not row:
                return fail("请先登录", 401, -2)
            if row.get("deactivated"):
                return fail("账号已注销", 401, -2)
        return fn(user, *args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(user, *args, **kwargs):
        with DB() as db:
            row = current_user_row(db, user["userId"])
            if not is_user_admin(row):
                return fail("需要管理员权限", 403)
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


# 短码生成：6 位大写字母数字，去掉易混淆字符（0/O/1/I）
SHORT_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_short_code(db, length=6):
    """生成唯一 6 位短码（create_event 与 reset-short-code 共用，无副作用）。

    event_created 埋点由调用方（event_routes.create_event）在 INSERT 成功后打，
    避免 reset-short-code 误报活动创建。
    """
    for _ in range(20):
        candidate = "".join(secrets.SystemRandom().choice(SHORT_CODE_ALPHABET) for _ in range(length))
        exists = db.get("SELECT id FROM events WHERE short_code = ?", (candidate,))
        if not exists:
            return candidate
    # 极端冲突情况：退化为 uuid 前缀
    return str(uuid.uuid4())[:8].upper()


def fetch_event(db, code):
    # 兼容查询：先按原始 code（uuid），再按短码
    row = db.get(
        """
        SELECT e.*, u.username AS owner_username
        FROM events e JOIN users u ON u.id = e.creator_id
        WHERE e.code = ?
        """,
        (code,),
    )
    if not row and code and len(code) <= 16:
        # 短码查找：先按 IP 查限速（防陌生人刷无效短码），超限直接 429
        if short_code_rate_limited(request.remote_addr or ""):
            raise ShortCodeRateLimited("Too many invalid short code attempts")
        row = db.get(
            """
            SELECT e.*, u.username AS owner_username
            FROM events e JOIN users u ON u.id = e.creator_id
            WHERE e.short_code = ?
            """,
            (code,),
        )
        if not row:
            record_short_code_failure(request.remote_addr or "")
    if not row:
        raise ValueError("活动不存在或已失效")
    return row


# ===== 短码查找限速（防邀请链接滥用：陌生人刷无效短码）=====
# 内存滑动窗口：同一 IP 1 小时内短码查找失败（查不到活动）达 10 次 → 429。
# 单实例内存 dict 足够；多实例部署时替换为 Redis
# （key: shortcode_fail:<ip>，TTL 1h，INCR + EXPIRE，读写需原子）。过期条目命中时惰性清理。
_SHORT_CODE_WINDOW_SECONDS = 60 * 60
_SHORT_CODE_MAX_FAILURES = 10
_short_code_failures = {}  # ip -> list[timestamp]
_short_code_failures_lock = threading.Lock()


class ShortCodeRateLimited(Exception):
    """短码查找超限（429）：由 api blueprint 的 errorhandler 统一转 429，不逐路由捕获。"""


def _short_code_failures_for(ip):
    """返回窗口内的失败时间戳列表（惰性清理过期条目）。线程安全。"""
    with _short_code_failures_lock:
        now = time.time()
        timestamps = [t for t in _short_code_failures.get(ip, []) if (now - t) <= _SHORT_CODE_WINDOW_SECONDS]
        _short_code_failures[ip] = timestamps
        return timestamps


def short_code_rate_limited(ip):
    """该 IP 短码查找失败是否已达上限（达上限返回 True，调用方应 429）。"""
    return len(_short_code_failures_for(ip)) >= _SHORT_CODE_MAX_FAILURES


def record_short_code_failure(ip):
    """记录一次短码查找失败（查不到活动）。线程安全。"""
    with _short_code_failures_lock:
        now = time.time()
        timestamps = [t for t in _short_code_failures.get(ip, []) if (now - t) <= _SHORT_CODE_WINDOW_SECONDS]
        timestamps.append(now)
        _short_code_failures[ip] = timestamps


@api.errorhandler(ShortCodeRateLimited)
def _short_code_rate_limited_handler(exc):
    """短码查找超限 → 429（保持 ok/fail {code, data, message} 结构）。"""
    return fail(str(exc), 429)


def create_notification(db, user_id, event_id, match_id, type_name, title, message):
    """兼容包装：委托 notify 统一入口（R5）。新代码请直接 from wxcloudrun.notify import notify。"""
    return notify(db, user_id, event_id, match_id, type_name, title, message)


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


def event_visible_to(db, event, user_id):
    """活动详情/参与者列表可见性（P1 修复）：
    公开活动（is_public=1）对所有登录用户可见；私密活动仅创建者与参与者可见。
    与 create_event 的「谁可以看到这个活动」语义一致。"""
    if event.get("is_public"):
        return True
    if event.get("creator_id") == user_id:
        return True
    return bool(
        db.get(
            "SELECT id FROM participants WHERE event_id = ? AND user_id = ?",
            (event["id"], user_id),
        )
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
        "preference_size": str(data.get("preferenceSize") or data.get("preference_size") or "").strip(),
        "preference_color": str(data.get("preferenceColor") or data.get("preference_color") or "").strip(),
        "wish_links": _normalize_wish_links(data),
    }


def _normalize_wish_links(data):
    """心愿链接：接受数组或换行/逗号分隔字符串，最多 3 条，统一存 JSON 数组"""
    raw = data.get("wishLinks") or data.get("wish_links") or ""
    items = []
    if isinstance(raw, list):
        items = [str(x).strip() for x in raw if str(x).strip()]
    elif isinstance(raw, str) and raw.strip():
        items = [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]
    return json.dumps(items[:3], ensure_ascii=False)


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
    if len(payload["preference_size"]) > 50:
        return "Size is too long"
    if len(payload["preference_color"]) > 80:
        return "Color is too long"
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
    # 并发容量原子化（R4 修复）：先条件 UPDATE 占位（容量不足/已抽签时条件不成立、
    # rowcount=0），再 INSERT participant，两步同一事务。SQLite 写锁串行化 / MySQL
    # 行锁保证并发 join 不会同时通过容量校验——第二个 UPDATE 在第一个提交后重读
    # participant_count。status='open' 同时封死 join 与 draw 的竞态窗口：并发抽签把
    # 活动置 drawn 后，占位失败，不再向已抽签活动插入参与者。
    # INSERT 撞唯一约束（并发重复加入同一用户）时抛异常让整个事务回滚，占位 +1 一并撤销。
    cur = db.execute(
        "UPDATE events SET participant_count = participant_count + 1, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = ? AND status = 'open' "
        "AND (max_participants IS NULL OR participant_count < max_participants)",
        (event_id,),
    )
    if cur.rowcount == 0:
        event_row = db.get("SELECT status FROM events WHERE id = ?", (event_id,))
        if event_row and event_row["status"] != "open":
            raise ValueError("活动已截止报名")
        raise ValueError("活动人数已满")
    try:
        cur = db.execute(
            """
            INSERT INTO participants (
                event_id, user_id, nickname, receiver_name, phone, address,
                preference_likes, preference_dislikes, preference_notes,
                preference_size, preference_color, wish_links
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                payload["preference_size"],
                payload["preference_color"],
                payload["wish_links"],
            ),
        )
    except integrity_errors():
        # 并发重复加入：另一请求已插入同 (event_id, user_id)。确认后按幂等处理
        # （抛 ValueError 触发事务回滚，撤销本请求的容量占位；返回既有记录会提交脏 count）。
        if db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event_id, user_id)):
            raise ValueError("你已加入该活动")
        raise
    return cur.lastrowid


def api_shipment(row):
    summary = row.get("tracking_summary") or ""
    return {
        "status": row.get("shipment_status") or "pending",
        "carrier": row.get("carrier") or "",
        "trackingNumber": row.get("tracking_number") or "",
        "shippedAt": str(row.get("shipped_at") or ""),
        "trackingUpdatedAt": str(row.get("tracking_updated_at") or ""),
        "trackingSummary": summary,
        # 前端据此显示「手动刷新物流」按钮：查询失败（含旧版失败文案的历史数据）时可重试，未配置不可
        "trackingRefreshable": summary in (TRACKING_QUERY_FAILED_MSG, TRACKING_LEGACY_FAILED_MSG),
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
    wish_links = []
    raw_links = row.get("wish_links") or ""
    if raw_links:
        try:
            parsed = json.loads(raw_links)
            if isinstance(parsed, list):
                wish_links = [str(x) for x in parsed if str(x)]
        except Exception:
            pass
    return {
        "likes": row.get("preference_likes") or "",
        "dislikes": row.get("preference_dislikes") or "",
        "notes": row.get("preference_notes") or "",
        "size": row.get("preference_size") or "",
        "color": row.get("preference_color") or "",
        "wishLinks": wish_links,
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


def parse_datetime(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ===== KDNiao 物流查询（3s 超时 + 6h 内存缓存 + 静默降级）=====
# 降级文案区分「未接入」与「查询失败」：未配置给用户自助指引；失败给可重试动作（前端显示手动刷新按钮）。
TRACKING_NOT_CONFIGURED_MSG = "暂未接入物流查询，可通过单号自行查询"
TRACKING_QUERY_FAILED_MSG = "物流信息查询失败，请稍后刷新重试"
TRACKING_LEGACY_FAILED_MSG = "物流查询暂不可用，稍后自动更新"  # 旧版失败文案（历史数据无迁移，仅用于可刷新判断）
KDNIAO_NOT_CONFIGURED = "KDNiao not configured"  # query_kdniao_tracking 的 detail 原因（内部契约）
_KDNIAO_API_URL = "https://api.kdniao.com/Ebusiness/EbusinessOrderHandle.aspx"
_KDNIAO_TIMEOUT_SECONDS = 3  # 外网同步调用硬超时：宁可降级也不拖垮请求线程
_KDNIAO_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 小时缓存：同一 (carrier, tracking_number) 不重复外呼
# 注：单实例部署内存缓存足够；多实例部署时替换为 Redis
# （key: kdniao:<carrier>:<tracking_number>，TTL 6h，读写同样需原子操作）。过期条目在命中时惰性清理。
_kdniao_cache = {}  # (carrier, tracking_number) -> (expire_at, (success, summary, detail))
_kdniao_cache_lock = threading.Lock()


def _kdniao_cache_get(key):
    """取缓存；未命中或已过期返回 None。线程安全。"""
    with _kdniao_cache_lock:
        entry = _kdniao_cache.get(key)
        if entry is None:
            return None
        expire_at, result = entry
        if time.time() >= expire_at:
            _kdniao_cache.pop(key, None)
            return None
        return result


def _kdniao_cache_set(key, result):
    """写缓存。线程安全。"""
    with _kdniao_cache_lock:
        _kdniao_cache[key] = (time.time() + _KDNIAO_CACHE_TTL_SECONDS, result)


def _kdniao_http_query(ebusiness_id, app_key, carrier, tracking_number):
    """真正的外网查询（无缓存、无降级）。返回 KDNiao 响应解析后的 dict。"""
    import hashlib
    import base64 as _b64
    import urllib.request as _urlreq
    import urllib.parse as _urlparse

    request_data = {
        "LogisticCode": tracking_number,
        "ShipperCode": carrier or "",
        "OrderCode": "",
    }
    data_json = json.dumps(request_data, separators=(",", ":"), ensure_ascii=False)
    sign = _b64.b64encode(
        hashlib.md5((data_json + app_key).encode("utf-8")).digest()
    ).decode("utf-8")
    payload = {
        "RequestData": _b64.b64encode(data_json.encode("utf-8")).decode("utf-8"),
        "EBusinessID": ebusiness_id,
        "RequestType": "1002",
        "DataSign": sign,
        "DataType": "2",
    }
    form = "&".join(f"{k}={_urlparse.quote(str(v))}" for k, v in payload.items())
    req = _urlreq.Request(
        _KDNIAO_API_URL,
        data=form.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        method="POST",
    )
    with _urlreq.urlopen(req, timeout=_KDNIAO_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _kdniao_result_to_summary(result):
    """KDNiao 响应 -> (success, summary, detail)。summary 是给用户看的简短状态。"""
    if result.get("Success") is not True:
        return False, "", str(result.get("Reason") or "KDNiao query failed")
    traces = result.get("Traces") or []
    state = str(result.get("State") or "0")
    state_map = {
        "0": "无信息",
        "1": "已揽收",
        "2": "在途中",
        "3": "已签收",
        "4": "问题件",
        "5": "转投",
    }
    latest = traces[0] if traces else {}
    summary_parts = [state_map.get(state, "未知状态")]
    if traces:
        summary_parts.append(f"最新：{latest.get('AcceptStation', '')[:80]}")
    return True, " | ".join(summary_parts), traces


def query_kdniao_tracking(db, carrier, tracking_number):
    """查询快递鸟物流轨迹。返回 (success, summary, detail)。

    - success=False 时调用方应静默降级（不阻塞主流程）
    - summary 是给用户看的简短状态
    - 增强：3 秒硬超时 + 6 小时内存缓存（key=(carrier, tracking_number)）+ 异常全兜底
    - 永不抛异常：配置缺失/超时/网络/解析错误一律降级为 (False, ...)
    - 调用方（gift_routes.py）已有 shipment_changed 判断，单号未变不会走到这里；
      同单号 6h 内重复提交则直接命中缓存，不重复外呼
    """
    key = (carrier or "", tracking_number or "")
    if not tracking_number:
        return False, "", "empty tracking number"

    cached = _kdniao_cache_get(key)
    if cached is not None:
        return cached

    try:
        ebusiness_id = setting_value(db, "kdniao_ebusiness_id").strip()
        app_key = setting_value(db, "kdniao_app_key").strip()
        if not ebusiness_id or not app_key:
            return False, "", KDNIAO_NOT_CONFIGURED

        outcome = _kdniao_result_to_summary(
            _kdniao_http_query(ebusiness_id, app_key, key[0], key[1])
        )
        # 只缓存成功结果：失败/降级不缓存，下次变更单号仍会重试
        if outcome[0]:
            _kdniao_cache_set(key, outcome)
        return outcome
    except Exception as exc:
        # 静默降级：超时/网络/解析异常一律不抛到路由层
        return False, "", str(exc)


def tracking_degradation_copy(detail):
    """把 KDNiao 降级原因映射为用户可读文案（存 tracking_summary）。

    - 未配置（detail == KDNIAO_NOT_CONFIGURED）→ 自助查询指引
    - 其余失败（超时/网络/解析/接口报错）→ 可重试提示（前端据此显示手动刷新按钮）
    """
    if detail == KDNIAO_NOT_CONFIGURED:
        return TRACKING_NOT_CONFIGURED_MSG
    return TRACKING_QUERY_FAILED_MSG


# ===== 图片上传（阶段二G：先传后引用，未来兼容 wx.uploadFile） =====

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
# 业务图片字段新格式：存 URL（≤2000）；兼容旧格式：data: 开头的 base64（≤350000）
MAX_IMAGE_REF_URL = 2000
MAX_IMAGE_REF_BASE64 = 350000


def uploads_dir():
    base = os.getenv("UPLOAD_DIR") or str(Path(__file__).resolve().parent.parent / "data" / "uploads")
    Path(base).mkdir(parents=True, exist_ok=True)
    return base


def image_ref_valid(value):
    """图片字段校验：先传后引用。新值应为 /uploads/ 相对 URL；旧 base64（data: 开头）继续兼容。"""
    if value.startswith("data:"):
        return len(value) <= MAX_IMAGE_REF_BASE64
    return len(value) <= MAX_IMAGE_REF_URL


# ===== 客户端真实 IP（防 X-Forwarded-For 伪造绕过限速，P1 修复）=====
# 仅当直连来源 IP 在 TRUSTED_PROXIES 白名单（逗号分隔环境变量）内时，才信任
# X-Forwarded-For 首段；否则一律用 request.remote_addr（客户端无法伪造）。
# 默认（白名单为空）：伪造 X-Forwarded-For 无效 → 登录/找回密码限速的 IP 半区不可绕过。
def client_ip():
    """取客户端真实 IP：登录/找回密码限速共用。"""
    remote = request.remote_addr or "unknown"
    trusted = {ip.strip() for ip in os.getenv("TRUSTED_PROXIES", "").split(",") if ip.strip()}
    if remote in trusted:
        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if xff:
            return xff
    return remote


# ===== 登录限速（防暴力破解）=====
# 内存滑动窗口：每个 IP 每 15 分钟最多 20 次失败；每个用户名每 15 分钟最多 10 次失败
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_IP = 20
_LOGIN_MAX_USER = 10
_login_attempts = {}  # key -> list[timestamp]


def _login_key_cleanup():
    now = time.time()
    expired = [k for k, v in _login_attempts.items() if v and (now - v[-1]) > _LOGIN_WINDOW_SECONDS]
    for k in expired:
        del _login_attempts[k]


def _login_failures(key):
    _login_key_cleanup()
    now = time.time()
    timestamps = [t for t in _login_attempts.get(key, []) if (now - t) <= _LOGIN_WINDOW_SECONDS]
    _login_attempts[key] = timestamps
    return timestamps


def rate_limit_login(client_ip, username):
    """检查是否超过限速。返回 (allowed, retry_after_seconds)"""
    ip_failures = _login_failures(f"ip:{client_ip}")
    if len(ip_failures) >= _LOGIN_MAX_IP:
        retry_after = max(1, int(_LOGIN_WINDOW_SECONDS - (time.time() - ip_failures[0])))
        return False, retry_after
    user_failures = _login_failures(f"user:{username.lower()}")
    if len(user_failures) >= _LOGIN_MAX_USER:
        retry_after = max(1, int(_LOGIN_WINDOW_SECONDS - (time.time() - user_failures[0])))
        return False, retry_after
    return True, 0


def record_failed_login(client_ip, username):
    now = time.time()
    _login_attempts.setdefault(f"ip:{client_ip}", []).append(now)
    _login_attempts.setdefault(f"user:{username.lower()}", []).append(now)
    # 可观测性埋点：login_failed（唯一调用点 = auth_routes.login 的密码错误分支）
    log_event("login_failed", username=username, client_ip=client_ip)


def clear_login_attempts(client_ip, username):
    _login_attempts.pop(f"ip:{client_ip}", None)
    _login_attempts.pop(f"user:{username.lower()}", None)
    # 可观测性埋点：login_success（唯一调用点 = auth_routes.login 的登录成功分支）
    log_event("login_success", username=username, client_ip=client_ip)


def excluded_pairs_list(raw):
    """解析互避对 JSON 为列表形式（用于 API 输出）：[[a,b], ...]"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [[int(p[0]), int(p[1])] for p in data if isinstance(p, list) and len(p) == 2]
    except Exception:
        pass
    return []


def parse_excluded_pairs(raw):
    """解析互避对 JSON：[[userId1, userId2], ...] → {(1,2),(2,1)}（用于抽签判定）"""
    pairs = set()
    if not raw:
        return pairs
    try:
        data = json.loads(raw)
        for pair in data:
            if isinstance(pair, list) and len(pair) == 2:
                a, b = int(pair[0]), int(pair[1])
                if a != b:
                    pairs.add((min(a, b), max(a, b)))
    except Exception:
        pass
    return pairs


def draw_matches(rows, excluded_pairs):
    """抽签核心：随机环 + 防自抽 + 互避规则。
    返回 (matches, ok)。matches 为空且 ok=False 表示规则太严无法满足。
    """
    from wxcloudrun.draw import draw_matches as _draw_matches
    return _draw_matches(rows, excluded_pairs)


def draw_solvable(n, excluded_pairs):
    """预判互避规则是否可能无解（2 人 / 3 人+互避对 在抽签前提前拒绝）"""
    from wxcloudrun.draw import is_draw_solvable as _is_draw_solvable
    return _is_draw_solvable(n, excluded_pairs)


def send_draw_notifications(db, event_id, rows):
    """抽签完成后通知所有参与者结果已出"""
    # 可观测性埋点：draw_success（唯一调用点 = draw_routes.draw 的写入成功分支）
    log_event("draw_success", event_id=event_id, participant_count=len(rows))
    for p in rows:
        notify(
            db, p["user_id"], event_id, None, "draw_result",
            "抽签结果已出 🎉",
            "你的送礼对象已经确定，快去看看要送谁吧！",
        )


def draw_deadline_passed(event):
    """报名截止（抽签日）已到：支持 ISO datetime 与 YYYY-MM-DD 日期，未设置视为未到"""
    raw = event.get("sign_up_deadline") or ""
    if not raw:
        return False
    value = str(raw).strip()
    try:
        deadline = datetime.fromisoformat(value)
    except ValueError:
        try:
            deadline = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= deadline
