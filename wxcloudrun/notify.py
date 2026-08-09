"""统一通知入口（ROADMAP R5）。

所有业务代码应通过本模块的 notify() 发送通知，不要直接 INSERT
notifications 表 —— 未来切换到微信订阅消息（或站外推送）实现时，
只需改动本模块这一个适配点，调用方零改动。

现有站内入口 views.create_notification 与本模块签名对齐：
    create_notification(db, user_id, event_id, match_id, type_name, title, message)
"""
import json

# 通知偏好（users.notification_prefs JSON 的键，默认全开）。API 键与存储键一致，
# 一处定义，路由层（notify_routes.py）与过滤层（本模块）共用。
DEFAULT_PREFS = {
    "deadline": True,      # 截止提醒（报名截止前 48h/24h 提醒组织者）
    "draw": True,          # 抽签结果（抽签完成 / 重置）
    "giftReceived": True,  # 晒图提醒（礼物被晒图评价 / 礼物墙解锁）
    "remind": True,        # 催办动态（有人加入活动 / 礼物发货）
}

# 通知 type -> 偏好键。未在此表内的 type 不受偏好过滤（默认投递）。
PREF_BY_TYPE = {
    "deadline_48h": "deadline",
    "deadline_24h": "deadline",
    "draw_result": "draw",
    "draw_redraw": "draw",
    "gift_posted": "giftReceived",
    "gift_wall_unlocked": "giftReceived",
    "participant_joined": "remind",
    "shipment_sent": "remind",
}


def user_notification_prefs(db, user_id):
    """读取用户通知偏好（缺省全开）。

    users.notification_prefs 存 JSON；NULL / 空 / 损坏 / 缺键一律按默认 true
    处理（旧数据与手工改动不会导致通知被静默关闭）。
    """
    prefs = dict(DEFAULT_PREFS)
    row = db.get("SELECT notification_prefs FROM users WHERE id = ?", (user_id,))
    raw = (row or {}).get("notification_prefs")
    if not raw:
        return prefs
    try:
        stored = json.loads(raw)
    except (TypeError, ValueError):
        return prefs
    if not isinstance(stored, dict):
        return prefs
    for key in DEFAULT_PREFS:
        if key in stored:
            prefs[key] = bool(stored[key])
    return prefs


def _pref_enabled(db, user_id, type_name):
    """该用户是否接收此类型通知；未归类类型不拦截。"""
    pref_key = PREF_BY_TYPE.get(type_name)
    if pref_key is None:
        return True
    return user_notification_prefs(db, user_id)[pref_key]


def notify(db, user_id, event_id=None, match_id=None, type_name="", title="", message=""):
    """写入一条站内通知（受用户通知偏好过滤）。

    适配点：未来接入微信订阅消息时，在这里先调用微信模板消息下发、
    再（或改为）写 notifications 表；所有调用方无需改动。

    参数顺序与 views.create_notification 完全一致，可直接替换调用；
    因 event_id/match_id 需要默认值（站级/系统级通知场景），
    type_name/title/message 也给出默认值，但三者必须显式传入，缺省抛 ValueError。

    :param db: DB 实例（wxcloudrun.database.DB）
    :param user_id: 接收通知的用户 id
    :param event_id: 关联活动 id（可空）
    :param match_id: 关联匹配 id（可空）
    :param type_name: 通知类型（如 deadline_48h / deadline_24h）
    :param title: 通知标题
    :param message: 通知正文
    :return: True=已写入；False=被用户通知偏好过滤（未写入）
    """
    if not type_name or not title:
        raise ValueError("notify() requires non-empty type_name and title")
    if not _pref_enabled(db, user_id, type_name):
        return False
    db.execute(
        """
        INSERT INTO notifications (user_id, event_id, match_id, type, title, message)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, event_id, match_id, type_name, title, message),
    )
    return True


def _reminder_sent(db, event_id, type_name):
    """去重：该 event_id + type 是否已发过（一次性提醒）。

    hours 已编码进 type_name（如 deadline_48h / deadline_24h），因此
    (event_id, type_name) 即 (event_id, type, hours) 的唯一键 ——
    48h 与 24h 是不同 type，可各自发一次，互不干扰。
    """
    row = db.get(
        "SELECT id FROM notifications WHERE event_id = ? AND type = ? LIMIT 1",
        (event_id, type_name),
    )
    return row is not None


def notify_deadline_approaching(db, event, hours):
    """给组织者发「报名截止提醒」通知（截止前 48h/24h）。

    :param db: DB 实例
    :param event: events 表一行（dict，须含 id / name / creator_id）
    :param hours: 提前小时数（48 或 24），编码进通知 type
    :return: True=本次新发送；False=已发过（去重跳过）
    """
    type_name = f"deadline_{int(hours)}h"
    if _reminder_sent(db, event["id"], type_name):
        return False
    # 被偏好过滤时不写库、不计数：重新打开偏好后，窗口内重新扫描即可恢复发送
    return notify(
        db,
        event["creator_id"],
        event["id"],
        None,
        type_name,
        "报名即将截止 ⏰",
        f"活动「{event['name']}」将在 {int(hours)} 小时后截止报名，请及时抽签分配礼物！",
    )
