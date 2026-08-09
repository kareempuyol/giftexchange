#!/usr/bin/env python3
"""数据完整性核查：扫描孤儿/悬空引用，只报告不修改。

覆盖（与任务清单一一对应）：
  - 孤儿 matches：event_id 指向不存在的活动；giver_id / receiver_id 指向不存在的参与者
  - 孤儿 participants：event_id 指向不存在的活动；user_id 指向不存在的用户
  - 孤儿 notifications：user_id 指向不存在的用户（另查 event_id / match_id 悬空引用）
  - gift_likes 引用完整性：match_id / user_id 指向不存在的行

退出码：0 = 全部通过；1 = 发现孤儿/悬空数据（供 cron 告警）。绝不修改数据库。

用法：
    python3 scripts/healthcheck_data.py            # 人类可读报告
    python3 scripts/healthcheck_data.py --json    # JSON 输出（含 exit_code 字段）

cron（建议每天一次，发现问题人工介入；修复参考 .audit/OPS_REPORT.md）：
    # 每天 05:00 跑数据完整性核查，发现孤儿数据时给运维发邮件/告警
    0 5 * * * cd /path/to/giftexchange && python3 scripts/healthcheck_data.py >> /var/log/gift_healthcheck.log 2>&1 || echo "healthcheck FAILED" | mail -s "giftexchange 数据完整性告警" ops@example.com

数据库连接沿用应用约定：SQLite 默认 ./data/gift_exchange.db（或 DB_PATH 环境变量），
设置了 MYSQL_ADDRESS/MYSQL_HOST 时自动走 MySQL（wxcloudrun.database.DB 双引擎）。
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wxcloudrun.database import DB  # noqa: E402

# 每项检查：name / 描述 / 返回列的 SELECT（id 列为受影响行主键，detail 列说明归属）
CHECKS = [
    {
        "name": "matches_no_event",
        "desc": "matches 引用不存在的活动（孤儿 matches）",
        "sql": ("SELECT m.id, m.event_id FROM matches m "
                "LEFT JOIN events e ON e.id = m.event_id WHERE e.id IS NULL "
                "ORDER BY m.id"),
        "id": "id",
        "detail": lambda row: f"match_id={row['id']} event_id={row['event_id']}",
    },
    {
        "name": "matches_no_giver",
        "desc": "matches.giver_id 引用不存在的参与者",
        "sql": ("SELECT m.id, m.giver_id FROM matches m "
                "LEFT JOIN participants p ON p.id = m.giver_id WHERE p.id IS NULL "
                "ORDER BY m.id"),
        "id": "id",
        "detail": lambda row: f"match_id={row['id']} giver_id={row['giver_id']}",
    },
    {
        "name": "matches_no_receiver",
        "desc": "matches.receiver_id 引用不存在的参与者",
        "sql": ("SELECT m.id, m.receiver_id FROM matches m "
                "LEFT JOIN participants p ON p.id = m.receiver_id WHERE p.id IS NULL "
                "ORDER BY m.id"),
        "id": "id",
        "detail": lambda row: f"match_id={row['id']} receiver_id={row['receiver_id']}",
    },
    {
        "name": "participants_no_event",
        "desc": "participants 引用不存在的活动（孤儿 participants）",
        "sql": ("SELECT p.id, p.event_id FROM participants p "
                "LEFT JOIN events e ON e.id = p.event_id WHERE e.id IS NULL "
                "ORDER BY p.id"),
        "id": "id",
        "detail": lambda row: f"participant_id={row['id']} event_id={row['event_id']}",
    },
    {
        "name": "participants_no_user",
        "desc": "participants.user_id 引用不存在的用户",
        "sql": ("SELECT p.id, p.user_id FROM participants p "
                "LEFT JOIN users u ON u.id = p.user_id WHERE u.id IS NULL "
                "ORDER BY p.id"),
        "id": "id",
        "detail": lambda row: f"participant_id={row['id']} user_id={row['user_id']}",
    },
    {
        "name": "notifications_no_user",
        "desc": "notifications.user_id 引用不存在的用户（孤儿 notifications）",
        "sql": ("SELECT n.id, n.user_id FROM notifications n "
                "LEFT JOIN users u ON u.id = n.user_id WHERE u.id IS NULL "
                "ORDER BY n.id"),
        "id": "id",
        "detail": lambda row: f"notification_id={row['id']} user_id={row['user_id']}",
    },
    {
        "name": "notifications_no_event",
        "desc": "notifications.event_id 引用不存在的活动（悬空引用）",
        "sql": ("SELECT n.id, n.event_id FROM notifications n "
                "LEFT JOIN events e ON e.id = n.event_id "
                "WHERE n.event_id IS NOT NULL AND e.id IS NULL ORDER BY n.id"),
        "id": "id",
        "detail": lambda row: f"notification_id={row['id']} event_id={row['event_id']}",
    },
    {
        "name": "notifications_no_match",
        "desc": "notifications.match_id 引用不存在的匹配（悬空引用）",
        "sql": ("SELECT n.id, n.match_id FROM notifications n "
                "LEFT JOIN matches m ON m.id = n.match_id "
                "WHERE n.match_id IS NOT NULL AND m.id IS NULL ORDER BY n.id"),
        "id": "id",
        "detail": lambda row: f"notification_id={row['id']} match_id={row['match_id']}",
    },
    {
        "name": "gift_likes_no_match",
        "desc": "gift_likes.match_id 引用不存在的匹配（引用完整性）",
        "sql": ("SELECT gl.id, gl.match_id FROM gift_likes gl "
                "LEFT JOIN matches m ON m.id = gl.match_id WHERE m.id IS NULL "
                "ORDER BY gl.id"),
        "id": "id",
        "detail": lambda row: f"gift_like_id={row['id']} match_id={row['match_id']}",
    },
    {
        "name": "gift_likes_no_user",
        "desc": "gift_likes.user_id 引用不存在的用户（引用完整性）",
        "sql": ("SELECT gl.id, gl.user_id FROM gift_likes gl "
                "LEFT JOIN users u ON u.id = gl.user_id WHERE u.id IS NULL "
                "ORDER BY gl.id"),
        "id": "id",
        "detail": lambda row: f"gift_like_id={row['id']} user_id={row['user_id']}",
    },
]


def run_checks(db):
    """执行全部核查，返回 {name: [rows, ...]}（每项仅含命中行，未命中为空列表）。"""
    results = {}
    for check in CHECKS:
        rows = db.all(check["sql"])
        results[check["name"]] = rows
    return results


def summarize(results):
    """返回 (总问题数, 有问题的检查项数)。"""
    total = sum(len(rows) for rows in results.values())
    failed = sum(1 for rows in results.values() if rows)
    return total, failed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="数据完整性核查（只报告，不修改）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（含 exit_code 字段）")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    with DB() as db:
        results = run_checks(db)
    total, failed = summarize(results)

    if args.json:
        payload = {"checks": {name: [row for row in rows] for name, rows in results.items()},
                   "total_issues": total, "failed_checks": failed, "exit_code": 1 if total else 0}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload["exit_code"]

    if total == 0:
        print(f"[healthcheck] 全部 {len(CHECKS)} 项核查通过，无孤儿/悬空数据")
        return 0
    print(f"[healthcheck] 发现 {total} 条问题，涉及 {failed}/{len(CHECKS)} 项核查：")
    for check in CHECKS:
        rows = results[check["name"]]
        if not rows:
            continue
        print(f"\n  ✗ {check['name']} — {check['desc']}（{len(rows)} 条）")
        for row in rows[:10]:
            print(f"      {check['detail'](row)}")
        if len(rows) > 10:
            print(f"      … 其余 {len(rows) - 10} 条省略（--json 可看全量）")
    print("\n[healthcheck] 只报告不修改；修复建议见 .audit/OPS_REPORT.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())
