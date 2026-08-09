#!/usr/bin/env python3
"""孤儿上传文件清理：删除 uploads 目录下无任何 DB 引用、且落盘超过 N 天的文件。

安全规则（三重保险，缺一不删）：
  1. 只扫描 uploads 目录下的**普通文件**（不递归、不碰子目录/符号链接外的文件）；
  2. 文件必须已存在超过 --min-age-days 天（默认 7 天，防「刚上传还没写库」的误删窗口）；
     **7 天是硬性下限**：传小于 7 的值直接报错退出，任何调用方（含测试）都不能低于该值；
  3. 文件名的任何一部分都不被 DB 引用列（见 REFERENCE_COLUMNS）引用——引用以
     `/uploads/<filename>` 相对 URL 或带 host 的完整 URL 形式存储。

默认 dry-run：只列出候选文件，不删除。加 --delete 才真正删除。

用法：
    python3 scripts/cleanup_orphans.py                 # 列出可删文件
    python3 scripts/cleanup_orphans.py --delete        # 真正删除
    python3 scripts/cleanup_orphans.py --dir /srv/uploads --min-age-days 3

cron（建议每天一次，先 dry-run 观察一轮再上 --delete）：
    # 每天 04:30 清理孤儿上传文件（保留 7 天引用窗口）
    30 4 * * * cd /path/to/giftexchange && python3 scripts/cleanup_orphans.py --delete >> /var/log/gift_cleanup.log 2>&1

数据库连接沿用应用约定：SQLite 默认 ./data/gift_exchange.db（或 DB_PATH 环境变量），
设置了 MYSQL_ADDRESS/MYSQL_HOST 时自动走 MySQL（wxcloudrun.database.DB 双引擎）。
"""
import argparse
import os
import sys
import time
from pathlib import Path

# 允许从任意 cwd 直接运行（cron 场景）：把仓库根目录挂进 sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wxcloudrun.database import DB  # noqa: E402

# 引用上传文件的 DB 列（URL 形如 /uploads/<uuid>.png）。新增图片字段时必须同步维护此处，
# 否则被新字段引用的文件会被误判为孤儿删除。
REFERENCE_COLUMNS = [
    ("users", "avatar_url"),
    ("events", "cover_image"),
    ("matches", "gift_photo_url"),
]

MIN_AGE_SECONDS = 7 * 24 * 3600


def referenced_filenames(db):
    """收集 DB 中所有被引用的上传文件名（含相对 URL 与带 host 的完整 URL 两种形态）。"""
    names = set()
    for table, column in REFERENCE_COLUMNS:
        rows = db.all(f"SELECT {column} AS ref FROM {table} WHERE {column} IS NOT NULL AND {column} != ''")
        for row in rows:
            url = str(row["ref"]).strip()
            # 旧 base64（data: 开头）不引用文件；其余按 URL 取最后一段作为文件名
            if url.startswith("data:"):
                continue
            name = url.rstrip("/").rsplit("/", 1)[-1]
            if name and "/" not in name:
                names.add(name)
    return names


def scan_orphans(db, upload_dir, min_age_seconds=MIN_AGE_SECONDS, now=None):
    """扫描 uploads 目录，返回孤儿文件路径列表（[path, ...]）。

    :param upload_dir: 上传目录（默认 helpers.uploads_dir() 语义）
    :param min_age_seconds: 文件需存在超过该秒数才算候选（防误删刚上传未写库的文件）；
        低于 MIN_AGE_SECONDS 的值会被钳制到 MIN_AGE_SECONDS（7 天硬性下限）
    :param now: 可选基准时间（epoch 秒，便于测试）；默认取当前时间
    """
    now = now if now is not None else time.time()
    min_age_seconds = max(min_age_seconds, MIN_AGE_SECONDS)
    referenced = referenced_filenames(db)
    orphans = []
    try:
        entries = sorted(os.listdir(upload_dir))
    except FileNotFoundError:
        return orphans
    for entry in entries:
        path = os.path.join(upload_dir, entry)
        if not os.path.isfile(path):
            continue  # 只清普通文件，不碰子目录（如 storage 预留的 uploads/uploads/ 形态）
        if entry in referenced:
            continue
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age < min_age_seconds:
            continue
        orphans.append(path)
    return orphans


def delete_files(paths):
    """物理删除文件；逐个 try/except，单个失败不中断整体。返回成功删除数。"""
    deleted = 0
    for path in paths:
        try:
            os.remove(path)
            deleted += 1
        except OSError as exc:
            print(f"  [skip] 删除失败 {path}: {exc}", file=sys.stderr)
    return deleted


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="清理 uploads 目录下无 DB 引用的孤儿文件（默认 dry-run）")
    parser.add_argument("--dir", default=None, help="上传目录（默认取应用 uploads_dir()）")
    parser.add_argument("--min-age-days", type=int, default=7, help="文件存在超过 N 天才候选（默认 7）")
    parser.add_argument("--delete", action="store_true", help="真正删除；缺省仅列出候选")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    def _default_upload_dir():
        from wxcloudrun.helpers import uploads_dir  # noqa: E402  # 延迟导入：避免脚本 --help 也要建目录

        return uploads_dir()

    upload_dir = args.dir or _default_upload_dir()
    if args.min_age_days < 7:
        print(f"[cleanup_orphans] --min-age-days 不能小于 7（硬性安全下限）: {args.min_age_days}", file=sys.stderr)
        return 2
    min_age_seconds = args.min_age_days * 24 * 3600

    with DB() as db:
        orphans = scan_orphans(db, upload_dir, min_age_seconds=min_age_seconds)

    if not orphans:
        print(f"[cleanup_orphans] 无孤儿文件（目录 {upload_dir}，引用窗口 {args.min_age_days} 天）")
        return 0

    total_bytes = 0
    for path in orphans:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        total_bytes += size
        age_days = (time.time() - os.path.getmtime(path)) / 86400 if os.path.exists(path) else 0
        print(f"  {path}  ({size} bytes, {age_days:.1f} 天前)")
    print(f"[cleanup_orphans] 候选 {len(orphans)} 个文件，合计 {total_bytes} bytes"
          f"{'；--delete 将删除' if not args.delete else '；已删除'}")

    if args.delete:
        deleted = delete_files(orphans)
        print(f"[cleanup_orphans] 已删除 {deleted}/{len(orphans)} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
