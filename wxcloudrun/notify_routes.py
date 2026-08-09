"""通知路由（notifications、notifications/read、clear、preferences）。"""
import json

from wxcloudrun.database import DB
from wxcloudrun.helpers import api, api_notification, body, fail, login_required, ok
from wxcloudrun.notify import DEFAULT_PREFS, user_notification_prefs


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
            # 批量标记已读：单条 UPDATE ... IN 代替逐条 UPDATE（N+1 消除）
            for chunk_start in range(0, len(ids), 500):
                chunk = ids[chunk_start:chunk_start + 500]
                placeholders = ",".join("?" for _ in chunk)
                db.execute(
                    f"UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP) "
                    f"WHERE id IN ({placeholders}) AND user_id = ?",
                    tuple(chunk) + (user["userId"],),
                )
        else:
            db.execute(
                "UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP) WHERE user_id = ?",
                (user["userId"],),
            )
        return ok(None, "Notifications marked read")


@api.route("/notifications/clear", methods=["POST"])
@login_required
def clear_read_notifications(user):
    """清空已读通知（保留未读）。"""
    with DB() as db:
        db.execute(
            "DELETE FROM notifications WHERE user_id = ? AND read_at IS NOT NULL",
            (user["userId"],),
        )
        return ok(None, "Read notifications cleared")


@api.route("/notifications/preferences", methods=["GET"])
@login_required
def get_notification_preferences(user):
    with DB() as db:
        return ok(user_notification_prefs(db, user["userId"]))


@api.route("/notifications/preferences", methods=["PUT"])
@login_required
def update_notification_preferences(user):
    """更新通知偏好。body 键与存储键一致（DEFAULT_PREFS：deadline/draw/giftReceived/remind），
    传部分键只改传到的项，未知键忽略；返回合并后的完整偏好。"""
    data = body()
    with DB() as db:
        current = user_notification_prefs(db, user["userId"])
        changed = False
        for key in DEFAULT_PREFS:
            if key in data:
                current[key] = bool(data[key])
                changed = True
        if changed:
            db.execute(
                "UPDATE users SET notification_prefs = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(current, ensure_ascii=False), user["userId"]),
            )
        return ok(current, "Preferences saved")
