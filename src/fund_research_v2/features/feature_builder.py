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
            benchmark_key = config.benchmark.key_for_primary_type(str(entity["primary_type"]))
            benchmark_lookup_map = _visible_benchmark_lookup_map(benchmark_rows, month, config.benchmark.default_key)
            benchmark_lookup = _benchmark_lookup_for_key(benchmark_lookup_map, benchmark_key, config.benchmark.default_key)
            benchmark_series = config.benchmark.series_for_key(benchmark_key)
            excess_ret_3m = round(_window_total_return(returns, index, 3) - _window_total_return_from_scalar(benchmark_lookup, months, index, 3), 6)
            excess_ret_6m = round(_window_total_return(returns, index, 6) - _window_total_return_from_scalar(benchmark_lookup, months, index, 6), 6)
            excess_ret_12m = round(_window_total_return(returns, index, 12) - _window_total_return_from_scalar(benchmark_lookup, months, index, 12), 6)
            monthly_excess_returns = _monthly_excess_returns(returns, months, benchmark_lookup)
            manager_row = manager_lookup.get((entity_id, month))
            manager_post_change_excess_delta_12m, manager_post_change_observation_months = _manager_post_change_excess_delta(
                months=months,
                monthly_excess_returns=monthly_excess_returns,
                manager_start_month=_manager_start_month_for_feature(entity, manager_row),
                current_month=month,
                window=12,
            )
            # 特征只用当月及历史窗口数据构造，避免把未来月份收益泄漏到当前信号。
            feature_rows.append(
                {
                    "entity_id": entity_id,
                    "month": month,
                    "is_eligible": eligibility[(entity_id, month)],
                    "entity_name": entity["entity_name"],
                    "fund_company": entity["fund_company"],
                    "primary_type": entity["primary_type"],
                    "benchmark_key": benchmark_key,
                    "benchmark_name": benchmark_series.name,
                    "manager_name": _manager_name_for_month(entity, manager_row),
                    "ret_3m": _window_total_return(returns, index, 3),
                    "ret_6m": _window_total_return(returns, index, 6),
                    "ret_12m": _window_total_return(returns, index, 12),
                    # excess_ret_12m 保留 benchmark 接口，即使当前 benchmark 还是代理值，也能固定未来的字段契约。
                    "excess_ret_3m": excess_ret_3m,
                    "excess_ret_6m": excess_ret_6m,
                    "excess_ret_12m": excess_ret_12m,
                    # 一致性因子优先回答“多个窗口是否持续跑赢”，先不用幅度大小主导结果，避免单一窗口极端行情放大噪声。
                    "excess_consistency_12m": _excess_consistency_ratio(excess_ret_3m, excess_ret_6m, excess_ret_12m),
                    "vol_12m": _window_volatility(returns, index, 12),
                    "downside_vol_12m": _window_downside_volatility(returns, index, 12),
                    "max_drawdown_12m": _window_max_drawdown(navs, index, 12),
                    "drawdown_recovery_ratio_12m": _window_drawdown_recovery_ratio(navs, index, 12),
                    "months_since_drawdown_low_12m": _window_months_since_drawdown_low(navs, index, 12),
                    "hit_rate_12m": _window_hit_rate(returns, index, 12),
                    "profit_loss_ratio_12m": _window_profit_loss_ratio(returns, index, 12),
                    "worst_3m_avg_return_12m": _window_worst_average_return(returns, index, 12, 3),
                    "manager_post_change_excess_delta_12m": manager_post_change_excess_delta_12m,
                    "manager_post_change_observation_months": manager_post_change_observation_months,
                    "manager_tenure_months": _manager_tenure_months(entity, month, manager_row),
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


def _manager_start_month_for_feature(entity: dict[str, object], manager_row: dict[str, object] | None) -> str | None:
    """统一获取当前月应使用的经理起始月份，保证经理相关因子口径一致。"""
    manager_start_month = _safe_month_or_none((manager_row or {}).get("manager_start_month"))
    if manager_start_month is not None:
        return manager_start_month
    return _safe_month_or_none(entity.get("manager_start_month"))


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


def _monthly_excess_returns(
    returns: list[float],
    months: list[str],
    benchmark_lookup: dict[str, float],
) -> list[float]:
    """构造逐月超额收益序列，供经理前后表现切分等事件类因子复用。"""
    return [round(fund_return - benchmark_lookup.get(month, 0.0), 6) for fund_return, month in zip(returns, months)]


def _visible_benchmark_lookup_map(
    benchmark_rows: list[dict[str, object]],
    signal_month: str,
    default_benchmark_key: str,
) -> dict[str, dict[str, float]]:
    """构建截至某个信号月末实际可见的 benchmark 月收益映射。"""
    visible_lookup: dict[str, dict[str, float]] = defaultdict(dict)
    for row in benchmark_rows:
        month = str(row["month"])
        available_date = _benchmark_available_date(row)
        if month <= signal_month and is_available_by_month_end(available_date, signal_month):
            benchmark_key = str(row.get("benchmark_key") or default_benchmark_key)
            visible_lookup[benchmark_key][month] = float(row["benchmark_return_1m"])
    return visible_lookup


def _benchmark_lookup_for_key(
    lookup_map: dict[str, dict[str, float]],
    benchmark_key: str,
    default_benchmark_key: str,
) -> dict[str, float]:
    """返回某条 benchmark 的可见收益映射，缺失时回退到默认 benchmark。"""
    if benchmark_key in lookup_map and lookup_map[benchmark_key]:
        return lookup_map[benchmark_key]
    return lookup_map.get(default_benchmark_key, {})


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


def _window_drawdown_recovery_ratio(navs: list[float], end_index: int, window: int) -> float:
    """衡量最大回撤低点到当前月份的恢复比例，刻画基金从挫折中修复净值的能力。"""
    subset = _window_slice(navs, end_index, window)
    if len(subset) < 2:
        return 0.0
    peak = subset[0]
    trough = subset[0]
    max_drawdown = 0.0
    for nav in subset:
        if nav > peak:
            peak = nav
            trough = nav
            continue
        drawdown = nav / peak - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            trough = nav
    if max_drawdown >= 0 or peak <= 0 or trough <= 0:
        return 1.0
    total_drop = peak - trough
    if total_drop <= 0:
        return 1.0
    recovered = subset[-1] - trough
    return round(max(recovered / total_drop, 0.0), 6)


def _window_months_since_drawdown_low(navs: list[float], end_index: int, window: int) -> int:
    """返回距离窗口内最大回撤低点已经过去的月份数，辅助解释恢复速度因子。"""
    subset = _window_slice(navs, end_index, window)
    if not subset:
        return 0
    peak = subset[0]
    trough_index = 0
    max_drawdown = 0.0
    for index, nav in enumerate(subset):
        if nav > peak:
            peak = nav
            continue
        drawdown = nav / peak - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            trough_index = index
    return len(subset) - trough_index - 1


def _window_hit_rate(values: list[float], end_index: int, window: int) -> float:
    """统计窗口内正收益月份占比，衡量收益路径是否连续稳定地产生正回报。"""
    subset = _window_slice(values, end_index, window)
    if not subset:
        return 0.0
    positive_count = sum(1 for value in subset if value > 0)
    return round(positive_count / len(subset), 6)


def _window_profit_loss_ratio(values: list[float], end_index: int, window: int) -> float:
    """比较窗口内平均盈利月收益与平均亏损月跌幅，避免只看正收益次数却忽略亏损杀伤力。"""
    subset = _window_slice(values, end_index, window)
    if not subset:
        return 0.0
    positive_values = [value for value in subset if value > 0]
    negative_values = [abs(value) for value in subset if value < 0]
    if not positive_values:
        return 0.0
    if not negative_values:
        return 999.0
    average_gain = sum(positive_values) / len(positive_values)
    average_loss = sum(negative_values) / len(negative_values)
    if average_loss <= 0:
        return 999.0
    return round(average_gain / average_loss, 6)


def _window_worst_average_return(values: list[float], end_index: int, window: int, worst_count: int) -> float:
    """取窗口内最差若干个月收益均值，直接度量左尾亏损杀伤力而不是只看整体波动。"""
    subset = _window_slice(values, end_index, window)
    if not subset:
        return 0.0
    ordered = sorted(subset)
    selected = ordered[: max(1, min(worst_count, len(ordered)))]
    return round(sum(selected) / len(selected), 6)


def _manager_post_change_excess_delta(
    *,
    months: list[str],
    monthly_excess_returns: list[float],
    manager_start_month: str | None,
    current_month: str,
    window: int,
) -> tuple[float | None, int]:
    """比较现任经理上任前后超额收益均值，衡量换经理后是否带来可见改善。"""
    if manager_start_month is None or manager_start_month > current_month:
        return None, 0
    history = [(month, excess_return) for month, excess_return in zip(months, monthly_excess_returns) if month <= current_month]
    if not history:
        return None, 0
    post_values = [value for month, value in history if month >= manager_start_month][-window:]
    pre_values = [value for month, value in history if month < manager_start_month][-window:]
    if len(post_values) < 3 or len(pre_values) < 3:
        return None, len(post_values)
    post_mean = sum(post_values) / len(post_values)
    pre_mean = sum(pre_values) / len(pre_values)
    return round(post_mean - pre_mean, 6), len(post_values)


def _window_asset_stability(values: list[float], end_index: int, window: int) -> float:
    """用窗口内规模波动幅度刻画规模稳定性。"""
    subset = _window_slice(values, end_index, window)
    if not subset or min(subset) <= 0:
        return 0.0
    # 数值越大表示规模波动越大；后续在稳定性打分里会按“更稳定更好”的方向处理。
    return round(max(subset) / min(subset) - 1.0, 6)


def _excess_consistency_ratio(*window_excess_returns: float) -> float:
    """统计多个超额收益窗口中为正的占比，衡量基金是否持续跑赢基准而非只押中单一窗口。"""
    if not window_excess_returns:
        return 0.0
    positive_windows = sum(1 for value in window_excess_returns if float(value) > 0)
    return round(positive_windows / len(window_excess_returns), 6)
