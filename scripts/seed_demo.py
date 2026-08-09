#!/usr/bin/env python3
"""演示种子数据（hackathon 轮5）：新用户登录 demo 账号即有内容可看。

幂等设计（可重复执行，重复跑不重复造数据）：
- demo 用户按 username 查重：已存在则跳过（不覆盖）。
- 示例活动按固定 code（demo-christmas-2026）查重：已存在则整个活动
  （参与者/匹配/通知）跳过 —— 活动相关数据只在活动首次创建时写入。
- 示例活动晒图照片走 storage.py 先写 data/uploads 再存 URL（不往 DB 写 base64）。

种子内容：
- 3 个 demo 用户：demo_alice / demo_bob / demo_carol（密码 Demo1234，组织者为 alice）
- 1 个示例活动「圣诞礼物交换 🎄」：公开、3 人、已抽签、部分发货/晒图、礼物墙已解锁
  - 3 条 match：1 条带完整物流（发货），2 条当面送达；3 条全部已收 + 已晒图 → 礼物墙解锁
  - 2 条晒图带照片（公开/模糊），1 条仅文字（privacy=text 演示隐私三模式）
- 通知：抽签结果/礼物墙解锁/晒图（已读未读混合，时间线错开）

用法：
    python3 scripts/seed_demo.py          # 幂等种子（SQLite 默认 data/gift_exchange.db）
    DB_PATH=/path/to.db python3 scripts/seed_demo.py   # 指定 SQLite 路径
    # 设置了 MYSQL_ADDRESS/MYSQL_HOST 时自动走 MySQL（wxcloudrun.database.DB 双引擎）
"""
import os
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wxcloudrun.auth import hash_password  # noqa: E402
from wxcloudrun.database import DB, init_schema  # noqa: E402
from wxcloudrun.helpers import generate_short_code  # noqa: E402
from wxcloudrun.notify import notify  # noqa: E402
from wxcloudrun.storage import storage  # noqa: E402

DEMO_PASSWORD = "Demo1234"
DEMO_USERS = [
    {"username": "demo_alice", "email": "demo_alice@example.com", "display_name": "爱丽丝"},
    {"username": "demo_bob", "email": "demo_bob@example.com", "display_name": "鲍勃"},
    {"username": "demo_carol", "email": "demo_carol@example.com", "display_name": "卡罗尔"},
]
DEMO_EVENT_CODE = "demo-christmas-2026"


def _utc_ts(days_ago, hour=10, minute=0):
    """过去第 N 天的 UTC 时间戳字符串（YYYY-MM-DD HH:MM:SS，双引擎通用）。"""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _solid_png(width, height, rgb):
    """生成纯色 PNG（无 PIL 依赖：struct + zlib 手写，魔数合法可被 SafeImage 渲染）。"""
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    idat = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def _seed_photo(rgb, label):
    """照片先落盘 data/uploads 再返回可访问 URL（先传后引用，不往 DB 写 base64）。

    与 /api/upload 同一落盘约定：storage.save(folder='') 平铺到 uploads_dir()
    （即 data/uploads/<uuid>.png），/uploads/<filename> 路由直接可读；
    save_image() 会嵌套到 uploads/uploads/，URL 会对不上，这里不能用。
    """
    key = storage.save(_solid_png(64, 64, rgb), "png", folder="")
    # 与 /api/upload 一致：URL 手工拼 /uploads/ 前缀（storage.url_for 只加 "/"）
    url = f"/uploads/{key}"
    print(f"  [seed] 照片已落盘: {key} -> {url}（{label}）")
    return url


def _seed_users(db):
    """幂等建 demo 用户：username 已存在则跳过（不覆盖密码/资料）。返回 {username: id}。"""
    ids = {}
    for u in DEMO_USERS:
        row = db.get("SELECT id FROM users WHERE username = ?", (u["username"],))
        if row:
            ids[u["username"]] = row["id"]
            print(f"  [skip] 用户已存在: {u['username']}")
            continue
        cur = db.execute(
            """
            INSERT INTO users (username, email, password, display_name)
            VALUES (?, ?, ?, ?)
            """,
            (u["username"], u["email"], hash_password(DEMO_PASSWORD), u["display_name"]),
        )
        ids[u["username"]] = cur.lastrowid
        print(f"  [seed] 创建用户: {u['username']}（密码 {DEMO_PASSWORD}）")
    return ids


def _seed_event(db, user_ids):
    """幂等建示例活动 + 参与者 + match + 晒图照片。活动已存在则整体跳过。"""
    existing = db.get("SELECT id FROM events WHERE code = ?", (DEMO_EVENT_CODE,))
    if existing:
        print(f"  [skip] 示例活动已存在: {DEMO_EVENT_CODE}")
        return None
    if len(user_ids) < 3:
        print("  [error] demo 用户不齐，无法建活动", file=sys.stderr)
        return None

    alice, bob, carol = user_ids["demo_alice"], user_ids["demo_bob"], user_ids["demo_carol"]
    short_code = generate_short_code(db)
    cur = db.execute(
        """
        INSERT INTO events (
            code, name, description, budget_min, creator_id, status,
            match_visibility, sign_up_deadline, participant_count, cover_image,
            is_public, max_participants, short_code, excluded_pairs,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            DEMO_EVENT_CODE,
            "圣诞礼物交换 🎄",
            "3 位朋友的圣诞礼物交换：已抽签完成，大家陆续晒出了礼物～",
            100,
            alice,
            "drawn",
            "public",  # 抽签结果全员可见
            "2025-12-20 20:00:00",
            3,
            "",
            1,
            3,
            short_code,
            "[]",
            _utc_ts(30),
            _utc_ts(30),
        ),
    )
    event_id = cur.lastrowid
    print(f"  [seed] 创建活动: 圣诞礼物交换 🎄 (code={DEMO_EVENT_CODE}, short={short_code})")

    # 参与者（3 人，每人填好收件信息 + 心愿单，演示已就绪状态）
    p_ids = {}
    participants = [
        (alice, "爱丽丝", "爱丽丝", "13800000001", "北京市朝阳区望京 SOHO T1", "香薰蜡烛、手帐本、围巾", "毛绒玩具", "喜欢暖色系，预算 100 左右"),
        (bob, "鲍勃", "鲍勃", "13800000002", "上海市浦东新区张江高科", "蓝牙耳机、保温杯、咖啡豆", "袜子", "最近在学手冲咖啡 ☕"),
        (carol, "卡罗尔", "卡罗尔", "13800000003", "广州市天河区珠江新城", "护手霜、书签、小夜灯", "零食大礼包", "喜欢绿色和简约风"),
    ]
    for user_id, nickname, receiver, phone, address, likes, dislikes, notes in participants:
        cur = db.execute(
            """
            INSERT INTO participants (
                event_id, user_id, nickname, receiver_name, phone, address,
                preference_likes, preference_dislikes, preference_notes,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, user_id, nickname, receiver, phone, address, likes, dislikes, notes, _utc_ts(28)),
        )
        p_ids[user_id] = cur.lastrowid
    print("  [seed] 创建 3 名参与者（收件信息 + 心愿单已填）")

    # match：alice→bob（带完整物流）、bob→carol（当面送达）、carol→alice（当面送达）
    # 全部 received → 礼物墙解锁；物流数据只在 1 条上 → 部分发货
    match_rows = [
        # (giver, receiver, note, shipment)
        (alice, bob, "挑了一条手织围巾，希望你喜欢这个冬天 ❄️", True),
        (bob, carol, "咖啡豆 + 手冲壶，愿你每天都有好心情 ☕", False),
        (carol, alice, "香薰小夜灯，睡前一点温柔的光 🕯️", False),
    ]
    match_ids = {}
    for i, (giver, receiver, note, with_shipment) in enumerate(match_rows):
        cur = db.execute(
            """
            INSERT INTO matches (
                event_id, giver_id, receiver_id, note, shipment_status,
                carrier, tracking_number, shipped_at, tracking_summary,
                received_at, gift_rating, gift_review, gift_photo_url, gift_privacy,
                matched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                p_ids[giver],
                p_ids[receiver],
                note,
                "shipped" if with_shipment else "pending",
                "顺丰速运" if with_shipment else None,
                "SF1234567890123" if with_shipment else None,
                _utc_ts(12) if with_shipment else None,
                "已签收，感谢使用顺丰速运" if with_shipment else None,
                _utc_ts(9),
                5,
                "包装很用心，围巾的质感和颜色都超喜欢，谢谢圣诞老人！🎄",
                _seed_photo((232, 85, 61), "match1 晒图照片") if i == 0 else "",
                "photo",
                _utc_ts(25),
            ),
        )
        match_ids[i] = cur.lastrowid
    print("  [seed] 创建 3 条 match（1 条带物流 / 2 条当面送达；全部已收已晒图 → 礼物墙解锁）")

    # 回填不同晒图形态：match2 仅文字、match3 公开照片 + 模糊照片演示隐私三模式
    db.execute(
        "UPDATE matches SET gift_privacy = 'text', gift_photo_url = '', gift_review = '手冲壶很好用，豆子也很新鲜，谢谢！' WHERE id = ?",
        (match_ids[1],),
    )
    db.execute(
        "UPDATE matches SET gift_privacy = 'photo', gift_review = '小夜灯的光很温柔，每晚都开着，谢谢！' WHERE id = ?",
        (match_ids[2],),
    )
    db.execute(
        "UPDATE matches SET gift_photo_url = ?, gift_review = '小夜灯的光很温柔，每晚都开着，谢谢！' WHERE id = ?",
        (_seed_photo((95, 158, 130), "match3 晒图照片"), match_ids[2]),
    )

    # 礼物墙点赞：互相点赞让礼物墙有互动感（活动整体幂等，无需 INSERT OR IGNORE）
    db.execute(
        "INSERT INTO gift_likes (match_id, user_id) VALUES (?, ?)",
        (match_ids[0], carol),
    )
    db.execute(
        "INSERT INTO gift_likes (match_id, user_id) VALUES (?, ?)",
        (match_ids[1], alice),
    )
    db.execute(
        "INSERT INTO gift_likes (match_id, user_id) VALUES (?, ?)",
        (match_ids[2], bob),
    )
    print("  [seed] 礼物墙 3 个点赞（每人给别人的晒图点了一个赞）")
    return event_id


def _seed_notifications(db, event_id, user_ids):
    """通过 notify() 统一入口写通知，再按 id 回填 read_at / created_at 形成已读未读混合时间线。

    先 notify() 拿最新一条 id（user_id+event_id+type 在种子内唯一），再 UPDATE 该 id ——
    避免「UPDATE 同表子查询 MAX」的 MySQL 1093 限制，双引擎通用。
    """
    if event_id is None:
        return
    alice, bob, carol = user_ids["demo_alice"], user_ids["demo_bob"], user_ids["demo_carol"]
    plans = [
        # (user_id, type, title, message, days_ago, read)
        (alice, "draw_result", "抽签结果已出 🎉", "你的送礼对象已经确定，快去看看要送谁吧！", 20, True),
        (bob, "draw_result", "抽签结果已出 🎉", "你的送礼对象已经确定，快去看看要送谁吧！", 20, True),
        (carol, "draw_result", "抽签结果已出 🎉", "你的送礼对象已经确定，快去看看要送谁吧！", 20, False),
        (alice, "shipment_sent", "你的礼物已发货 📦", "顺丰速运 SF1234567890123 已揽收，请留意收件。", 11, True),
        (bob, "gift_posted", "TA 已晒出礼物 ✨", "爱丽丝 晒出了送给你的礼物，快去看看吧！", 8, False),
        (carol, "gift_posted", "TA 已晒出礼物 ✨", "鲍勃 晒出了送给你的礼物，快去看看吧！", 8, False),
        (alice, "gift_posted", "TA 已晒出礼物 ✨", "卡罗尔 晒出了送给你的礼物，快去看看吧！", 5, False),
        (alice, "gift_wall_unlocked", "礼物墙已解锁 🎉", "所有礼物都已晒出，快去礼物墙看看吧！", 5, True),
        (bob, "gift_wall_unlocked", "礼物墙已解锁 🎉", "所有礼物都已晒出，快去礼物墙看看吧！", 5, False),
        (carol, "gift_wall_unlocked", "礼物墙已解锁 🎉", "所有礼物都已晒出，快去礼物墙看看吧！", 5, False),
    ]
    for user_id, type_name, title, message, days_ago, is_read in plans:
        if not notify(db, user_id, event_id, None, type_name, title, message):
            continue  # 被通知偏好过滤（demo 用户默认全开，一般不会走到）
        row = db.get(
            "SELECT MAX(id) AS id FROM notifications WHERE user_id = ? AND event_id = ? AND type = ?",
            (user_id, event_id, type_name),
        )
        if not row or not row.get("id"):
            continue
        nid = row["id"]
        created_at = _utc_ts(days_ago)
        if is_read:
            read_at = _utc_ts(days_ago, hour=12)
            db.execute(
                "UPDATE notifications SET created_at = ?, read_at = ? WHERE id = ?",
                (created_at, read_at, nid),
            )
        else:
            db.execute(
                "UPDATE notifications SET created_at = ? WHERE id = ?",
                (created_at, nid),
            )
    print(f"  [seed] 写入 10 条通知（已读/未读混合，时间线错开）")


def main():
    init_schema()  # 建表 + 迁移幂等；保证脚本可在全新库上直接跑
    with DB() as db:
        print("[seed_demo] 开始（幂等：已存在的用户/活动自动跳过）")
        user_ids = _seed_users(db)
        event_id = _seed_event(db, user_ids)
        _seed_notifications(db, event_id, user_ids)
        print("[seed_demo] 完成。")
        print("  演示账号：demo_alice / demo_bob / demo_carol（密码 Demo1234）")
        print("  示例活动：圣诞礼物交换 🎄（公开、已抽签、礼物墙已解锁）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
