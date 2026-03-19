from __future__ import annotations

from datetime import datetime


def month_to_int(value: str) -> int:
    """把 YYYY-MM 月份编码成整数，便于窗口和先后关系计算。"""
    # 月份统一映射到整数，避免直接比较字符串时在窗口计算里埋下边界错误。
    return int(value[:4]) * 12 + int(value[5:7])


def month_diff(later: str, earlier: str) -> int:
    """计算两个月份之间相差的月数。"""
    # 基金成立月数、经理任期月数这类金融语义，本质上都是月度差值而不是自然日差值。
    return month_to_int(later) - month_to_int(earlier)


def current_timestamp() -> str:
    """生成 UTC 时间戳，用于数据快照和实验记录。"""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
