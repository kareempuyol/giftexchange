"""抽签核心算法（纯函数，无 Flask/DB 依赖，便于单元测试）。

draw_matches 输入参与者行列表 + 互避对集合，输出一个合法的
送礼环排列（随机环 + 防自抽 + 互避规则），或明确的无解信号。
"""
import secrets


def draw_matches(rows, excluded_pairs):
    """抽签核心：随机环 + 防自抽 + 互避规则。

    返回 (matches, ok)：
    - ok=True 时 matches 是合法排列（list of row dict，每个含 user_id）
    - ok=False 时 matches 为空，表示规则太严无法满足（如 3 人 + 1 互避对）
    """
    n = len(rows)
    if n < 2:
        return [], False
    max_attempts = 200
    for _ in range(max_attempts):
        shuffled = rows[:]
        secrets.SystemRandom().shuffle(shuffled)
        valid = True
        for index, giver in enumerate(shuffled):
            receiver = shuffled[(index + 1) % n]
            if giver["user_id"] == receiver["user_id"]:
                valid = False
                break
            pair_key = (min(giver["user_id"], receiver["user_id"]),
                        max(giver["user_id"], receiver["user_id"]))
            if pair_key in excluded_pairs:
                valid = False
                break
        if valid:
            return shuffled, True
    return [], False


def is_draw_solvable(n, excluded_pairs):
    """预判互避规则是否可能无解（供前端/接口返回友好错误）。

    数学事实：当参与人数 n >= 4 时，任意互避集合理论上都存在合法环；
    n == 3 时若存在任意一个互避对，则无解（三人环任意两人必相邻）。
    n == 2 时无解（两人互送必然成对，且必然互为相邻）。
    """
    if n < 2:
        return False
    if n == 2:
        return False
    if n == 3:
        # 三人环中任意两个成员必为相邻，任一互避对都会破坏所有排列
        return len(excluded_pairs) == 0
    return True
