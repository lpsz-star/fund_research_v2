from __future__ import annotations

from collections import defaultdict
from math import sqrt

from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.contracts import DatasetSnapshot, UniverseSnapshot
from fund_research_v2.common.date_utils import is_available_by_month_end, month_diff


def build_feature_rows(config: AppConfig, dataset: DatasetSnapshot, universe: UniverseSnapshot) -> list[dict[str, object]]:
    """按基金实体和月份构建特征表。"""
    entity_lookup = {str(row["entity_id"]): row for row in dataset.fund_entity_master}
    manager_lookup = {(str(row["entity_id"]), str(row["month"])): row for row in dataset.manager_assignment_monthly}
    eligibility = {(str(row["entity_id"]), str(row["month"])): int(row["is_eligible"]) for row in universe.rows}
    nav_by_entity: dict[str, list[dict[str, object]]] = defaultdict(list)
    benchmark_rows = sorted(dataset.benchmark_monthly, key=lambda item: str(item["month"]))
    for row in dataset.fund_nav_monthly:
        nav_by_entity[str(row["entity_id"])].append(row)
    feature_rows = []
    for entity_id, nav_rows in nav_by_entity.items():
        nav_rows = sorted(nav_rows, key=lambda item: str(item["month"]))
        entity = entity_lookup[entity_id]
        raw_months = [str(row["month"]) for row in nav_rows]
        for month in raw_months:
            visible_rows = [row for row in nav_rows if str(row["month"]) <= month and is_available_by_month_end(str(row["available_date"]), month)]
            if not visible_rows:
                continue
            current_visible_row = next((row for row in visible_rows if str(row["month"]) == month), None)
            if current_visible_row is None:
                # 若当月净值在月末前尚不可见，则该月不能形成合法信号，也不应生成特征行。
                continue
            # 所有滚动窗口都基于“截至当月末已可见”的历史序列，而不是事后补全后的完整历史。
            returns = [float(row["return_1m"]) for row in visible_rows]
            navs = [float(row["nav"]) for row in visible_rows]
            assets = [float(row["assets_cny_mn"]) for row in visible_rows]
            months = [str(row["month"]) for row in visible_rows]
            index = len(months) - 1
            benchmark_lookup = _visible_benchmark_lookup(benchmark_rows, month)
            # 特征只用当月及历史窗口数据构造，避免把未来月份收益泄漏到当前信号。
            feature_rows.append(
                {
                    "entity_id": entity_id,
                    "month": month,
                    "is_eligible": eligibility[(entity_id, month)],
                    "entity_name": entity["entity_name"],
                    "fund_company": entity["fund_company"],
                    "primary_type": entity["primary_type"],
                    "manager_name": _manager_name_for_month(entity, manager_lookup.get((entity_id, month))),
                    "ret_3m": _window_total_return(returns, index, 3),
                    "ret_6m": _window_total_return(returns, index, 6),
                    "ret_12m": _window_total_return(returns, index, 12),
                    # excess_ret_12m 保留 benchmark 接口，即使当前 benchmark 还是代理值，也能固定未来的字段契约。
                    "excess_ret_12m": round(_window_total_return(returns, index, 12) - _window_total_return_from_scalar(benchmark_lookup, months, index, 12), 6),
                    "vol_12m": _window_volatility(returns, index, 12),
                    "downside_vol_12m": _window_downside_volatility(returns, index, 12),
                    "max_drawdown_12m": _window_max_drawdown(navs, index, 12),
                    "manager_tenure_months": _manager_tenure_months(entity, month, manager_lookup.get((entity_id, month))),
                    "asset_stability_12m": _window_asset_stability(assets, index, 12),
                }
            )
    return feature_rows


def _window_slice(values: list[float], end_index: int, window: int) -> list[float]:
    """截取截至当前月份的滚动窗口。"""
    start = max(0, end_index - window + 1)
    return values[start : end_index + 1]


def _manager_name_for_month(entity: dict[str, object], manager_row: dict[str, object] | None) -> str:
    """返回某个月份应使用的经理名称。"""
    if manager_row is not None and str(manager_row.get("manager_name") or "").strip():
        return str(manager_row["manager_name"])
    return str(entity.get("manager_name") or "unknown")


def _manager_tenure_months(entity: dict[str, object], month: str, manager_row: dict[str, object] | None = None) -> int:
    """计算当前月份下的真实经理任期月数，并在异常情况下安全回退。"""
    manager_start_month = _safe_month_or_none((manager_row or {}).get("manager_start_month"))
    if manager_start_month is None:
        manager_start_month = _safe_month_or_none(entity.get("manager_start_month"))
    inception_month = _safe_month_or_none(entity.get("inception_month"))

    # 优先使用真实经理任职起始月；如果缺失或异常，再回退到基金成立月，至少保证口径可计算。
    anchor_month = manager_start_month or inception_month or month

    # 若经理起始月晚于当前观察月，通常意味着数据缺失、映射错误或样本期内尚未上任，不能算成负任期。
    if month_diff(month, anchor_month) < 0:
        fallback_anchor = inception_month or month
        if month_diff(month, fallback_anchor) < 0:
            return 0
        return month_diff(month, fallback_anchor) + 1
    return month_diff(month, anchor_month) + 1


def _safe_month_or_none(raw: object) -> str | None:
    """把原始月份值校验为 YYYY-MM，异常值返回 None。"""
    value = str(raw or "").strip()
    if len(value) != 7 or value[4] != "-":
        return None
    year = value[:4]
    month = value[5:7]
    if not year.isdigit() or not month.isdigit():
        return None
    if not 1 <= int(month) <= 12:
        return None
    return value


def _window_total_return(values: list[float], end_index: int, window: int) -> float:
    """计算滚动窗口内的复利累计收益。"""
    # 收益窗口使用复利连乘，而不是简单求和，否则长窗口收益会系统性偏差。
    result = 1.0
    for value in _window_slice(values, end_index, window):
        result *= 1 + value
    return round(result - 1.0, 6)


def _window_total_return_from_scalar(benchmark_lookup: dict[str, float], months: list[str], end_index: int, window: int) -> float:
    """根据 benchmark 月收益序列计算对应窗口的累计收益。"""
    result = 1.0
    for month in months[max(0, end_index - window + 1) : end_index + 1]:
        result *= 1 + benchmark_lookup.get(month, 0.0)
    return round(result - 1.0, 6)


def _visible_benchmark_lookup(benchmark_rows: list[dict[str, object]], signal_month: str) -> dict[str, float]:
    """构建截至某个信号月末实际可见的 benchmark 月收益映射。"""
    visible_lookup: dict[str, float] = {}
    for row in benchmark_rows:
        month = str(row["month"])
        available_date = _benchmark_available_date(row)
        if month <= signal_month and is_available_by_month_end(available_date, signal_month):
            visible_lookup[month] = float(row["benchmark_return_1m"])
    return visible_lookup


def _benchmark_available_date(row: dict[str, object]) -> str:
    """推断 benchmark 月收益的可见日期，兼容旧缓存缺少该字段的情况。"""
    explicit_date = str(row.get("available_date") or "").strip()
    if explicit_date:
        return explicit_date
    trade_date = str(row.get("benchmark_trade_date") or "").strip()
    if trade_date:
        return trade_date
    return f"{str(row['month'])}-28"


def _window_volatility(values: list[float], end_index: int, window: int) -> float:
    """计算窗口内月收益波动率。"""
    subset = _window_slice(values, end_index, window)
    # 这里先用最朴素的总体波动口径，目的是提供可解释基线；后续如需年化或去偏可以单独演进。
    mean = sum(subset) / len(subset)
    variance = sum((value - mean) ** 2 for value in subset) / len(subset)
    return round(sqrt(variance), 6)


def _window_downside_volatility(values: list[float], end_index: int, window: int) -> float:
    """计算窗口内负收益部分的下行波动率。"""
    subset = [value for value in _window_slice(values, end_index, window) if value < 0]
    if not subset:
        return 0.0
    variance = sum(value**2 for value in subset) / len(subset)
    return round(sqrt(variance), 6)


def _window_max_drawdown(navs: list[float], end_index: int, window: int) -> float:
    """基于净值路径计算窗口内最大回撤。"""
    subset = _window_slice(navs, end_index, window)
    # 最大回撤基于净值路径而不是收益序列直接推导，因为它依赖历史峰值路径。
    peak = subset[0]
    max_drawdown = 0.0
    for nav in subset:
        peak = max(peak, nav)
        max_drawdown = min(max_drawdown, nav / peak - 1.0)
    return round(max_drawdown, 6)


def _window_asset_stability(values: list[float], end_index: int, window: int) -> float:
    """用窗口内规模波动幅度刻画规模稳定性。"""
    subset = _window_slice(values, end_index, window)
    if not subset or min(subset) <= 0:
        return 0.0
    # 数值越大表示规模波动越大；后续在稳定性打分里会按“更稳定更好”的方向处理。
    return round(max(subset) / min(subset) - 1.0, 6)
