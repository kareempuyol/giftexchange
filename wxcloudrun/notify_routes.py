"""通知路由（notifications、notifications/read）。"""
from wxcloudrun.database import DB
from wxcloudrun.helpers import api, api_notification, body, fail, login_required, ok


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
