from __future__ import annotations

from collections import defaultdict

from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.date_utils import iter_months, month_start
from fund_research_v2.portfolio.construction import build_portfolio


def run_backtest(
    config: AppConfig,
    score_rows: list[dict[str, object]],
    nav_rows: list[dict[str, object]],
    benchmark_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """按“月末生成信号、次月月初申购代理执行”口径回放历史表现。"""
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
        return [], []
    start_month = config.backtest.start_month or available_months[0]
    end_month = config.backtest.end_month or available_months[-1]
    # 回测必须按完整月历推进，否则“无信号月份”会被静默跳过，导致月数、收益路径和年化口径失真。
    months = iter_months(start_month, end_month)
    backtest_rows = []
    position_audit_rows = []
    previous_weights: dict[str, float] = {}
    for current_month, next_month in zip(months, months[1:]):
        # 回测严格采用“本月生成信号，下一月兑现收益”的时序。
        current_scores = scores_by_month.get(current_month, [])
        portfolio = build_portfolio(config, current_scores)
        execution_request_date = month_start(next_month)
        # 这里把 execution_month 月初同时作为“申请提交”和“确认生效”的代理日。
        # 原因不是认为真实基金一定在这一天成交，而是当前只有月频收益、没有开放申购日和确认规则，
        # 因此只能用一个显式代理日把“次月开始承担收益”写清楚，避免误读为信号月内已成交。
        execution_effective_date = execution_request_date
        gross_return = 0.0
        benchmark_return = _benchmark_return_for_key(
            benchmark_lookup,
            config.benchmark.default_key,
            config.benchmark.default_key,
            next_month,
        )
        current_weights = {}
        missing_weight = 0.0
        missing_position_count = 0
        for position in portfolio:
            entity_id = str(position["entity_id"])
            weight = float(position["target_weight"])
            current_weights[entity_id] = weight
            observed_return = nav_lookup.get((entity_id, next_month))
            resolved_position = _resolve_position_return(config.backtest.missing_return_policy, observed_return)
            gross_return += weight * float(resolved_position["applied_return_1m"])
            if int(resolved_position["missing_return_flag"]) == 1:
                missing_weight += weight
                missing_position_count += 1
            position_audit_rows.append(
                {
                    "signal_month": current_month,
                    "execution_month": next_month,
                    "entity_id": entity_id,
                    "entity_name": str(position.get("entity_name", "")),
                    "target_weight": round(weight, 6),
                    "observed_return_1m": resolved_position["observed_return_1m"],
                    "applied_return_1m": resolved_position["applied_return_1m"],
                    "outcome_status": resolved_position["outcome_status"],
                    "handling_policy": config.backtest.missing_return_policy,
                }
            )
        turnover = _turnover(previous_weights, current_weights)
        cost = turnover * (config.backtest.transaction_cost_bps / 10000.0)
        net_return = gross_return - cost
        return_validity = _classify_month_return_validity(len(portfolio), missing_position_count)
        backtest_rows.append(
            {
                "signal_month": current_month,
                "execution_month": next_month,
                "execution_request_date_proxy": execution_request_date,
                "execution_effective_date_proxy": execution_effective_date,
                "portfolio_return_gross": round(gross_return, 6),
                "portfolio_return_net": round(net_return, 6),
                "benchmark_return": round(benchmark_return, 6),
                "turnover": round(turnover, 6),
                "transaction_cost": round(cost, 6),
                "holdings": len(portfolio),
                "missing_weight": round(missing_weight, 6),
                "missing_position_count": missing_position_count,
                "low_confidence_flag": 1 if missing_weight > config.backtest.missing_weight_warning_threshold else 0,
                "return_validity": return_validity,
            }
        )
        previous_weights = current_weights
    return backtest_rows, position_audit_rows


def _resolve_position_return(missing_return_policy: str, observed_return: float | None) -> dict[str, object]:
    """把单持仓在执行月的收益观测结果转换成回测使用值和审计状态。"""
    if observed_return is not None:
        return {
            "observed_return_1m": round(observed_return, 6),
            "applied_return_1m": round(observed_return, 6),
            "outcome_status": "observed_return",
            "missing_return_flag": 0,
        }
    if missing_return_policy == "audit_only":
        applied_return = 0.0
    else:
        applied_return = 0.0
    return {
        "observed_return_1m": "",
        "applied_return_1m": round(applied_return, 6),
        "outcome_status": "missing_return",
        "missing_return_flag": 1,
    }


def _classify_month_return_validity(holdings: int, missing_position_count: int) -> str:
    """把单月回测结果映射到可审计的收益有效性标签。"""
    if holdings == 0:
        return "empty_portfolio"
    if missing_position_count == 0:
        return "valid"
    if missing_position_count >= holdings:
        return "all_missing"
    return "partial_missing"


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
