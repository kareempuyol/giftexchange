"""送礼状态机（Luna 独到项）纯函数测试。

验证 gift_routes.shipment_state 的阶段推导：
- 'purchase'：pending 未发货（含无单号 pending 边界）
- 'shipped'：有单号 或 status='shipped'/'delivered' 且未签收
- 'received'：received_at 非空但未晒图（含 review 空串边界）
- 'posted'：gift_review 非空（优先级最高）

wxcloudrun 包 __init__ 在 import 时跑 create_app→init_schema，
因此先用临时 DB 环境变量兜住（与 test_gift_privacy.py 同模式），
并在测试内部懒导入 shipment_state。
"""
import os
import tempfile

import pytest


@pytest.fixture(scope="module", autouse=True)
def _temp_db_env():
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_shipment_state_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-shipment-state"
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()
        yield
    finally:
        if saved_db is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = saved_db
        if saved_jwt is None:
            os.environ.pop("JWT_SECRET", None)
        else:
            os.environ["JWT_SECRET"] = saved_jwt


def state(row=None):
    from wxcloudrun.gift_routes import shipment_state  # 懒导入：env 已就位

    return shipment_state(row or {})


def test_purchase_when_pending_no_tracking():
    assert state({"shipment_status": "pending"}) == "purchase"


def test_purchase_when_empty_row():
    assert state({}) == "purchase"


def test_purchase_when_none_values():
    assert state(
        {"shipment_status": None, "tracking_number": None, "received_at": None, "gift_review": None}
    ) == "purchase"


def test_shipped_when_tracking_number_present_even_status_pending():
    # 边界：status 仍是 pending 但有单号 → 已发货（有单号优先）
    assert state({"shipment_status": "pending", "tracking_number": "SF123"}) == "shipped"


def test_shipped_when_status_shipped():
    assert state({"shipment_status": "shipped", "tracking_number": "SF123"}) == "shipped"


def test_shipped_when_status_shipped_without_tracking():
    assert state({"shipment_status": "shipped", "tracking_number": ""}) == "shipped"


def test_shipped_when_status_delivered():
    # delivered 也是已发货但未签收（received_at 空）→ 仍算 shipped 阶段
    assert state({"shipment_status": "delivered"}) == "shipped"


def test_received_when_received_at_and_no_review():
    assert state({"shipment_status": "shipped", "received_at": "2026-08-09 10:00:00"}) == "received"


def test_received_when_review_is_empty_string():
    # 边界：晒图 PUT 允许空 review → received_at 非空但 review 空串 = 未晒图
    assert state({"received_at": "2026-08-09 10:00:00", "gift_review": ""}) == "received"


def test_posted_when_review_present():
    assert state({"received_at": "2026-08-09 10:00:00", "gift_review": "超喜欢！"}) == "posted"


def test_posted_has_highest_priority():
    # 优先级：已晒图 > 已签收 > 已发货（即使字段冲突也以 review 为准）
    assert state(
        {"shipment_status": "pending", "received_at": "2026-08-09 10:00:00", "gift_review": "赞"}
    ) == "posted"


def test_posted_whitespace_review_counts_as_posted():
    # 非空判断按真值：有内容的 review 才算晒图
    assert state({"gift_review": "nice"}) == "posted"


def test_full_transition_chain():
    # 完整流转：purchase → shipped → received → posted
    row = {"shipment_status": "pending", "tracking_number": "", "received_at": "", "gift_review": ""}
    assert state(row) == "purchase"
    row["tracking_number"] = "YT456"
    assert state(row) == "shipped"
    row["received_at"] = "2026-08-10 09:00:00"
    assert state(row) == "received"
    row["gift_review"] = "礼物太棒了"
    assert state(row) == "posted"
