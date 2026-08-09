#!/usr/bin/env python3
"""通知表增长控制：删除「已读且创建超过 N 天」的通知（默认 90 天）。

- 未读通知永不删（用户可能还没看）。
- 已读但 90 天内的保留（用户可能想回看）。
- 截止时间在 Python 侧算成 UTC 时间戳字符串再下推参数：
  SQLite 存 "YYYY-MM-DD HH:MM:SS"（CURRENT_TIMESTAMP UTC）、MySQL 存 DATETIME，
  同一字符串参数两端字符串比较语义一致（双引擎通用，符合项目 SQL 约定）。

默认 dry-run：只统计不删除。加 --delete 才真正删除（cron 场景建议先观察一轮）。

用法：
    python3 scripts/cleanup_notifications.py               # 统计可删通知
    python3 scripts/cleanup_notifications.py --delete      # 真正删除
    python3 scripts/cleanup_notifications.py --days 180    # 自定义保留期

cron（建议每周一次）：
    # 每周日 04:00 清理 90 天前已读通知
    0 4 * * 0 cd /path/to/giftexchange && python3 scripts/cleanup_notifications.py --delete >> /var/log/gift_cleanup.log 2>&1

数据库连接沿用应用约定：SQLite 默认 ./data/gift_exchange.db（或 DB_PATH 环境变量），
设置了 MYSQL_ADDRESS/MYSQL_HOST 时自动走 MySQL（wxcloudrun.database.DB 双引擎）。
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wxcloudrun.database import DB  # noqa: E402

DEFAULT_RETENTION_DAYS = 90


def cutoff_ts(days, now=None):
    """返回保留截止的 UTC 时间戳字符串（YYYY-MM-DD HH:MM:SS），早于它的已读通知可删。"""
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def stale_notification_rows(db, days, now=None):
    """返回可删通知的完整行（id / user_id / type / title / read_at / created_at）。"""
    cutoff = cutoff_ts(days, now)
    return db.all(
        "SELECT id, user_id, type, title, read_at, created_at FROM notifications "
        "WHERE read_at IS NOT NULL AND read_at != '' AND created_at IS NOT NULL AND created_at != '' "
        "AND created_at < ? "
        "ORDER BY created_at ASC",
        (cutoff,),
    )


def delete_stale(db, days, now=None):
    """删除已读且超过 days 天的通知，返回删除条数。"""
    rows = stale_notification_rows(db, days, now)
    if not rows:
        return 0
    ids = [row["id"] for row in rows]
    placeholders = ",".join("?" * len(ids))
    cur = db.execute(f"DELETE FROM notifications WHERE id IN ({placeholders})", ids)
    return cur.rowcount


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="清理已读且超过 N 天的通知（默认 dry-run，--delete 才真删）")
    parser.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS, help="已读保留天数（默认 90）")
    parser.add_argument("--delete", action="store_true", help="真正删除；缺省仅统计")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.days < 1:
        print("[cleanup_notifications] --days 必须 >= 1", file=sys.stderr)
        return 2

    with DB() as db:
        rows = stale_notification_rows(db, args.days)
        if args.delete:
            deleted = delete_stale(db, args.days)
            print(f"[cleanup_notifications] 已删除 {deleted} 条已读超过 {args.days} 天的通知")
            return 0
        print(f"[cleanup_notifications] 可删 {len(rows)} 条已读超过 {args.days} 天的通知（--delete 才真删）：")
        for row in rows[:20]:
            print(f"  id={row['id']} user={row['user_id']} type={row['type']} "
                  f"read_at={row['read_at']} created_at={row['created_at']} | {row['title'][:40]}")
        if len(rows) > 20:
            print(f"  … 其余 {len(rows) - 20} 条省略")
    return 0


if __name__ == "__main__":
    sys.exit(main())
