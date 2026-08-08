"""定时任务（ROADMAP R5）：活动报名截止提醒。

直接运行（手动扫一次，本地 dev 库）：
    python3 -m wxcloudrun.jobs

未来接入建议：
    - 本地/单机：Flask 启动后起一个后台守护线程，每小时调用一次 scan_deadlines()
    - 云端：微信云托管定时触发器 / cron / APScheduler 调用 scan_deadlines()
    scan_deadlines 内部自带去重（同一活动同一档位只发一次），重复调度安全。
"""
from datetime import datetime, timedelta, timezone

from wxcloudrun.database import DB, init_schema
from wxcloudrun.notify import notify_deadline_approaching

# 提前提醒的时间点（小时）。每个档位对同一活动只发一次（notify 内部去重）。
REMINDER_HOURS = (48, 24)


def parse_deadline(value):
    """解析 sign_up_deadline 字符串 → aware datetime；无法解析返回 None。

    兼容仓库现存三种存储格式：
      - ISO 带时区（前端 new Date().toISOString()）：2026-08-10T12:00:00.000Z
      - 无时区 datetime（datetime-local 输入）：2026-12-25T20:00 → 按 UTC 处理
      - 纯日期：2026-12-25 → 按当天 23:59:59 UTC 处理（截止到当天结束）
    """
    if not value:
        return None
    value = str(value).strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # 纯日期（无时间部分）按当天 23:59:59 处理：截止到当天结束
    if not any(sep in value for sep in ("T", "t", " ")):
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt


def scan_deadlines(db=None, now=None):
    """扫描 status='open' 且 sign_up_deadline 即将到期（48h/24h 内）的活动，
    给组织者发截止提醒通知（调用 notify.py，内部自带去重）。

    触发窗口（避免每轮扫描重复触发 + 保证文案准确）：
      - 剩余 (24h, 48h]   → deadline_48h 提醒
      - 剩余 (0h, 24h]    → deadline_24h 提醒
      - 剩余 >48h 或已过期 → 不提醒

    :param db: 可选 DB 实例；不传则自行打开/关闭（with 块负责 commit）
    :param now: 可选基准时间（便于测试）；默认 UTC 当前时间
    :return: 本次新发送的通知条数
    """
    if db is None:
        with DB() as db:
            return _scan(db, now)
    return _scan(db, now)


def _scan(db, now):
    now = now or datetime.now(timezone.utc)
    events = db.all(
        "SELECT id, name, creator_id, status, sign_up_deadline FROM events "
        "WHERE status = 'open' AND sign_up_deadline IS NOT NULL AND sign_up_deadline != ''"
    )
    sent = 0
    for event in events:
        deadline = parse_deadline(event["sign_up_deadline"])
        if deadline is None:
            continue
        remaining = deadline - now
        for hours in REMINDER_HOURS:
            window = timedelta(hours=hours)
            prev = timedelta(hours=hours - 24)  # 48h 档在 (24h,48h] 触发；24h 档在 (0h,24h] 触发
            if prev < remaining <= window and notify_deadline_approaching(db, event, hours):
                sent += 1
    return sent


if __name__ == "__main__":
    init_schema()
    with DB() as db:
        sent = _scan(db, datetime.now(timezone.utc))
    print(f"[jobs] deadline scan done: {sent} new notification(s) sent")
