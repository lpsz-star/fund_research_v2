from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import prod

from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.date_utils import decision_date_for_month, iter_months, month_start, next_trading_day, shift_trading_days
from fund_research_v2.portfolio.construction import build_portfolio


@dataclass(frozen=True)
class BacktestExecutionCache:
    """回测执行代理共享的只读索引缓存。"""
    open_trade_dates: list[str]
    trade_date_index: dict[str, int]
    daily_return_lookup: dict[tuple[str, str], float]
    benchmark_daily_lookup: dict[tuple[str, str], float]
    schedule_by_month: dict[str, dict[str, object]]


def run_backtest(
    config: AppConfig,
    score_rows: list[dict[str, object]],
    nav_rows: list[dict[str, object]],
    benchmark_rows: list[dict[str, object]],
    trade_calendar_rows: list[dict[str, object]] | None = None,
    nav_daily_rows: list[dict[str, object]] | None = None,
    prepared_execution_cache: BacktestExecutionCache | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """执行历史回测；若提供交易日历和 PIT 日频净值，则使用新执行代理口径。"""
    if prepared_execution_cache is not None:
        if not trade_calendar_rows:
            raise ValueError("prepared_execution_cache 需要同时提供 trade_calendar_rows。")
        return _run_backtest_with_daily_execution(
            config=config,
            score_rows=score_rows,
            benchmark_rows=benchmark_rows,
            trade_calendar_rows=trade_calendar_rows,
            prepared_execution_cache=prepared_execution_cache,
        )
    if trade_calendar_rows and nav_daily_rows:
        available_months = sorted({str(row["month"]) for row in score_rows} | {str(row["month"]) for row in benchmark_rows})
        if not available_months:
            return [], []
        start_month = config.backtest.start_month or available_months[0]
        end_month = config.backtest.end_month or available_months[-1]
        return _run_backtest_with_daily_execution(
            config=config,
            score_rows=score_rows,
            benchmark_rows=benchmark_rows,
            trade_calendar_rows=trade_calendar_rows,
            prepared_execution_cache=prepare_backtest_execution_cache(
                config=config,
                benchmark_rows=benchmark_rows,
                trade_calendar_rows=trade_calendar_rows,
                nav_daily_rows=nav_daily_rows,
                months=iter_months(start_month, end_month),
            ),
        )
    return _run_backtest_monthly_legacy(config, score_rows, nav_rows, benchmark_rows)


def prepare_backtest_execution_cache(
    *,
    config: AppConfig,
    benchmark_rows: list[dict[str, object]],
    trade_calendar_rows: list[dict[str, object]],
    nav_daily_rows: list[dict[str, object]],
    months: list[str] | None = None,
) -> BacktestExecutionCache:
    """构建同一实验可复用的回测执行代理缓存。"""
    open_trade_dates = _open_trade_dates(trade_calendar_rows)
    schedule_months = sorted(set(months or []))
    if not schedule_months:
        schedule_months = sorted({str(row.get("month") or "") for row in benchmark_rows if str(row.get("month") or "")})
    return BacktestExecutionCache(
        open_trade_dates=open_trade_dates,
        trade_date_index={trade_date: index for index, trade_date in enumerate(open_trade_dates)},
        daily_return_lookup=_daily_return_lookup(nav_daily_rows),
        benchmark_daily_lookup=_benchmark_daily_return_lookup(config, benchmark_rows, trade_calendar_rows),
        schedule_by_month=_build_execution_schedule_by_month(config, schedule_months, trade_calendar_rows),
    )


def _run_backtest_with_daily_execution(
    *,
    config: AppConfig,
    score_rows: list[dict[str, object]],
    benchmark_rows: list[dict[str, object]],
    trade_calendar_rows: list[dict[str, object]],
    prepared_execution_cache: BacktestExecutionCache,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """按 decision_date(T) 卖出、T+2 到账、T+3 新组合开始收益的研究代理口径回放。"""
    scores_by_month: dict[str, list[dict[str, object]]] = defaultdict(list)
    entity_primary_type_lookup: dict[str, str] = {}
    for row in score_rows:
        month = str(row["month"])
        entity_id = str(row["entity_id"])
        scores_by_month[month].append(row)
        entity_primary_type_lookup[entity_id] = str(row.get("primary_type") or "")

    available_months = sorted({str(row["month"]) for row in score_rows} | {str(row["month"]) for row in benchmark_rows})
    if not available_months:
        return [], []
    start_month = config.backtest.start_month or available_months[0]
    end_month = config.backtest.end_month or available_months[-1]
    months = iter_months(start_month, end_month)
    if len(months) < 2:
        return [], []

    execution_cache = _ensure_execution_schedule_for_months(
        config=config,
        trade_calendar_rows=trade_calendar_rows,
        prepared_execution_cache=prepared_execution_cache,
        months=months,
    )

    backtest_rows: list[dict[str, object]] = []
    position_audit_rows: list[dict[str, object]] = []
    previous_weights: dict[str, float] = {}

    for current_month, next_month in zip(months, months[1:]):
        portfolio = build_portfolio(config, scores_by_month.get(current_month, []))
        current_weights = {str(row["entity_id"]): float(row["target_weight"]) for row in portfolio}
        turnover = _turnover(previous_weights, current_weights)
        transaction_cost = turnover * (config.backtest.transaction_cost_bps / 10000.0)

        schedule = execution_cache.schedule_by_month[current_month]
        decision_date = str(schedule["decision_date"])
        next_decision_date = str(schedule["next_decision_date"])
        cash_available_date = str(schedule["cash_available_date"])
        buy_effective_date = str(schedule["buy_effective_date"])
        transition_start_date = str(schedule["transition_start_date"])
        period_trade_dates = _trade_dates_between(
            execution_cache.open_trade_dates,
            execution_cache.trade_date_index,
            transition_start_date,
            next_decision_date,
        )
        invested_trade_dates = _trade_dates_between(
            execution_cache.open_trade_dates,
            execution_cache.trade_date_index,
            buy_effective_date,
            next_decision_date,
        )

        gross_return, missing_weight, missing_position_count, period_position_rows = _portfolio_period_return(
            config=config,
            portfolio=portfolio,
            invested_trade_dates=invested_trade_dates,
            daily_return_lookup=execution_cache.daily_return_lookup,
        )
        benchmark_return = _compound_benchmark_return(execution_cache.benchmark_daily_lookup, period_trade_dates)
        net_return = gross_return - transaction_cost
        return_validity = _classify_period_return_validity(len(portfolio), invested_trade_dates, missing_weight)

        for row in period_position_rows:
            benchmark_key = config.benchmark.key_for_primary_type(entity_primary_type_lookup.get(str(row["entity_id"]), ""))
            position_audit_rows.append(
                {
                    "valuation_month": current_month,
                    "signal_month": current_month,
                    "execution_month": buy_effective_date[:7],
                    "decision_date": decision_date,
                    "cash_available_date": cash_available_date,
                    "buy_effective_date": buy_effective_date,
                    "holding_start_date": transition_start_date,
                    "holding_end_date": next_decision_date,
                    "entity_id": row["entity_id"],
                    "entity_name": row["entity_name"],
                    "target_weight": row["target_weight"],
                    "missing_trade_date_count": row["missing_trade_date_count"],
                    "covered_trade_date_count": row["covered_trade_date_count"],
                    "invested_trade_date_count": len(invested_trade_dates),
                    "outcome_status": row["outcome_status"],
                    "benchmark_key": benchmark_key,
                    "observed_return_1m": "",
                    "applied_return_1m": row["applied_period_return"],
                    "handling_policy": config.backtest.missing_return_policy,
                }
            )

        backtest_rows.append(
            {
                "valuation_month": current_month,
                "signal_month": current_month,
                "execution_month": buy_effective_date[:7],
                "decision_date": decision_date,
                "cash_available_date": cash_available_date,
                "buy_effective_date": buy_effective_date,
                "holding_start_date": transition_start_date,
                "holding_end_date": next_decision_date,
                "execution_request_date_proxy": decision_date,
                "execution_effective_date_proxy": buy_effective_date,
                "period_type": "decision_t_plus_2_buy_t_plus_3",
                "portfolio_return_gross": round(gross_return, 6),
                "portfolio_return_net": round(net_return, 6),
                "benchmark_return": round(benchmark_return, 6),
                "turnover": round(turnover, 6),
                "transaction_cost": round(transaction_cost, 6),
                "holdings": len(portfolio),
                "missing_weight": round(missing_weight, 6),
                "missing_position_count": missing_position_count,
                "low_confidence_flag": 1 if missing_weight > config.backtest.missing_weight_warning_threshold else 0,
                "return_validity": return_validity,
                "cash_transition_trade_days": max(len(period_trade_dates) - len(invested_trade_dates), 0),
                "invested_trade_days": len(invested_trade_dates),
            }
        )
        previous_weights = current_weights
    return backtest_rows, position_audit_rows


def _portfolio_period_return(
    *,
    config: AppConfig,
    portfolio: list[dict[str, object]],
    invested_trade_dates: list[str],
    daily_return_lookup: dict[tuple[str, str], float],
) -> tuple[float, float, int, list[dict[str, object]]]:
    """计算一段持仓期的组合收益与缺失审计。"""
    if not portfolio:
        return 0.0, 0.0, 0, []
    if not invested_trade_dates:
        return 0.0, 0.0, 0, [
            {
                "entity_id": str(position["entity_id"]),
                "entity_name": str(position.get("entity_name", "")),
                "target_weight": round(float(position["target_weight"]), 6),
                "missing_trade_date_count": 0,
                "covered_trade_date_count": 0,
                "applied_period_return": 0.0,
                "outcome_status": "cash_only_period",
            }
            for position in portfolio
        ]

    weighted_daily_returns: list[float] = []
    missing_weight = 0.0
    position_rows: list[dict[str, object]] = []
    missing_position_count = 0
    per_position_path: dict[str, list[float]] = defaultdict(list)
    per_position_missing_days: dict[str, int] = defaultdict(int)

    for trade_date in invested_trade_dates:
        daily_portfolio_return = 0.0
        for position in portfolio:
            entity_id = str(position["entity_id"])
            weight = float(position["target_weight"])
            observed = daily_return_lookup.get((entity_id, trade_date))
            if observed is None:
                per_position_missing_days[entity_id] += 1
                missing_weight += weight / len(invested_trade_dates)
                applied = 0.0
            else:
                applied = observed
            per_position_path[entity_id].append(applied)
            daily_portfolio_return += weight * applied
        weighted_daily_returns.append(daily_portfolio_return)

    for position in portfolio:
        entity_id = str(position["entity_id"])
        path = per_position_path.get(entity_id, [])
        applied_period_return = _compound_returns(path)
        missing_days = per_position_missing_days.get(entity_id, 0)
        if missing_days > 0:
            missing_position_count += 1
        position_rows.append(
            {
                "entity_id": entity_id,
                "entity_name": str(position.get("entity_name", "")),
                "target_weight": round(float(position["target_weight"]), 6),
                "missing_trade_date_count": missing_days,
                "covered_trade_date_count": len(invested_trade_dates) - missing_days,
                "applied_period_return": round(applied_period_return, 6),
                "outcome_status": "missing_return" if missing_days > 0 else "observed_return",
            }
        )

    return _compound_returns(weighted_daily_returns), missing_weight, missing_position_count, position_rows


def _benchmark_daily_return_lookup(
    config: AppConfig,
    benchmark_rows: list[dict[str, object]],
    trade_calendar_rows: list[dict[str, object]],
) -> dict[tuple[str, str], float]:
    """把月频 benchmark 收益展开成日频代理，使跨月持有期也可复利聚合。"""
    monthly_lookup: dict[str, dict[str, float]] = defaultdict(dict)
    for row in benchmark_rows:
        benchmark_key = str(row.get("benchmark_key") or config.benchmark.default_key)
        monthly_lookup[benchmark_key][str(row["month"])] = float(row.get(config.backtest.benchmark_field, 0.0))

    open_dates_by_month: dict[str, list[str]] = defaultdict(list)
    for row in trade_calendar_rows:
        if int(str(row.get("is_open") or "0")) != 1:
            continue
        trade_date = str(row.get("cal_date") or "")
        open_dates_by_month[trade_date[:7]].append(trade_date)

    benchmark_daily: dict[tuple[str, str], float] = {}
    for benchmark_key, month_lookup in monthly_lookup.items():
        for month, monthly_return in month_lookup.items():
            open_dates = sorted(open_dates_by_month.get(month, []))
            if not open_dates:
                continue
            daily_return = (1.0 + monthly_return) ** (1.0 / len(open_dates)) - 1.0
            for trade_date in open_dates:
                if benchmark_key == config.benchmark.default_key:
                    benchmark_daily[("benchmark", trade_date)] = daily_return
    return benchmark_daily


def _compound_benchmark_return(
    benchmark_daily_lookup: dict[tuple[str, str], float],
    trade_dates: list[str],
) -> float:
    """使用默认 benchmark 的日频代理收益计算一段期间的累计收益。"""
    if not trade_dates:
        return 0.0
    daily_returns = [benchmark_daily_lookup.get(("benchmark", trade_date), 0.0) for trade_date in trade_dates]
    return round(_compound_returns(daily_returns), 6)


def _daily_return_lookup(nav_daily_rows: list[dict[str, object]]) -> dict[tuple[str, str], float]:
    """构建实体级日收益查询表。"""
    lookup: dict[tuple[str, str], float] = {}
    for row in nav_daily_rows:
        entity_id = str(row.get("entity_id") or "")
        trade_date = str(row.get("trade_date") or "")
        if not entity_id or not trade_date:
            continue
        lookup[(entity_id, trade_date)] = float(row.get("daily_return", 0.0))
    return lookup


def _open_trade_dates(trade_calendar_rows: list[dict[str, object]]) -> list[str]:
    """提取全部开市日期并排序。"""
    return sorted(
        str(row.get("cal_date") or "")
        for row in trade_calendar_rows
        if int(str(row.get("is_open") or "0")) == 1 and str(row.get("cal_date") or "").strip()
    )


def _trade_dates_between(
    open_trade_dates: list[str],
    trade_date_index: dict[str, int],
    start_date: str,
    end_date: str,
) -> list[str]:
    """基于交易日索引返回闭区间内的交易日。"""
    start_index = trade_date_index.get(start_date)
    end_index = trade_date_index.get(end_date)
    if start_index is None or end_index is None or start_index > end_index:
        return []
    return open_trade_dates[start_index : end_index + 1]


def _build_execution_schedule_by_month(
    config: AppConfig,
    months: list[str],
    trade_calendar_rows: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    """预计算逐月执行日程，避免同一实验重复推导 T/T+2/T+3 边界。"""
    ordered_months = sorted(set(months))
    schedule_by_month: dict[str, dict[str, object]] = {}
    for month in ordered_months:
        decision_date = decision_date_for_month(month, trade_calendar_rows)
        try:
            cash_available_date = shift_trading_days(
                decision_date,
                config.backtest.redemption_settlement_lag_days,
                trade_calendar_rows,
            )
        except ValueError:
            cash_available_date = decision_date
        try:
            buy_effective_date = shift_trading_days(
                cash_available_date,
                config.backtest.purchase_effective_lag_days,
                trade_calendar_rows,
            )
        except ValueError:
            buy_effective_date = cash_available_date
        try:
            transition_start_date = next_trading_day(decision_date, trade_calendar_rows)
        except ValueError:
            # 尾月若缺少后续交易日，该日程不会被实际消费；这里仅为保持缓存结构完整。
            transition_start_date = decision_date
        schedule_by_month[month] = {
            "decision_date": decision_date,
            "cash_available_date": cash_available_date,
            "buy_effective_date": buy_effective_date,
            "transition_start_date": transition_start_date,
            "next_decision_date": decision_date,
        }
    for current_month, next_month in zip(ordered_months, ordered_months[1:]):
        schedule_by_month[current_month]["next_decision_date"] = schedule_by_month[next_month]["decision_date"]
    if ordered_months:
        last_month = ordered_months[-1]
        schedule_by_month[last_month]["next_decision_date"] = decision_date_for_month(last_month, trade_calendar_rows)
    return schedule_by_month


def _ensure_execution_schedule_for_months(
    *,
    config: AppConfig,
    trade_calendar_rows: list[dict[str, object]],
    prepared_execution_cache: BacktestExecutionCache,
    months: list[str],
) -> BacktestExecutionCache:
    """若缓存缺少当前回测区间的执行日程，则补齐并返回对齐后的缓存。"""
    missing_months = [month for month in months if month not in prepared_execution_cache.schedule_by_month]
    if not missing_months:
        return prepared_execution_cache
    merged_months = sorted(set(prepared_execution_cache.schedule_by_month) | set(months))
    return BacktestExecutionCache(
        open_trade_dates=prepared_execution_cache.open_trade_dates,
        trade_date_index=prepared_execution_cache.trade_date_index,
        daily_return_lookup=prepared_execution_cache.daily_return_lookup,
        benchmark_daily_lookup=prepared_execution_cache.benchmark_daily_lookup,
        schedule_by_month=_build_execution_schedule_by_month(config, merged_months, trade_calendar_rows),
    )


def _compound_returns(values: list[float]) -> float:
    """将一串日收益复利成区间收益。"""
    if not values:
        return 0.0
    return prod(1.0 + value for value in values) - 1.0


def _classify_period_return_validity(holdings: int, invested_trade_dates: list[str], missing_weight: float) -> str:
    """把新口径下的区间收益映射到可审计的有效性标签。"""
    if holdings == 0:
        return "empty_portfolio"
    if not invested_trade_dates:
        return "cash_only"
    if missing_weight <= 0:
        return "valid"
    if missing_weight >= 0.999999:
        return "all_missing"
    return "partial_missing"


def _run_backtest_monthly_legacy(
    config: AppConfig,
    score_rows: list[dict[str, object]],
    nav_rows: list[dict[str, object]],
    benchmark_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """兼容旧测试和无日频数据场景的月频代理回测。"""
    scores_by_month: dict[str, list[dict[str, object]]] = defaultdict(list)
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
    months = iter_months(start_month, end_month)
    backtest_rows = []
    position_audit_rows = []
    previous_weights: dict[str, float] = {}
    for current_month, next_month in zip(months, months[1:]):
        current_scores = scores_by_month.get(current_month, [])
        portfolio = build_portfolio(config, current_scores)
        execution_request_date = month_start(next_month)
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
