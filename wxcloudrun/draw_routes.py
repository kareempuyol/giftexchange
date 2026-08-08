"""抽签路由（draw、matches、my-match）。"""
from wxcloudrun.database import DB
from wxcloudrun.gift_routes import shipment_state
from wxcloudrun.helpers import (
    api,
    api_contact,
    api_gift_post,
    api_preference,
    api_shipment,
    draw_matches,
    draw_solvable,
    fail,
    fetch_event,
    login_required,
    ok,
    participant_rows,
    parse_excluded_pairs,
    send_draw_notifications,
)


@api.route("/events/<code>/draw", methods=["POST"])
@login_required
def draw(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("Only the event creator can draw", 403)
            if event["status"] == "drawn":
                return fail("This event has already been drawn", 409)

            rows = participant_rows(db, event["id"])
            if len(rows) < 2:
                return fail("At least 2 people are required to draw")
            excluded = parse_excluded_pairs(event.get("excluded_pairs"))
            n = len(rows)
            # 预判：数学上无解的组合在抽签前直接拒绝，给出明确提示
            if not draw_solvable(n, excluded):
                if n == 2:
                    return fail("至少需要 3 人才能完成抽签（2 人只能互送，失去随机性）", 400)
                return fail("互避规则太严格，无法完成抽签，请调整互避设置", 400)
            shuffled, draw_ok = draw_matches(rows, excluded)
            if not draw_ok:
                # 兜底：随机重试仍失败（如互避对过于密集），不写任何数据、不改状态
                return fail("互避规则太严格，无法完成抽签，请调整互避设置", 400)

            # 并发幂等：条件更新 open→drawn 先抢锁；rowcount=0 说明并发下已被其他请求抽过。
            # 抢锁失败时尚未触碰 matches 数据（不删旧、不插新），事务提交无副作用
            cur_status = db.execute(
                "UPDATE events SET status = 'drawn', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'open'",
                (event["id"],),
            )
            if cur_status.rowcount == 0:
                return fail("Draw already completed", 409)

            # 只有抢锁成功的请求才写 matches（DELETE 旧 + INSERT 新，随 with DB() 事务一并提交）
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
            send_draw_notifications(db, event["id"], rows)
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
                       p.preference_size, p.preference_color, p.wish_links,
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
                    "shipmentState": shipment_state(row),
                    "shipment": api_shipment(row),
                    "giftPost": api_gift_post(row),
                    "contact": api_contact(row),
                    "preference": api_preference(row),
                }
            )
    except ValueError as exc:
        return fail(str(exc), 404)
