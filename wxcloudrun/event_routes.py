"""活动路由（events CRUD、list、public、joined、preview、join、leave、participants、dashboard）。"""
import json
import uuid
from datetime import datetime, timezone

from flask import request

from wxcloudrun.database import DB
from wxcloudrun.helpers import (
    add_participant,
    api,
    api_event,
    api_event_summary,
    body,
    current_user_row,
    draw_deadline_passed,
    event_visible_to,
    fail,
    fetch_event,
    generate_short_code,
    image_ref_valid,
    log_event,
    login_required,
    notify,
    ok,
    participant_payload,
    participant_rows,
    parse_datetime,
)


@api.route("/events", methods=["POST"])
@login_required
def create_event(user):
    data = body()
    title = str(data.get("title") or "").strip()
    note = str(data.get("note") or "").strip()
    draw_date = str(data.get("drawDate") or "")
    try:
        budget = int(data.get("budget") or 0)
    except (TypeError, ValueError):
        return fail("预算格式无效")
    match_visibility = str(data.get("matchVisibility") or data.get("match_visibility") or "private").strip()
    is_public = bool(data.get("isPublic")) if data.get("isPublic") is not None else True
    max_participants = data.get("maxParticipants")
    cover_image = str(data.get("coverImage") or "").strip()
    excluded_pairs_raw = data.get("excludedPairs")
    excluded_pairs = json.dumps(excluded_pairs_raw, ensure_ascii=False) if excluded_pairs_raw else "[]"

    if not title:
        return fail("请填写活动名称")
    if len(title) > 100:
        return fail("活动名称过长")
    if budget < 0:
        return fail("预算不能为负数")
    if len(note) > 500:
        return fail("活动说明过长")
    if match_visibility not in {"private", "public"}:
        return fail("匹配可见性设置无效")
    if max_participants is not None:
        try:
            max_participants = int(max_participants)
        except (ValueError, TypeError):
            return fail("人数上限设置无效")
        if max_participants < 2:
            return fail("人数上限至少为 2")
        if max_participants > 999:
            return fail("人数上限过大")
    if cover_image and not image_ref_valid(cover_image):
        return fail("封面图过大")

    with DB() as db:
        code = str(uuid.uuid4())
        short_code = generate_short_code(db)
        cur = db.execute(
            """
            INSERT INTO events (code, name, description, budget_min, creator_id, sign_up_deadline,
                                match_visibility, is_public, max_participants, cover_image, short_code, excluded_pairs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (code, title, note, budget, user["userId"], draw_date, match_visibility,
             1 if is_public else 0, max_participants, cover_image, short_code, excluded_pairs),
        )
        # 组织者自动加入：创建即参与者（participant_count +1，抽签门槛/人数上限随之计算）。
        # 收件信息取用户资料默认值，与手动 join 同一路径；加入动作不通知任何人（不打扰创建者）。
        add_participant(db, cur.lastrowid, user["userId"])
        # 可观测性埋点：event_created（INSERT 成功后打；generate_short_code 已无副作用，
        # reset-short-code 不会误报活动创建）
        log_event("event_created")
        return ok(api_event(fetch_event(db, code)), "Event created", 201)


@api.route("/events/mine")
@login_required
def my_events(user):
    with DB() as db:
        rows = db.all(
            """
            SELECT e.*, u.username AS owner_username
            FROM events e JOIN users u ON u.id = e.creator_id
            WHERE e.creator_id = ? AND e.archived = 0
            ORDER BY e.created_at DESC
            """,
            (user["userId"],),
        )
        return ok([api_event_summary(row) for row in rows])


@api.route("/events/archived")
@login_required
def archived_events(user):
    """组织者视角的已归档活动列表（归档只影响列表可见性，详情仍可访问）。"""
    with DB() as db:
        rows = db.all(
            """
            SELECT e.*, u.username AS owner_username
            FROM events e JOIN users u ON u.id = e.creator_id
            WHERE e.creator_id = ? AND e.archived = 1
            ORDER BY e.created_at DESC
            """,
            (user["userId"],),
        )
        return ok([api_event_summary(row) for row in rows])


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
            WHERE p.user_id = ? AND e.archived = 0
            ORDER BY e.created_at DESC
            """,
            (user["userId"],),
        )
        return ok([api_event_summary(row) for row in rows])


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
        conditions = ["e.status = 'open'", "e.is_public = 1", "e.archived = 0"]
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
            "events": [api_event_summary(row) for row in events],
            "total": total,
            "page": page,
            "perPage": per_page,
        })


def derive_flow_state(event_row, posted, total):
    """活动级流程状态推导（纯函数，event detail 用）：
    recruiting（open 且未过截止）→ drawing（已过截止未抽签）→ active（drawn 未全晒）→ completed（drawn 且全部 posted）。
    sign_up_deadline 为空视为未截止；未知状态兜底 active。
    """
    if event_row.get("status") == "drawn":
        return "completed" if total > 0 and posted >= total else "active"
    if event_row.get("status") == "open":
        return "drawing" if draw_deadline_passed(event_row) else "recruiting"
    return "active"


def _event_flow_state(db, event):
    """detail 接口用：统计已晒图数（收礼 match 有评分/评价/照片）+ 参与总数，推导流程状态。"""
    total = int(event.get("participant_count") or 0)
    posted = 0
    if event["status"] == "drawn":
        row = db.get(
            "SELECT COUNT(*) AS c FROM matches WHERE event_id = ? "
            "AND (gift_rating IS NOT NULL OR gift_review IS NOT NULL OR gift_photo_url IS NOT NULL)",
            (event["id"],),
        )
        posted = int(row["c"]) if row else 0
    return derive_flow_state(event, posted, total)


@api.route("/events/<code>", methods=["GET"])
@login_required
def event_detail(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            # 可见性（P1 修复）：公开活动所有登录用户可见；私密活动仅创建者与参与者
            if not event_visible_to(db, event, user["userId"]):
                return fail("活动不存在或无权访问", 403)
            payload = api_event(event)
            payload["flowState"] = _event_flow_state(db, event)
            return ok(payload)
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/preview", methods=["GET"])
def event_preview(code):
    """游客可读的活动概要（邀请落地页用，不泄露收件人/发货等敏感信息）"""
    try:
        with DB() as db:
            event = fetch_event(db, code)
            participant_row = db.get(
                "SELECT COUNT(*) AS c FROM participants WHERE event_id = ?",
                (event["id"],),
            )
            participant_count = participant_row["c"] if participant_row else 0
            return ok({
                "code": event["code"],
                "shortCode": event["short_code"],
                "title": event["name"],
                "note": event.get("note") or "",
                "budget": event.get("budget"),
                "signUpDeadline": event.get("sign_up_deadline"),
                "status": event["status"],
                "coverImage": event.get("cover_image") or "",
                "participantCount": participant_count,
                "isPublic": bool(event.get("is_public")),
            })
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>", methods=["PATCH"])
@login_required
def edit_event(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("仅创建者可编辑活动", 403)

            data = body()
            fields = {}
            params = []

            if "title" in data:
                title = str(data["title"] or "").strip()
                if not title:
                    return fail("活动名称不能为空")
                if len(title) > 100:
                    return fail("活动名称过长")
                fields["name"] = title
                params.append(title)

            if "coverImage" in data:
                cover = str(data["coverImage"] or "").strip()
                if cover and not image_ref_valid(cover):
                    return fail("封面图过大")
                fields["cover_image"] = cover
                params.append(cover)

            if "drawDate" in data:
                draw = str(data["drawDate"] or "")
                if draw:
                    try:
                        dt = parse_datetime(draw)
                        if dt <= datetime.now(timezone.utc):
                            return fail("截止时间必须晚于当前时间")
                    except Exception:
                        return fail("日期格式无效")
                fields["sign_up_deadline"] = draw
                params.append(draw)

            if "maxParticipants" in data:
                max_p = data["maxParticipants"]
                if max_p is not None:
                    try:
                        max_p = int(max_p)
                    except (ValueError, TypeError):
                        return fail("人数上限设置无效")
                    if max_p < 2:
                        return fail("人数上限至少为 2")
                    if max_p > 999:
                        return fail("人数上限过大")
                    current_count = int(event.get("participant_count") or 0)
                    if max_p < current_count:
                        return fail(f"Cannot set max below current participant count ({current_count})")
                fields["max_participants"] = max_p
                params.append(max_p)

            if "isPublic" in data:
                is_public = bool(data["isPublic"])
                fields["is_public"] = 1 if is_public else 0
                params.append(1 if is_public else 0)

            if "excludedPairs" in data:
                fields["excluded_pairs"] = json.dumps(data["excludedPairs"], ensure_ascii=False)
                params.append(fields["excluded_pairs"])

            if not fields:
                return fail("没有需要更新的内容")

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
    """硬删除活动（仅创建者，API 直达；前端 UI 无删除入口，只暴露归档）。

    删除语义与归档互补（不重叠）：
      - 硬删除（本路由）：物理删除 events 行，级联清理 participants/matches/gift_likes
        （双引擎 FK ON DELETE CASCADE 兜底）+ 显式清理 notifications（无 event_id 外键，
        必须显式删，否则留孤儿通知）。删除后数据不可恢复。
      - 软删除（POST /events/<code>/archive）：仅 drawn 活动，置 archived=1，
        所有关联数据原样保留，可 unarchive 恢复。
    约定：open（未抽签）活动无历史数据价值 → 直接硬删除；drawn（已抽签）活动
    前端引导走归档（数据保留）。两者在任一状态都可执行，语义由调用方选择；
    无管理台删除入口（admin 角色仅管理 settings，不越权删他人活动）。
    """
    with DB() as db:
        event = db.get("SELECT id FROM events WHERE code = ? AND creator_id = ?", (code, user["userId"]))
        if not event:
            return fail("活动不存在或无权访问", 403)
        # 级联清理：participants/matches/gift_likes 由 FK ON DELETE CASCADE 兜底（双引擎已建 FK）；
        # notifications 无 event_id 外键（站内通知按 user 级联），必须显式清理，否则删活动留孤儿通知
        db.execute("DELETE FROM notifications WHERE event_id = ?", (event["id"],))
        db.execute("DELETE FROM events WHERE id = ?", (event["id"],))
        return ok(None, "Event deleted")


@api.route("/events/<code>/archive", methods=["POST"])
@login_required
def archive_event(user, code):
    """归档活动（软删除）：仅组织者；已抽签（drawn）才能归档，open 直接删除。

    软删语义与 DELETE /events/<code>（硬删除）互补：
    - 归档 = 软删除，数据（participants/matches/notifications/gift_likes）原样保留，
      只影响列表可见性（mine/joined/public 隐藏，archived 列表可见，详情仍可访问），
      可 unarchive 恢复。
    - 硬删除 = 物理删除 + 级联清理，不可恢复；open 活动走硬删除。
    drawn 活动数据有历史价值（晒图/物流），一律走归档，避免误删。
    """
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("仅创建者可归档活动", 403)
            if event["status"] != "drawn":
                return fail("未抽签活动请直接删除", 400)
            db.execute("UPDATE events SET archived = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event["id"],))
            return ok(api_event(fetch_event(db, code)), "Event archived")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/unarchive", methods=["POST"])
@login_required
def unarchive_event(user, code):
    """恢复归档活动：仅组织者，置回 archived=0（回到默认列表）。"""
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("仅创建者可恢复活动", 403)
            db.execute("UPDATE events SET archived = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event["id"],))
            return ok(api_event(fetch_event(db, code)), "Event unarchived")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/reset-short-code", methods=["POST"])
@login_required
def reset_short_code(user, code):
    """重置邀请短码：仅组织者；生成新 6 位短码覆盖旧码，旧链接立即失效（短码查不到活动）。"""
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("仅创建者可重置邀请码", 403)
            new_code = generate_short_code(db)
            db.execute("UPDATE events SET short_code = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_code, event["id"]))
            return ok({"code": event["code"], "shortCode": new_code}, "Short code reset")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/join", methods=["POST"])
@login_required
def join_event(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            # 报名截止（抽签日已过）或活动已抽签：一律拒绝新加入
            if event["status"] != "open" or draw_deadline_passed(event):
                return fail("活动已截止报名")
            max_ppl = event.get("max_participants")
            if max_ppl is not None and int(event.get("participant_count") or 0) >= int(max_ppl):
                return fail("活动人数已满")
            if db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"])):
                return fail("你已加入该活动")
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
            # 加入确认通知给本人（自己的动作，不受偏好过滤拦截）
            notify(
                db,
                user["userId"],
                event["id"],
                None,
                "join_success",
                f"你已加入「{event['name']}」",
                "加入成功，等待组织者抽签吧 🎁",
            )
            # 通知组织者：新参与者加入（组织者自己加入不通知自己）
            if event["creator_id"] != user["userId"]:
                joiner_name = user_row.get("display_name") or user_row["username"]
                notify(
                    db,
                    event["creator_id"],
                    event["id"],
                    None,
                    "participant_joined",
                    f"{joiner_name} 加入了活动",
                    f"{joiner_name} 加入了「{event['name']}」，快去看看吧。",
                )
            return ok(
                {"id": participant_id, "eventCode": code, "userName": user_row.get("display_name") or user_row["username"]},
                "Joined event",
                201,
            )
    except ValueError as exc:
        message = str(exc)
        return fail(message, 404 if message == "活动不存在或已失效" else 400)


@api.route("/events/<code>/leave", methods=["DELETE"])
@login_required
def leave_event(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] == user["userId"]:
                return fail("创建者不能退出，请删除活动")
            if event["status"] != "open":
                return fail("活动已抽签")
            cur = db.execute("DELETE FROM participants WHERE event_id = ? AND user_id = ?", (event["id"], user["userId"]))
            if cur.rowcount == 0:
                return fail("你尚未加入该活动")
            db.execute(
                "UPDATE events SET participant_count = participant_count - 1, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND participant_count > 0",
                (event["id"],),
            )
            return ok(None, "Left event")
    except ValueError as exc:
        return fail(str(exc), 404)


def _member_match_rows(db, event_id):
    """每个参与者对应的送礼/收礼 match 数据。

    抽签后每人至多一条送礼 match、一条收礼 match（重抽会先 DELETE 旧 matches 再重建），
    因此按 participant 双向 LEFT JOIN 不会产生重复行。
    """
    return db.all(
        """
        SELECT p.id AS participant_id,
               gm.id AS giver_match_id,
               gm.shipment_status AS giver_shipment_status,
               gm.tracking_number AS giver_tracking_number,
               rm.id AS receiver_match_id,
               rm.gift_review AS receiver_gift_review
        FROM participants p
        LEFT JOIN matches gm ON gm.giver_id = p.id AND gm.event_id = ?
        LEFT JOIN matches rm ON rm.receiver_id = p.id AND rm.event_id = ?
        WHERE p.event_id = ?
        """,
        (event_id, event_id, event_id),
    )


def member_status(row, match_row):
    """成员完成度状态，按完成度取最高档：joined < ready < shipped < posted。

    - joined：已加入但收件信息（收件人/电话/地址）未填全
    - ready：已加入且收件信息填全
    - shipped：其送礼 match 已发货（有物流单号或 shipment_status != 'pending'）
    - posted：其收礼 match 已晒图（gift_review 非空）
    """
    if match_row and match_row.get("receiver_gift_review"):
        return "posted"
    if match_row and (match_row.get("giver_shipment_status") not in (None, "", "pending") or match_row.get("giver_tracking_number")):
        return "shipped"
    if row.get("receiver_name") and row.get("phone") and row.get("address"):
        return "ready"
    return "joined"


@api.route("/events/<code>/participants")
@login_required
def participants(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            # 可见性（P1 修复）：公开活动所有登录用户可见；私密活动仅创建者与参与者
            if not event_visible_to(db, event, user["userId"]):
                return fail("活动不存在或无权访问", 403)
            rows = participant_rows(db, event["id"])
            match_by_participant = {m["participant_id"]: m for m in _member_match_rows(db, event["id"])}
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
                    "status": member_status(row, match_by_participant.get(row["id"]) or {}),
                }
                for row in rows
            ]
            return ok({"participants": data, "count": len(data)})
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/remind", methods=["POST"])
@login_required
def remind_members(user, code):
    """催办未完成成员：仅组织者。

    给所有未完成成员（未填收件信息 / 未发货 / 未晒图，即 status != 'posted'）发站内
    type='remind' 通知；组织者自己不算（自己的完成度在成员列表可见）。
    """
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("仅创建者可催办成员", 403)
            rows = participant_rows(db, event["id"])
            match_by_participant = {m["participant_id"]: m for m in _member_match_rows(db, event["id"])}
            name = event["name"]
            reminded = 0
            for row in rows:
                if row["user_id"] == event["creator_id"]:
                    continue  # 组织者不催自己
                status = member_status(row, match_by_participant.get(row["id"]) or {})
                if status == "posted":
                    continue
                if status == "joined":
                    message = f"你已加入「{name}」但还未填写收件信息（收件人/电话/地址），请尽快补充，否则对方无法寄出礼物。"
                elif status == "ready":
                    message = f"「{name}」的礼物还未寄出，请尽快发货并填写物流单号。"
                else:  # shipped
                    message = f"「{name}」的礼物已寄出，收到后记得晒图分享。"
                notify(db, row["user_id"], event["id"], None, "remind", f"「{name}」待完成提醒", message)
                reminded += 1
            return ok({"reminded": reminded}, f"已提醒 {reminded} 人")
    except ValueError as exc:
        return fail(str(exc), 404)


@api.route("/events/<code>/dashboard")
@login_required
def event_dashboard(user, code):
    try:
        with DB() as db:
            event = fetch_event(db, code)
            if event["creator_id"] != user["userId"]:
                return fail("仅创建者可查看仪表盘", 403)
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
            pending_shipments = 0
            unposted_gifts = 0
            for row in participants_data:
                match_row = match_by_participant.get(row["id"]) or {}
                # 催办统计并入同一循环（matches 已按 receiver 全量拉齐，
                # 与单独 COUNT 等价——每个 match 必有 receiver 参与者）：
                # 已抽签未发货（shipment_status='pending'）/ 已发货未晒图（有物流且未签收）
                if match_row.get("match_id"):
                    if (match_row.get("shipment_status") or "pending") == "pending":
                        pending_shipments += 1
                    elif match_row.get("received_at") is None:
                        unposted_gifts += 1
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
            # 催办提醒
            reminders = []
            if event["status"] != "drawn":
                if draw_deadline_passed(event):
                    reminders.append({"type": "draw", "message": "报名截止时间已到，快去抽签"})
            else:
                if pending_shipments > 0:
                    reminders.append({"type": "shipment", "message": f"{pending_shipments} 人已抽签未发货"})
                if unposted_gifts > 0:
                    reminders.append({"type": "gift", "message": f"{unposted_gifts} 人已发货未晒图"})
            return ok(
                {
                    "participants": data,
                    "count": len(data),
                    "pendingShipments": pending_shipments,
                    "unpostedGifts": unposted_gifts,
                    "reminders": reminders,
                }
            )
    except ValueError as exc:
        return fail(str(exc), 404)
