"""轻量版本化迁移（双引擎：MySQL + SQLite）。

裁决背景（ROADMAP 迁移管理）：2/3 模型支持引 Alembic，1/3 反对；本项目双引擎——
MySQL+SQLite——Alembic 迁移脚本要写双方言，成本高收益低。裁决：不引 Alembic，
做轻量版本化迁移：MIGRATIONS 声明式列表 + schema_migrations 记录表 + _column_exists
幂等守卫（旧库已加过的列重跑不报 duplicate column）。

如何新增未来迁移：
  1. 在 MIGRATIONS 末尾 append 一项：{'version': <当前最大版本+1>, 'name': '...', 'up': [...]}
  2. up 里的每个元素（二选一）：
     - _add_column('表名', '列名', mysql='MySQL 类型', sqlite='SQLite 类型')
       —— 执行前自动做 _column_exists 检查，双引擎类型分离，MySQL 不必写 SQLite 语法
     - _create_table(mysql='MySQL 建表 SQL', sqlite='SQLite 建表 SQL')
       —— CREATE TABLE IF NOT EXISTS 双方言（MySQL 需 ENGINE=InnoDB 子句）
  3. 服务下次启动 init_schema → run_migrations → run_migrations_v2 自动应用并记录。
     也可在测试/脚本里直接调 wxcloudrun.migrations.run_migrations_v2(db)。
"""
from datetime import datetime, timezone


def _engine_sql(db, mysql, sqlite):
    return mysql if db.engine == "mysql" else sqlite


def _column_exists(db, table, column):
    """幂等迁移辅助：检查列是否已存在（MySQL 走 information_schema，SQLite 走 pragma_table_info）。"""
    if db.engine == "mysql":
        row = db.get(
            "SELECT COUNT(*) AS count FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?",
            (table, column),
        )
    else:
        row = db.get("SELECT COUNT(*) AS count FROM pragma_table_info(?) WHERE name = ?", (table, column))
    return int(row["count"] or 0) > 0


def _add_column(table, column, mysql, sqlite):
    """声明式加列描述符：执行前自动 _column_exists 检查，双引擎类型分离。"""
    return {"op": "add_column", "table": table, "column": column, "mysql": mysql, "sqlite": sqlite}


def _create_index(name, table, columns):
    """声明式建索引描述符：CREATE INDEX IF NOT EXISTS（MySQL 8+ / SQLite 同语法；
    MySQL 5.7 无 IF NOT EXISTS，由执行前的 _index_exists 守卫保证幂等）。"""
    return {
        "op": "create_index",
        "index": name,
        "table": table,
        "sql": f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({', '.join(columns)})",
    }


def _index_exists(db, name, table=None):
    """幂等迁移辅助：索引是否已存在（MySQL 走 information_schema，SQLite 走 sqlite_master）。

    传入 table 时按表限定（MySQL 索引名仅表内唯一，跨表同名会误判为已存在而跳过建索引）。
    """
    if db.engine == "mysql":
        sql = (
            "SELECT COUNT(*) AS count FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND index_name = ?"
        )
        params = [name]
        if table:
            sql += " AND table_name = ?"
            params.append(table)
        row = db.get(sql, tuple(params))
    else:
        sql = "SELECT COUNT(*) AS count FROM sqlite_master WHERE type = 'index' AND name = ?"
        params = [name]
        if table:
            sql += " AND tbl_name = ?"
            params.append(table)
        row = db.get(sql, tuple(params))
    return int(row["count"] or 0) > 0


def _create_table(mysql, sqlite):
    """声明式建表描述符：CREATE TABLE IF NOT EXISTS 双方言。"""
    return {"op": "create_table", "mysql": mysql, "sqlite": sqlite}


# 历史迁移（版本 1-6，与旧 run_migrations 的 ALTER 一一对应；后续迁移请 append 版本号 +1）
MIGRATIONS = [
    {
        "version": 1,
        "name": "events.short_code 邀请短码（阶段二A）",
        "up": [
            _add_column("events", "short_code", mysql="VARCHAR(16)", sqlite="TEXT"),
        ],
    },
    {
        "version": 2,
        "name": "events.excluded_pairs 抽签互避规则（阶段二C）",
        "up": [
            _add_column("events", "excluded_pairs", mysql="TEXT", sqlite="TEXT"),
        ],
    },
    {
        "version": 3,
        "name": "participants.preference_likes/dislikes/notes 报名心愿单结构化（阶段二B）",
        "up": [
            _add_column("participants", "preference_likes", mysql="TEXT", sqlite="TEXT"),
            _add_column("participants", "preference_dislikes", mysql="TEXT", sqlite="TEXT"),
            _add_column("participants", "preference_notes", mysql="TEXT", sqlite="TEXT"),
        ],
    },
    {
        "version": 4,
        "name": "gift_likes 礼物墙点赞表（阶段二E）",
        "up": [
            _create_table(
                mysql="""
                CREATE TABLE IF NOT EXISTS gift_likes (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  match_id INT NOT NULL,
                  user_id INT NOT NULL,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uniq_like_match_user (match_id, user_id),
                  INDEX idx_likes_match (match_id),
                  INDEX idx_likes_user (user_id),
                  CONSTRAINT fk_likes_match FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
                  CONSTRAINT fk_likes_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                sqlite="""
                CREATE TABLE IF NOT EXISTS gift_likes (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(match_id, user_id)
                )
                """,
            ),
        ],
    },
    {
        "version": 5,
        "name": "users.openid/unionid/session_key 微信字段预留（阶段二G）",
        "up": [
            _add_column("users", "openid", mysql="VARCHAR(64)", sqlite="TEXT"),
            _add_column("users", "unionid", mysql="VARCHAR(64)", sqlite="TEXT"),
            _add_column("users", "session_key", mysql="VARCHAR(64)", sqlite="TEXT"),
        ],
    },
    {
        "version": 6,
        "name": "matches.gift_privacy 晒图隐私三模式（第三批）",
        "up": [
            _add_column("matches", "gift_privacy", mysql="VARCHAR(24) DEFAULT 'photo'", sqlite="TEXT DEFAULT 'photo'"),
        ],
    },
    {
        "version": 7,
        "name": "users.reset_code/reset_code_expires_at 找回密码数字码（P0 忘记密码）",
        "up": [
            _add_column("users", "reset_code", mysql="VARCHAR(6)", sqlite="TEXT"),
            _add_column("users", "reset_code_expires_at", mysql="DATETIME", sqlite="TEXT"),
        ],
    },
    {
        "version": 8,
        "name": "users.notification_prefs 通知偏好 JSON（通知批量管理）",
        "up": [
            _add_column("users", "notification_prefs", mysql="TEXT", sqlite="TEXT"),
        ],
    },
    {
        "version": 9,
        "name": "users.deactivated 账号注销标记（P0 注销，本任务独占）",
        "up": [
            _add_column("users", "deactivated", mysql="TINYINT DEFAULT 0", sqlite="INTEGER DEFAULT 0"),
        ],
    },
    {
        "version": 10,
        "name": "events.archived 活动归档标记（P0 归档，本任务独占）",
        "up": [
            _add_column("events", "archived", mysql="TINYINT DEFAULT 0", sqlite="INTEGER DEFAULT 0"),
        ],
    },
    {
        "version": 11,
        "name": "性能索引：events/participants/matches/notifications/gift_likes 高频查询列",
        "up": [
            _create_index("idx_events_short_code", "events", ["short_code"]),
            _create_index("idx_events_creator_archived", "events", ["creator_id", "archived"]),
            _create_index("idx_events_status_public_archived", "events", ["status", "is_public", "archived"]),
            _create_index("idx_participants_user", "participants", ["user_id"]),
            _create_index("idx_matches_event", "matches", ["event_id"]),
            _create_index("idx_matches_giver", "matches", ["giver_id"]),
            _create_index("idx_matches_receiver", "matches", ["receiver_id"]),
            _create_index("idx_notifications_user_created", "notifications", ["user_id", "created_at"]),
            _create_index("idx_notifications_user_read", "notifications", ["user_id", "read_at"]),
            _create_index("idx_gift_likes_user", "gift_likes", ["user_id"]),
        ],
    },
]


def run_migrations_v2(db):
    """轻量版本化迁移入口：创建 schema_migrations 记录表，逐条应用未记录的迁移。

    - 每个 ALTER 带 _column_exists 幂等守卫：旧库（旧 run_migrations 已加过列）重跑不报
      duplicate column；CREATE TABLE 均带 IF NOT EXISTS。
    - 迁移全部语句成功后才写入 schema_migrations；中途失败则本次不记录，下次启动重试
      （语句本身幂等，已生效的部分会被守卫跳过）。
    - applied_at 用 Python 侧 UTC 时间，避免 SQLite datetime('now') / MySQL NOW() 方言差异。
    返回本次新应用的迁移数。
    """
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT)"
    )
    applied = 0
    for migration in sorted(MIGRATIONS, key=lambda m: m["version"]):
        version = migration["version"]
        row = db.get("SELECT version FROM schema_migrations WHERE version = ?", (version,))
        if row:
            continue
        for statement in migration["up"]:
            op = statement["op"]
            if op == "add_column":
                if not _column_exists(db, statement["table"], statement["column"]):
                    db.execute(
                        f"ALTER TABLE {statement['table']} ADD COLUMN {statement['column']} "
                        + _engine_sql(db, statement["mysql"], statement["sqlite"])
                    )
            elif op == "create_table":
                db.execute(_engine_sql(db, statement["mysql"], statement["sqlite"]))
            elif op == "create_index":
                if not _index_exists(db, statement["index"], statement["table"]):
                    db.execute(statement["sql"])
            else:
                raise ValueError(f"未知迁移语句类型: {op!r}（MIGRATIONS 版本 {version}）")
        db.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, migration["name"], datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        applied += 1
    return applied
