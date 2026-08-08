"""轻量可观测性：request_id + 结构化 JSON 日志（单实例、零第三方依赖）。

设计要点
--------
- request_id：uuid4 hex 前 12 位，经 contextvars 按请求隔离（单进程多线程安全；
  每个请求线程/上下文独立，后台线程未设置时取默认值 "-"）。
- log_event()：一行 JSON 输出到 stdout（logging 模块，logger 名 "giftexchange"），
  字段含 event / request_id / ts / user_id（可选，自动带）/ 调用方自定义字段。
- 日志失败绝不影响业务：log_event 内部兜底，任何异常静默吞掉。
- 多进程/多实例部署时：request_id 可由网关透传（X-Request-ID 回显已支持），
  日志采集可换外部 sidecar 接管（本模块只负责 stdout 一行 JSON，格式即契约）。
"""
import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timezone

_REQUEST_ID_VAR = contextvars.ContextVar("gift_request_id", default="")
_USER_ID_VAR = contextvars.ContextVar("gift_user_id", default="")

# 结构化日志专用 logger：独立 stdout handler，一行一条 JSON。
# propagate=False 避免与 Flask/Werkzeug 的 stderr 日志重复输出。
logger = logging.getLogger("giftexchange")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def make_request_id():
    """生成 12 位请求 id（uuid4 hex 前 12 位）。"""
    return uuid.uuid4().hex[:12]


def get_request_id():
    """当前请求的 request_id；非请求上下文（后台线程）返回默认空串。"""
    return _REQUEST_ID_VAR.get()


def set_request_id(request_id):
    """设置当前请求的 request_id（before_request 中调用）。"""
    _REQUEST_ID_VAR.set(request_id)


def get_user_id():
    """当前请求关联的 user_id（字符串或空串）；未登录为空。"""
    return _USER_ID_VAR.get()


def set_user_id(user_id):
    """记录当前请求的用户（仅用于日志；before_request 中从 JWT 解析）。"""
    _USER_ID_VAR.set(str(user_id) if user_id is not None else "")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def log_event(event, **fields):
    """结构化日志：一行 JSON 输出到 stdout。

    标准字段：event / request_id / ts；已登录时自动带 user_id。
    调用方可附加任意字段（如 username、event_id、participant_count）。
    内部兜底：JSON 序列化失败或日志异常一律静默，绝不抛到业务层。
    """
    record = {
        "event": event,
        "request_id": get_request_id() or "-",
        "ts": _now_iso(),
    }
    user_id = get_user_id()
    if user_id:
        record["user_id"] = user_id
    record.update({key: value for key, value in fields.items() if value is not None})
    try:
        logger.info(json.dumps(record, ensure_ascii=False, default=str))
    except Exception:
        pass
