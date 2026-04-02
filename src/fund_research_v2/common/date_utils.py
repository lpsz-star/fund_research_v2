from __future__ import annotations

from bisect import bisect_right
from calendar import monthrange
from datetime import date, datetime, timedelta


_TRADE_CALENDAR_INDEX_CACHE: dict[int, dict[str, object]] = {}


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


def month_start(value: str) -> str:
    """返回某个月份对应的月初日期字符串。"""
    # 回测目前只有月频收益，因此任何“执行日”都只能落成月内代理日，统一取月初最容易审计。
    year = int(value[:4])
    month = int(value[5:7])
    return f"{year:04d}-{month:02d}-01"


def add_months(value: str, offset: int) -> str:
    """对 YYYY-MM 月份做整数月偏移，返回偏移后的月份。"""
    month_index = month_to_int(value) + offset
    year = month_index // 12
    month = month_index % 12
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def latest_completed_month(as_of_date: str) -> str:
    """返回 as_of_date 之前最后一个完整结束的月份。"""
    current_month = as_of_date[:7]
    # 研究主链路默认以“完整结束的自然月”作为正式信号月。
    # 只要 as_of_date 还没走到当月月末，就必须回退到上一个月，避免把月内快照误当成正式月末信号。
    if as_of_date < month_end(current_month):
        return add_months(current_month, -1)
    return current_month


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


def decision_date_for_month(month: str, trade_calendar_rows: list[dict[str, object]]) -> str:
    """返回某个估值月对应的决策日，定义为下月第 1 个交易日。"""
    next_month = add_months(month, 1)
    if trade_calendar_rows:
        return first_trading_day_of_month(next_month, trade_calendar_rows)
    # 兼容旧测试和缺失交易日历的场景：至少把决策日明确推到下个月，而不是继续落在信号月月末。
    return month_start(next_month)


def is_available_by_decision_date(available_date: str, month: str, trade_calendar_rows: list[dict[str, object]]) -> bool:
    """判断一条记录是否在该估值月的决策日之前已经可见。"""
    return available_date <= decision_date_for_month(month, trade_calendar_rows)


def current_timestamp() -> str:
    """生成 UTC 时间戳，用于数据快照和实验记录。"""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def first_trading_day_of_month(month: str, trade_calendar_rows: list[dict[str, object]]) -> str:
    """返回某个月的第一个交易日；缺失时抛出异常而不是静默回退。"""
    first_by_month = _trade_calendar_index(trade_calendar_rows)["first_by_month"]
    if month not in first_by_month:
        raise ValueError(f"交易日历中缺少 {month} 的首个交易日。")
    return str(first_by_month[month])


def last_trading_day_of_month(month: str, trade_calendar_rows: list[dict[str, object]]) -> str:
    """返回某个月的最后一个交易日。"""
    last_by_month = _trade_calendar_index(trade_calendar_rows)["last_by_month"]
    if month not in last_by_month:
        raise ValueError(f"交易日历中缺少 {month} 的最后一个交易日。")
    return str(last_by_month[month])


def next_trading_day(current_date: str, trade_calendar_rows: list[dict[str, object]]) -> str:
    """返回给定日期之后的下一个交易日。"""
    open_dates = _trade_calendar_index(trade_calendar_rows)["open_dates"]
    next_index = bisect_right(open_dates, current_date)
    if next_index >= len(open_dates):
        raise ValueError(f"交易日历中缺少 {current_date} 之后的交易日。")
    return str(open_dates[next_index])


def shift_trading_days(current_date: str, offset: int, trade_calendar_rows: list[dict[str, object]]) -> str:
    """从给定日期向后偏移若干个交易日。offset=0 返回原日期（若它是交易日）。"""
    if offset < 0:
        raise ValueError("当前仅支持向后偏移交易日。")
    open_dates = _trade_calendar_index(trade_calendar_rows)["open_dates"]
    if not open_dates:
        raise ValueError("交易日历为空，无法偏移交易日。")
    if offset == 0:
        if current_date in open_dates:
            return current_date
        return next_trading_day(current_date, trade_calendar_rows)
    if current_date in open_dates:
        current_index = open_dates.index(current_date)
    else:
        current_index = bisect_right(open_dates, current_date) - 1
    shifted_index = current_index + offset
    if shifted_index >= len(open_dates):
        raise ValueError(f"交易日历中缺少 {current_date} 向后偏移 {offset} 个交易日的结果。")
    return str(open_dates[shifted_index])


def generate_weekday_trade_calendar(start_date: str, end_date: str, exchange: str = "SSE") -> list[dict[str, object]]:
    """生成仅用于 sample / 测试的工作日交易日历。"""
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    rows: list[dict[str, object]] = []
    previous_open_date = ""
    current = start
    while current <= end:
        open_flag = 1 if current.weekday() < 5 else 0
        rows.append(
            {
                "exchange": exchange,
                "cal_date": current.isoformat(),
                "is_open": open_flag,
                "pretrade_date": previous_open_date,
            }
        )
        if open_flag == 1:
            previous_open_date = current.isoformat()
        current += timedelta(days=1)
    return rows


def _parse_iso_date(value: str) -> date:
    """把 YYYY-MM-DD 字符串解析成 date。"""
    return datetime.strptime(value, "%Y-%m-%d").date()


def _trade_calendar_index(trade_calendar_rows: list[dict[str, object]]) -> dict[str, object]:
    """构建交易日历索引，避免在热点路径中反复全表扫描。"""
    cache_key = id(trade_calendar_rows)
    cached = _TRADE_CALENDAR_INDEX_CACHE.get(cache_key)
    if cached is not None:
        return cached
    open_dates: list[str] = []
    first_by_month: dict[str, str] = {}
    last_by_month: dict[str, str] = {}
    for row in trade_calendar_rows:
        cal_date = str(row.get("cal_date", "")).strip()
        if str(row.get("is_open", "0")) != "1" or not cal_date:
            continue
        open_dates.append(cal_date)
        month = cal_date[:7]
        previous_first = first_by_month.get(month)
        previous_last = last_by_month.get(month)
        if previous_first is None or cal_date < previous_first:
            first_by_month[month] = cal_date
        if previous_last is None or cal_date > previous_last:
            last_by_month[month] = cal_date
    open_dates = sorted(open_dates)
    index = {
        "open_dates": open_dates,
        "first_by_month": first_by_month,
        "last_by_month": last_by_month,
    }
    _TRADE_CALENDAR_INDEX_CACHE[cache_key] = index
    return index
