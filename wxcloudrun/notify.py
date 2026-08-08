"""统一通知入口（ROADMAP R5）。

所有业务代码应通过本模块的 notify() 发送通知，不要直接 INSERT
notifications 表 —— 未来切换到微信订阅消息（或站外推送）实现时，
只需改动本模块这一个适配点，调用方零改动。

现有站内入口 views.create_notification 与本模块签名对齐：
    create_notification(db, user_id, event_id, match_id, type_name, title, message)
"""


def notify(db, user_id, event_id=None, match_id=None, type_name="", title="", message=""):
    """写入一条站内通知。

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
    """
    if not type_name or not title:
        raise ValueError("notify() requires non-empty type_name and title")
    db.execute(
        """
        INSERT INTO notifications (user_id, event_id, match_id, type, title, message)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, event_id, match_id, type_name, title, message),
    )


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
    notify(
        db,
        event["creator_id"],
        event["id"],
        None,
        type_name,
        "报名即将截止 ⏰",
        f"活动「{event['name']}」将在 {int(hours)} 小时后截止报名，请及时抽签分配礼物！",
    )
    return True
