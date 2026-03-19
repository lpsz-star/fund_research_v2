from __future__ import annotations

from calendar import monthrange
from datetime import datetime


def month_to_int(value: str) -> int:
    """把 YYYY-MM 月份编码成整数，便于窗口和先后关系计算。"""
    # 月份统一映射到整数，避免直接比较字符串时在窗口计算里埋下边界错误。
    return int(value[:4]) * 12 + int(value[5:7])


def month_diff(later: str, earlier: str) -> int:
    """计算两个月份之间相差的月数。"""
    # 基金成立月数、经理任期月数这类金融语义，本质上都是月度差值而不是自然日差值。
    return month_to_int(later) - month_to_int(earlier)


def month_end(value: str) -> str:
    """返回某个月份对应的月末日期字符串。"""
    year = int(value[:4])
    month = int(value[5:7])
    return f"{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}"


def add_months(value: str, offset: int) -> str:
    """对 YYYY-MM 月份做整数月偏移，返回偏移后的月份。"""
    month_index = month_to_int(value) + offset
    year = month_index // 12
    month = month_index % 12
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def iter_months(start_month: str, end_month: str) -> list[str]:
    """生成闭区间 [start_month, end_month] 内的连续月份序列。"""
    if start_month > end_month:
        return []
    months = [start_month]
    current = start_month
    while current < end_month:
        current = add_months(current, 1)
        months.append(current)
    return months


def is_available_by_month_end(available_date: str, signal_month: str) -> bool:
    """判断一条记录在某个信号月月末之前是否已经可见。"""
    # 可得性边界统一收敛为“信号月月末”，避免不同模块各自解释 available_date。
    return available_date <= month_end(signal_month)


def current_timestamp() -> str:
    """生成 UTC 时间戳，用于数据快照和实验记录。"""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
