from __future__ import annotations

from collections import defaultdict

from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.date_utils import iter_months
from fund_research_v2.portfolio.construction import build_portfolio


def run_backtest(
    config: AppConfig,
    score_rows: list[dict[str, object]],
    nav_rows: list[dict[str, object]],
    benchmark_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """按“本月信号、下一月执行”口径回放历史表现。"""
    scores_by_month: dict[str, list[dict[str, object]]] = defaultdict(list)
    # 回测直接使用月收益查表，是为了把时间边界固定在月频层，不在引擎里重复解释日频净值。
    nav_lookup = {(str(row["entity_id"]), str(row["month"])): float(row["return_1m"]) for row in nav_rows}
    benchmark_lookup: dict[str, dict[str, float]] = defaultdict(dict)
    for row in benchmark_rows:
        benchmark_key = str(row.get("benchmark_key") or config.benchmark.default_key)
        benchmark_lookup[benchmark_key][str(row["month"])] = float(row[config.backtest.benchmark_field])
    for row in score_rows:
        scores_by_month[str(row["month"])].append(row)
    available_months = sorted({str(row["month"]) for row in score_rows} | {str(row["month"]) for row in benchmark_rows})
    if not available_months:
        return []
    start_month = config.backtest.start_month or available_months[0]
    end_month = config.backtest.end_month or available_months[-1]
    # 回测必须按完整月历推进，否则“无信号月份”会被静默跳过，导致月数、收益路径和年化口径失真。
    months = iter_months(start_month, end_month)
    backtest_rows = []
    previous_weights: dict[str, float] = {}
    for current_month, next_month in zip(months, months[1:]):
        # 回测严格采用“本月生成信号，下一月兑现收益”的时序。
        current_scores = scores_by_month.get(current_month, [])
        portfolio = build_portfolio(config, current_scores)
        score_lookup = {str(row["entity_id"]): row for row in current_scores}
        gross_return = 0.0
        benchmark_return = 0.0
        current_weights = {}
        benchmark_key_weights: dict[str, float] = defaultdict(float)
        for position in portfolio:
            entity_id = str(position["entity_id"])
            weight = float(position["target_weight"])
            current_weights[entity_id] = weight
            # 若下一月缺少收益，这里暂按 0 处理；这是保守但粗糙的默认口径，后续需要更严格的异常处理。
            gross_return += weight * nav_lookup.get((entity_id, next_month), 0.0)
            primary_type = str(score_lookup.get(entity_id, {}).get("primary_type") or "")
            benchmark_key = config.benchmark.key_for_primary_type(primary_type)
            benchmark_value = _benchmark_return_for_key(benchmark_lookup, benchmark_key, config.benchmark.default_key, next_month)
            benchmark_return += weight * benchmark_value
            benchmark_key_weights[benchmark_key] += weight
        if not portfolio:
            default_key = config.benchmark.default_key
            benchmark_return = _benchmark_return_for_key(benchmark_lookup, default_key, default_key, next_month)
            benchmark_key_weights[default_key] = 1.0
        turnover = _turnover(previous_weights, current_weights)
        cost = turnover * (config.backtest.transaction_cost_bps / 10000.0)
        net_return = gross_return - cost
        backtest_rows.append(
            {
                "signal_month": current_month,
                "execution_month": next_month,
                "portfolio_return_gross": round(gross_return, 6),
                "portfolio_return_net": round(net_return, 6),
                "benchmark_return": round(benchmark_return, 6),
                "benchmark_mix": _format_benchmark_mix(benchmark_key_weights),
                "turnover": round(turnover, 6),
                "transaction_cost": round(cost, 6),
                "holdings": len(portfolio),
            }
        )
        previous_weights = current_weights
    return backtest_rows


def _turnover(previous_weights: dict[str, float], current_weights: dict[str, float]) -> float:
    """根据相邻两期目标权重计算组合换手率。"""
    keys = set(previous_weights) | set(current_weights)
    # 使用权重变化的一半定义换手，是组合研究里常见且可审计的简化口径。
    return round(sum(abs(current_weights.get(key, 0.0) - previous_weights.get(key, 0.0)) for key in keys) / 2.0, 6)


def _benchmark_return_for_key(
    benchmark_lookup: dict[str, dict[str, float]],
    benchmark_key: str,
    default_benchmark_key: str,
    month: str,
) -> float:
    """返回指定月份的 benchmark 收益，缺失时回退到默认 benchmark。"""
    if benchmark_key in benchmark_lookup and month in benchmark_lookup[benchmark_key]:
        return benchmark_lookup[benchmark_key][month]
    return benchmark_lookup.get(default_benchmark_key, {}).get(month, 0.0)


def _format_benchmark_mix(weights: dict[str, float]) -> str:
    """把组合内 benchmark 权重写成可审计字符串，方便回头解释组合比较基准。"""
    ordered = sorted(((key, value) for key, value in weights.items() if value > 0), key=lambda item: item[0])
    return "|".join(f"{key}:{round(value, 6)}" for key, value in ordered)
