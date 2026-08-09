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
    log_event,
    login_required,
    notify,
    ok,
    participant_rows,
    parse_excluded_pairs,
    send_draw_notifications,
)


def _insert_matches(db, event_id, shuffled):
    """删除该活动旧 matches（连同 gift_likes 点赞，双引擎 FK 级联兜底）并写入新结果。

    返回新 matches 列表（含 id/giver/receiver 的 API 形状）。调用方需先完成
    状态校验与可解性预判，本函数不做业务判断，随 with DB() 事务一并提交。
    """
    db.execute(
        "DELETE FROM gift_likes WHERE match_id IN (SELECT id FROM matches WHERE event_id = ?)",
        (event_id,),
    )
    db.execute("DELETE FROM matches WHERE event_id = ?", (event_id,))
    matches = []
    for index, giver in enumerate(shuffled):
        receiver = shuffled[(index + 1) % len(shuffled)]
        cur = db.execute(
            "INSERT INTO matches (event_id, giver_id, receiver_id) VALUES (?, ?, ?)",
            (event_id, giver["id"], receiver["id"]),
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
    return matches


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
            matches = _insert_matches(db, event["id"], shuffled)
            send_draw_notifications(db, event["id"], rows)
            return ok(matches, "Draw complete")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/redraw", methods=["POST"])
@login_required
def redraw(user, code):
    """重置抽签：仅组织者、仅 drawn 状态可重抽；旧 matches（含物流/晒图/点赞）清空后重新分配。

    - 幂等/并发：活动状态不变（仍 drawn），靠"仅组织者 + 删除后重建"保证；
      重复点击会重新抽（可接受），每次重抽都发新通知（不去重，同内容可合并展示）。
    - 失败回滚：先 draw_solvable 预判 + draw_matches 兜底，任何无解都提前 400，
      不触碰旧 matches（旧结果原样保留）。
    """
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("Only the event creator can redraw", 403)
            if event["status"] != "drawn":
                return fail("活动尚未抽签", 400)

            rows = participant_rows(db, event["id"])
            if len(rows) < 2:
                return fail("At least 2 people are required to draw")
            excluded = parse_excluded_pairs(event.get("excluded_pairs"))
            n = len(rows)
            # 预判：数学上无解的组合在删除旧结果前直接拒绝，旧 matches 保留
            if not draw_solvable(n, excluded):
                if n == 2:
                    return fail("至少需要 3 人才能完成抽签（2 人只能互送，失去随机性）", 400)
                return fail("互避规则太严格，无法完成抽签，请调整互避设置", 400)
            shuffled, draw_ok = draw_matches(rows, excluded)
            if not draw_ok:
                # 兜底：随机重试仍失败（如互避对过于密集），不删旧数据
                return fail("互避规则太严格，无法完成抽签，请调整互避设置", 400)

            matches = _insert_matches(db, event["id"], shuffled)
            # 通知所有成员：每次重抽都发（不去重，旧通知保留）
            for p in rows:
                notify(
                    db, p["user_id"], event["id"], None, "draw_redraw",
                    "抽签已重置 🔄",
                    "抽签已重置，请查看新的送礼任务",
                )
            log_event("draw_redraw", event_id=event["id"], participant_count=len(rows))
            return ok(matches, "Redraw complete")
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
