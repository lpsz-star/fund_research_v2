from __future__ import annotations

from math import sqrt


def summarize_backtest(backtest_rows: list[dict[str, object]]) -> dict[str, object]:
    """把月频回测结果汇总为常用绩效指标。"""
    if not backtest_rows:
        return {"months": 0}
    net_returns = [float(row["portfolio_return_net"]) for row in backtest_rows]
    benchmark_returns = [float(row["benchmark_return"]) for row in backtest_rows]
    missing_weights = [float(row.get("missing_weight", 0.0)) for row in backtest_rows]
    cumulative = 1.0
    benchmark_cumulative = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in net_returns:
        # 最大回撤基于策略净值曲线逐期更新峰值，避免把回撤误算成单期最差收益。
        cumulative *= 1 + value
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative / peak - 1.0)
    for value in benchmark_returns:
        benchmark_cumulative *= 1 + value
    mean_return = sum(net_returns) / len(net_returns)
    # 月频结果按 12 期年化；只要调仓频率改变，这里的年化逻辑就必须同步调整。
    volatility = sqrt(sum((value - mean_return) ** 2 for value in net_returns) / len(net_returns))
    return {
        "months": len(backtest_rows),
        "cumulative_return": round(cumulative - 1.0, 6),
        "annualized_return": round((cumulative ** (12 / len(net_returns))) - 1.0, 6),
        "annualized_volatility": round(volatility * sqrt(12), 6),
        "max_drawdown": round(max_drawdown, 6),
        "win_rate": round(sum(1 for value in net_returns if value > 0) / len(net_returns), 6),
        "benchmark_cumulative_return": round(benchmark_cumulative - 1.0, 6),
        "excess_cumulative_return": round(cumulative - benchmark_cumulative, 6),
        "missing_month_count": sum(1 for row in backtest_rows if str(row.get("return_validity", "")) in {"partial_missing", "all_missing"}),
        "low_confidence_month_count": sum(1 for row in backtest_rows if int(row.get("low_confidence_flag", 0)) == 1),
        "avg_missing_weight": round(sum(missing_weights) / len(missing_weights), 6),
        "max_missing_weight": round(max(missing_weights), 6),
    }
