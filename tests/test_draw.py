"""抽签核心算法单元测试（wxcloudrun/draw.py）"""
import pytest

from wxcloudrun.draw import draw_matches, is_draw_solvable


def make_rows(n, prefix="u"):
    """构造 n 个参与者行（含 user_id）"""
    return [{"user_id": f"{prefix}{i}", "id": i} for i in range(1, n + 1)]


def assert_valid_ring(matches, n, excluded_pairs):
    """验证排列是合法送礼环：恰好 n 个、每人不自送、不违反互避"""
    assert len(matches) == n
    givers = {m["user_id"] for m in matches}
    assert len(givers) == n, "giver 重复"
    receivers = {matches[(i + 1) % n]["user_id"] for i in range(n)}
    assert receivers == givers, "接收者集合必须等于送礼者集合（环）"
    for i, giver in enumerate(matches):
        receiver = matches[(i + 1) % n]
        assert giver["user_id"] != receiver["user_id"], "不能自送"
        pair = (min(giver["user_id"], receiver["user_id"]),
                max(giver["user_id"], receiver["user_id"]))
        assert pair not in excluded_pairs, f"违反互避: {pair}"


class TestDrawBasic:
    def test_two_people(self):
        matches, ok = draw_matches(make_rows(2), set())
        assert ok is True
        assert_valid_ring(matches, 2, set())

    def test_three_people(self):
        matches, ok = draw_matches(make_rows(3), set())
        assert ok is True
        assert_valid_ring(matches, 3, set())

    def test_ten_people(self):
        matches, ok = draw_matches(make_rows(10), set())
        assert ok is True
        assert_valid_ring(matches, 10, set())

    def test_less_than_two(self):
        matches, ok = draw_matches(make_rows(1), set())
        assert ok is False
        assert matches == []
        matches, ok = draw_matches([], set())
        assert ok is False

    def test_does_not_mutate_input(self):
        rows = make_rows(5)
        before = [r["user_id"] for r in rows]
        draw_matches(rows, set())
        assert [r["user_id"] for r in rows] == before, "不能修改输入列表"


class TestExcludedPairs:
    def test_single_excluded_pair(self):
        rows = make_rows(4)
        excluded = {("u1", "u2")}
        matches, ok = draw_matches(rows, excluded)
        assert ok is True
        assert_valid_ring(matches, 4, excluded)

    def test_all_excluded_pair(self):
        # 4 人全互避：任意两人都不能相邻 → 无解
        rows = make_rows(4)
        excluded = {("u1", "u2"), ("u1", "u3"), ("u1", "u4"),
                    ("u2", "u3"), ("u2", "u4"), ("u3", "u4")}
        matches, ok = draw_matches(rows, excluded)
        assert ok is False
        assert matches == []

    def test_dense_exclusion_four(self):
        # 4 人 5 个互避对：多数排列被破坏，仍可能有解（最多需 200 次重试）
        rows = make_rows(4)
        excluded = {("u1", "u2"), ("u1", "u3"), ("u1", "u4"),
                    ("u2", "u3"), ("u2", "u4")}
        matches, ok = draw_matches(rows, excluded)
        # 允许有解或无解，但无解时必须是空列表（不返回非法结果）
        if ok:
            assert_valid_ring(matches, 4, excluded)
        else:
            assert matches == []

    def test_three_with_exclusion_is_impossible(self):
        # 3 人 + 1 互避对：数学上无解
        rows = make_rows(3)
        excluded = {("u1", "u2")}
        matches, ok = draw_matches(rows, excluded)
        assert ok is False
        assert matches == []

    def test_normalized_pair_key(self):
        # 互避对传入顺序无关（(u2,u1) 等价于 (u1,u2)）
        rows = make_rows(4)
        excluded = {("u2", "u1")}
        matches, ok = draw_matches(rows, excluded)
        assert ok is True
        assert_valid_ring(matches, 4, {("u1", "u2")})


class TestSolvability:
    def test_impossible_cases(self):
        assert is_draw_solvable(1, set()) is False
        assert is_draw_solvable(0, set()) is False
        assert is_draw_solvable(2, set()) is False
        assert is_draw_solvable(3, {("a", "b")}) is False

    def test_possible_cases(self):
        assert is_draw_solvable(3, set()) is True
        assert is_draw_solvable(4, {("a", "b")}) is True
        assert is_draw_solvable(10, {("a", "b"), ("c", "d")}) is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
