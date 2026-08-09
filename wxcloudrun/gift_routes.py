"""礼物路由（received-gift、gift-wall、gift-wall/like、note、shipment）。"""
from flask import request

from wxcloudrun.database import DB
from wxcloudrun.helpers import (
    api,
    api_gift_post,
    api_shipment,
    body,
    fail,
    fetch_event,
    image_ref_valid,
    login_required,
    notify,
    ok,
    participant_rows,
    query_kdniao_tracking,
    tracking_degradation_copy,
)


def shipment_state(row):
    """推导送礼状态机当前阶段（Luna 独到项，纯函数）。

    阶段流转：'purchase'（待购买）→ 'shipped'（已发货）→ 'received'（已签收）→ 'posted'（已晒图）。
    优先级：已晒图 > 已签收 > 已发货 > 待购买。
    - posted：gift_review 非空（已晒图）
    - received：received_at 非空但未晒图
    - shipped：有单号或 shipment_status != 'pending'（已发货未签收）
    - purchase：其余（未购买/未发货）
    """
    if row.get("gift_review"):
        return "posted"
    if row.get("received_at"):
        return "received"
    status = row.get("shipment_status") or "pending"
    if status != "pending" or row.get("tracking_number"):
        return "shipped"
    return "purchase"


def gift_wall_allowed(db, event, user_id):
    """礼物墙权限：参与者或组织者"""
    participant = db.get(
        "SELECT id FROM participants WHERE event_id = ? AND user_id = ?",
        (event["id"], user_id),
    )
    return bool(participant) or event["creator_id"] == user_id


def gift_post(row):
    """api_gift_post + 晒图隐私字段（helpers 的 api_gift_post 不含 gift_privacy）。

    privacy: 'photo'=公开照片 / 'text'=仅文字 / 'blur'=模糊照片（旧数据默认 photo）。
    """
    post = api_gift_post(row)
    post["privacy"] = row.get("gift_privacy") or "photo"
    return post


def gift_like_count(db, match_id):
    row = db.get("SELECT COUNT(*) AS count FROM gift_likes WHERE match_id = ?", (match_id,))
    return int(row["count"] or 0)


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
                       m.received_at, m.gift_rating, m.gift_review, m.gift_photo_url, m.gift_privacy,
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
                    "giftPost": gift_post(row),
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
    # 晒图隐私（Luna 独到项）：'photo'=公开照片 / 'text'=仅文字 / 'blur'=模糊照片（默认 photo）
    privacy = str(data.get("privacy") or "photo").strip() or "photo"

    if not match_id:
        return fail("matchId is required")
    try:
        rating_value = int(rating)
    except Exception:
        return fail("请给出评分")
    if rating_value < 1 or rating_value > 5:
        return fail("评分需在 1-5 之间")
    if len(review) > 500:
        return fail("评价内容过长")
    if privacy not in {"photo", "text", "blur"}:
        return fail("晒图隐私设置无效")
    if photo_url and not image_ref_valid(photo_url):
        return fail("照片过大")

    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return fail("你不是该活动的参与者", 403)
            cur = db.execute(
                """
                UPDATE matches
                SET received_at = COALESCE(received_at, CURRENT_TIMESTAMP),
                    gift_rating = ?, gift_review = ?, gift_photo_url = ?, gift_privacy = ?
                WHERE id = ? AND event_id = ? AND receiver_id = ?
                """,
                (rating_value, review, photo_url, privacy, match_id, event["id"], me["id"]),
            )
            if cur.rowcount == 0:
                return fail("未找到对应的送礼任务")
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
            notify(
                db,
                row["giver_user_id"],
                event["id"],
                row["id"],
                "gift_posted",
                f"{row.get('receiver_display_name') or row.get('receiver_username')} 已晒礼物",
                "TA 已收到你的礼物，并完成了晒图评价。",
            )
            # 礼物墙解锁通知：全部晒完时通知所有参与者；用 event_id + type 去重，只发一次
            remaining = db.get(
                "SELECT COUNT(*) AS count FROM matches WHERE event_id = ? AND received_at IS NULL",
                (event["id"],),
            )
            if int(remaining["count"] or 0) == 0 and not db.get(
                "SELECT id FROM notifications WHERE event_id = ? AND type = 'gift_wall_unlocked' LIMIT 1",
                (event["id"],),
            ):
                for p in participant_rows(db, event["id"]):
                    notify(
                        db,
                        p["user_id"],
                        event["id"],
                        None,
                        "gift_wall_unlocked",
                        "礼物墙已解锁 🎉",
                        "所有礼物都已晒出，快去礼物墙看看吧！",
                    )
            return ok(gift_post(row), "晒图已保存")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/received-gift", methods=["DELETE"])
@login_required
def delete_received_gift(user, code):
    """删除晒图（仅收礼人本人，P0）。

    清空晒图字段（照片/评价/评分/隐私）并回退 received_at 为 NULL，
    礼物墙 posted 计数随之 -1，卡片恢复"未揭晓/未晒图"状态。
    未晒图/他人晒图/已删除 一律 404（幂等由前端二次确认 + 本路由拒重删保证）。
    """
    raw_match_id = request.args.get("matchId") or ""
    try:
        match_id = int(raw_match_id)
    except (TypeError, ValueError):
        return fail("matchId is required")
    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return fail("你不是该活动的参与者", 403)
            cur = db.execute(
                """
                UPDATE matches
                SET gift_photo_url = '', gift_review = '', gift_rating = NULL,
                    received_at = NULL, gift_privacy = 'photo'
                WHERE id = ? AND event_id = ? AND receiver_id = ? AND received_at IS NOT NULL
                """,
                (match_id, event["id"], me["id"]),
            )
            if cur.rowcount == 0:
                return fail("未找到对应的送礼任务", 404)
            # 晒图已删：残留点赞一并清掉（卡片恢复未揭晓状态，点赞失去意义）
            db.execute("DELETE FROM gift_likes WHERE match_id = ?", (match_id,))
            return ok(None, "晒图已删除")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/gift-wall")
@login_required
def gift_wall(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if not gift_wall_allowed(db, event, user["userId"]):
                return fail("无权访问", 403)
            counts = db.get(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN received_at IS NOT NULL THEN 1 ELSE 0 END) AS posted
                FROM matches
                WHERE event_id = ?
                """,
                (event["id"],),
            )
            total = int(counts.get("total") or 0)
            posted = int(counts.get("posted") or 0)
            unlocked = total > 0 and total == posted
            rows = []
            like_counts = {}
            liked_by_me = set()
            if unlocked:
                rows = db.all(
                    """
                    SELECT m.id, m.received_at, m.gift_rating, m.gift_review, m.gift_photo_url, m.gift_privacy,
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
                if rows:
                    ids = [row["id"] for row in rows]
                    placeholders = ",".join("?" for _ in ids)
                    for lrow in db.all(
                        f"SELECT match_id, COUNT(*) AS count FROM gift_likes WHERE match_id IN ({placeholders}) GROUP BY match_id",
                        tuple(ids),
                    ):
                        like_counts[lrow["match_id"]] = int(lrow["count"] or 0)
                    for lrow in db.all(
                        f"SELECT match_id FROM gift_likes WHERE match_id IN ({placeholders}) AND user_id = ?",
                        tuple(ids) + (user["userId"],),
                    ):
                        liked_by_me.add(lrow["match_id"])
            return ok(
                {
                    "unlocked": unlocked,
                    "posted": posted,
                    "total": total,
                    "title": event["name"],
                    "note": event.get("description") or "",
                    "budget": event.get("budget_min") or 0,
                    "progress": {
                        "posted": posted,
                        "total": total,
                        "unlocked": unlocked,
                        "remaining": max(0, total - posted),
                    },
                    "items": [
                        {
                            "matchId": row["id"],
                            "giverName": row.get("giver_display_name") or row["giver_username"],
                            "receiverName": row.get("receiver_display_name") or row["receiver_username"],
                            "privacy": row.get("gift_privacy") or "photo",
                            "giftPost": gift_post(row),
                            "likeCount": like_counts.get(row["id"], 0),
                            "likedByMe": row["id"] in liked_by_me,
                        }
                        for row in rows
                    ],
                }
            )
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/gift-wall/like", methods=["POST"])
@login_required
def gift_wall_like(user, code):
    data = body()
    match_id = data.get("matchId")
    if not match_id:
        return fail("matchId is required")
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if not gift_wall_allowed(db, event, user["userId"]):
                return fail("无权访问", 403)
            if not db.get(
                "SELECT id FROM matches WHERE id = ? AND event_id = ?",
                (match_id, event["id"]),
            ):
                return fail("未找到对应的送礼任务", 404)
            existing = db.get(
                "SELECT id FROM gift_likes WHERE match_id = ? AND user_id = ?",
                (match_id, user["userId"]),
            )
            if not existing:
                db.execute(
                    "INSERT INTO gift_likes (match_id, user_id) VALUES (?, ?)",
                    (match_id, user["userId"]),
                )
            return ok(
                {"matchId": match_id, "liked": True, "likeCount": gift_like_count(db, match_id)},
                "Liked",
            )
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/gift-wall/like", methods=["DELETE"])
@login_required
def gift_wall_unlike(user, code):
    raw_match_id = request.args.get("matchId") or ""
    try:
        match_id = int(raw_match_id)
    except (TypeError, ValueError):
        return fail("matchId is required")
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if not gift_wall_allowed(db, event, user["userId"]):
                return fail("无权访问", 403)
            if not db.get(
                "SELECT id FROM matches WHERE id = ? AND event_id = ?",
                (match_id, event["id"]),
            ):
                return fail("未找到对应的送礼任务", 404)
            db.execute(
                "DELETE FROM gift_likes WHERE match_id = ? AND user_id = ?",
                (match_id, user["userId"]),
            )
            return ok(
                {"matchId": match_id, "liked": False, "likeCount": gift_like_count(db, match_id)},
                "Unliked",
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
                return fail("你不是该活动的参与者", 403)
            cur = db.execute("UPDATE matches SET note = ? WHERE id = ? AND giver_id = ?", (note, match_id, me["id"]))
            if cur.rowcount == 0:
                return fail("未找到对应的送礼任务")
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
        return fail("发货状态无效")
    if not match_id:
        return fail("matchId is required")
    if status != "pending" and not tracking_number:
        return fail("请填写快递单号")
    if len(carrier) > 80:
        return fail("快递公司名称过长")
    if len(tracking_number) > 120:
        return fail("快递单号过长")

    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return fail("你不是该活动的参与者", 403)
            old_row = db.get(
                """
                SELECT carrier, tracking_number, tracking_summary
                FROM matches
                WHERE id = ? AND event_id = ? AND giver_id = ?
                """,
                (match_id, event["id"], me["id"]),
            )
            if not old_row:
                return fail("未找到对应的送礼任务")
            shipment_changed = (old_row.get("carrier") or "") != carrier or (old_row.get("tracking_number") or "") != tracking_number

            # 物流自动跟踪：填了单号且配置了 KDNiao 时查询，失败静默降级
            # 单号未变化时保留旧 summary（否则同单号重复提交会把已存摘要清空）
            tracking_summary = old_row.get("tracking_summary") or ""
            if status != "pending" and tracking_number and shipment_changed:
                success, summary, detail = query_kdniao_tracking(db, carrier, tracking_number)
                if success:
                    tracking_summary = summary
                else:
                    # 区分「未接入」与「查询失败」：未配置给自助指引，失败给可重试动作
                    tracking_summary = tracking_degradation_copy(detail)

            cur = db.execute(
                """
                UPDATE matches
                SET shipment_status = ?, carrier = ?, tracking_number = ?,
                    tracking_summary = ?,
                    shipped_at = CASE
                        WHEN ? = 'pending' THEN NULL
                        ELSE COALESCE(shipped_at, CURRENT_TIMESTAMP)
                    END,
                    tracking_updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND event_id = ? AND giver_id = ?
                """,
                (status, carrier, tracking_number, tracking_summary, status, match_id, event["id"], me["id"]),
            )
            if cur.rowcount == 0:
                return fail("未找到对应的送礼任务")

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
                notify(
                    db,
                    row["receiver_user_id"],
                    event["id"],
                    row["id"],
                    "shipment_sent",
                    "你的礼物已发货",
                    f"{row.get('giver_display_name') or row.get('giver_username')} 已填写快递信息，请留意收件。",
                )
            return ok(api_shipment(row), "发货信息已保存")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/shipment/refresh", methods=["POST"])
@login_required
def refresh_shipment_tracking(user, code):
    """物流查询手动刷新：上次查询失败后的重试入口。

    - 仅送礼人本人可刷新自己的 match；单号未变也强制重新外呼（失败结果不缓存，可重试）
    - 成功更新 tracking_summary；失败保留失败文案，前端按钮继续可点
    - 不改变 shipment_status / 不重复通知（不同于 PUT shipment）
    """
    data = body()
    match_id = data.get("matchId")
    if not match_id:
        return fail("matchId is required")
    try:
        with DB() as db:
            event = fetch_event(db, code)
            me = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if not me:
                return fail("你不是该活动的参与者", 403)
            row = db.get(
                "SELECT * FROM matches WHERE id = ? AND event_id = ? AND giver_id = ?",
                (match_id, event["id"], me["id"]),
            )
            if not row:
                return fail("未找到对应的送礼任务")
            if not row.get("tracking_number"):
                return fail("还没有物流单号")
            success, summary, detail = query_kdniao_tracking(db, row.get("carrier") or "", row["tracking_number"])
            tracking_summary = summary if success else tracking_degradation_copy(detail)
            db.execute(
                "UPDATE matches SET tracking_summary = ?, tracking_updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (tracking_summary, match_id),
            )
            row["tracking_summary"] = tracking_summary
            return ok(api_shipment(row), "物流信息已刷新" if success else "物流查询暂不可用")
    except ValueError as exc:
        return fail(str(exc), 404)
