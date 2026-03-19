from __future__ import annotations

from collections import defaultdict

from fund_research_v2.common.config import AppConfig
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
    benchmark_lookup = {str(row["month"]): float(row[config.backtest.benchmark_field]) for row in benchmark_rows}
    for row in score_rows:
        scores_by_month[str(row["month"])].append(row)
    months = sorted(scores_by_month)
    if config.backtest.start_month:
        months = [month for month in months if month >= config.backtest.start_month]
    if config.backtest.end_month:
        months = [month for month in months if month <= config.backtest.end_month]
    backtest_rows = []
    previous_weights: dict[str, float] = {}
    for current_month, next_month in zip(months, months[1:]):
        # 回测严格采用“本月生成信号，下一月兑现收益”的时序。
        portfolio = build_portfolio(config, scores_by_month[current_month])
        if not portfolio:
            continue
        gross_return = 0.0
        current_weights = {}
        for position in portfolio:
            entity_id = str(position["entity_id"])
            weight = float(position["target_weight"])
            current_weights[entity_id] = weight
            # 若下一月缺少收益，这里暂按 0 处理；这是保守但粗糙的默认口径，后续需要更严格的异常处理。
            gross_return += weight * nav_lookup.get((entity_id, next_month), 0.0)
        turnover = _turnover(previous_weights, current_weights)
        cost = turnover * (config.backtest.transaction_cost_bps / 10000.0)
        net_return = gross_return - cost
        backtest_rows.append(
            {
                "signal_month": current_month,
                "execution_month": next_month,
                "portfolio_return_gross": round(gross_return, 6),
                "portfolio_return_net": round(net_return, 6),
                "benchmark_return": round(benchmark_lookup.get(next_month, 0.0), 6),
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
