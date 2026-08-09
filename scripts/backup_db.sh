#!/usr/bin/env bash
# SQLite 数据库备份：WAL 安全备份 + 时间戳命名 + 滚动保留最近 N 份。
#
# 为什么不用 cp：SQLite 处于 WAL 模式时主库文件可能不含最新提交，直接拷文件会丢数据；
# 本脚本优先用 sqlite3 CLI 的 .backup 命令（在线一致性快照），CLI 不存在时回退
# python3 sqlite3 模块的 backup API（同一语义）。
#
# 用法：
#     scripts/backup_db.sh                     # 备份到 ./data/backups/，保留 7 份
#     BACKUP_DIR=/srv/backups BACKUP_KEEP=14 scripts/backup_db.sh
#
# cron（建议每天一次，凌晨低峰）：
#     # 每天 03:00 备份数据库，保留 7 份
#     0 3 * * * /path/to/giftexchange/scripts/backup_db.sh >> /var/log/gift_backup.log 2>&1
#
# MySQL 形态：本脚本只覆盖 SQLite；设置了 MYSQL_ADDRESS/MYSQL_HOST 时直接跳过并提示，
# 请用 mysqldump（见 DEPLOY.md「数据持久化与备份」）。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 默认路径相对仓库根解析，cron 从任意 cwd 调用都正确
DB_PATH="${DB_PATH:-${REPO_ROOT}/data/gift_exchange.db}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/data/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"

if [[ -n "${MYSQL_ADDRESS:-}${MYSQL_HOST:-}" ]]; then
  echo "[backup_db] 检测到 MySQL 模式（MYSQL_ADDRESS/MYSQL_HOST），本脚本仅支持 SQLite；请用 mysqldump 备份。" >&2
  exit 0
fi

if [[ ! -f "${DB_PATH}" ]]; then
  echo "[backup_db] 数据库不存在: ${DB_PATH}，跳过" >&2
  exit 0
fi

mkdir -p "${BACKUP_DIR}"
stamp="$(date +%Y%m%d-%H%M%S)"
dest="${BACKUP_DIR}/gift_exchange-${stamp}.db"
tmp="${dest}.tmp"

backup_ok=0
if command -v sqlite3 >/dev/null 2>&1; then
  if sqlite3 "${DB_PATH}" ".backup '${tmp}'" 2>/dev/null; then
    backup_ok=1
  else
    echo "[backup_db] sqlite3 .backup 失败，尝试 python3 回退" >&2
  fi
fi

if [[ "${backup_ok}" -ne 1 ]]; then
  python3 - "${DB_PATH}" "${tmp}" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
src_conn = sqlite3.connect(src)
dst_conn = sqlite3.connect(dst)
try:
    src_conn.backup(dst_conn)
finally:
    dst_conn.close()
    src_conn.close()
PY
fi

mv "${tmp}" "${dest}"
echo "[backup_db] 已备份: ${dest}"

# 滚动清理：按文件名（时间戳）排序，只保留最新的 BACKUP_KEEP 份
# （macOS 自带 bash 3.2 无 mapfile，用可移植循环收集）
backups=()
while IFS= read -r f; do backups+=("$f"); done < <(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'gift_exchange-*.db' | sort)
prune=$(( ${#backups[@]} - BACKUP_KEEP ))
if [[ "${prune}" -gt 0 ]]; then
  for old in "${backups[@]:0:${prune}}"; do
    rm -f "${old}"
    echo "[backup_db] 清理旧备份: ${old}"
  done
fi
echo "[backup_db] 完成，当前备份 $(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'gift_exchange-*.db' | wc -l | tr -d ' ')/${BACKUP_KEEP} 份"
