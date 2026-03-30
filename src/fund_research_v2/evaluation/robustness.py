from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fund_research_v2.backtest.engine import run_backtest
from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.contracts import DatasetSnapshot
from fund_research_v2.common.date_utils import add_months
from fund_research_v2.evaluation.factor_evaluator import _rank_correlation, _to_float, _top_bottom_spread
from fund_research_v2.evaluation.metrics import summarize_backtest
from fund_research_v2.portfolio.construction import build_portfolio


def build_robustness_analysis(
    *,
    candidate_config: AppConfig,
    baseline_config: AppConfig,
    dataset: DatasetSnapshot,
    candidate_score_rows: list[dict[str, object]],
    baseline_score_rows: list[dict[str, object]],
) -> dict[str, object]:
    """构建候选评分体系相对 baseline 的稳健性验证结果。"""
    candidate_backtest_rows, _ = run_backtest(
        config=candidate_config,
        score_rows=candidate_score_rows,
        nav_rows=dataset.fund_nav_monthly,
        benchmark_rows=dataset.benchmark_monthly,
        trade_calendar_rows=dataset.trade_calendar,
        nav_daily_rows=dataset.fund_nav_pit_daily,
    )
    baseline_backtest_rows, _ = run_backtest(
        config=baseline_config,
        score_rows=baseline_score_rows,
        nav_rows=dataset.fund_nav_monthly,
        benchmark_rows=dataset.benchmark_monthly,
        trade_calendar_rows=dataset.trade_calendar,
        nav_daily_rows=dataset.fund_nav_pit_daily,
    )
    candidate_monthly_portfolios = _build_monthly_portfolios(candidate_config, candidate_score_rows)
    baseline_monthly_portfolios = _build_monthly_portfolios(baseline_config, baseline_score_rows)
    time_slice_rows = _build_time_slice_rows(candidate_backtest_rows, baseline_backtest_rows)
    contribution_rows, contribution_summary = _build_month_contribution_rows(candidate_backtest_rows)
    portfolio_behavior_rows = _build_portfolio_behavior_rows(
        candidate_monthly_portfolios,
        baseline_monthly_portfolios,
    )
    factor_regime_rows = _build_factor_regime_rows(
        candidate_score_rows,
        dataset.fund_nav_monthly,
        _candidate_factor_fields(candidate_config),
    )
    summary = _build_robustness_summary(
        candidate_config=candidate_config,
        baseline_config=baseline_config,
        candidate_backtest_rows=candidate_backtest_rows,
        baseline_backtest_rows=baseline_backtest_rows,
        time_slice_rows=time_slice_rows,
        contribution_summary=contribution_summary,
        portfolio_behavior_rows=portfolio_behavior_rows,
        factor_regime_rows=factor_regime_rows,
    )
    return {
        "summary": summary,
        "time_slice_rows": time_slice_rows,
        "month_contribution_rows": contribution_rows,
        "portfolio_behavior_rows": portfolio_behavior_rows,
        "factor_regime_rows": factor_regime_rows,
    }


def _build_time_slice_rows(
    candidate_rows: list[dict[str, object]],
    baseline_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """按时间切片输出 baseline 和候选方案的回测摘要。"""
    rows: list[dict[str, object]] = []
    month_map = {
        "candidate": {str(row["execution_month"]): row for row in candidate_rows},
        "baseline": {str(row["execution_month"]): row for row in baseline_rows},
    }
    months = sorted(set(month_map["candidate"]) & set(month_map["baseline"]))
    slice_defs = _time_slice_definitions(months)
    for slice_type, slice_label, slice_months in slice_defs:
        for scheme in ["baseline", "candidate"]:
            scoped_rows = [month_map[scheme][month] for month in slice_months if month in month_map[scheme]]
            summary = summarize_backtest(scoped_rows)
            rows.append(
                {
                    "scheme": scheme,
                    "slice_type": slice_type,
                    "slice_label": slice_label,
                    "month_count": summary.get("months", 0),
                    "cumulative_return": summary.get("cumulative_return", 0.0),
                    "annualized_return": summary.get("annualized_return", 0.0),
                    "annualized_volatility": summary.get("annualized_volatility", 0.0),
                    "max_drawdown": summary.get("max_drawdown", 0.0),
                    "benchmark_cumulative_return": summary.get("benchmark_cumulative_return", 0.0),
                    "excess_cumulative_return": summary.get("excess_cumulative_return", 0.0),
                    "win_rate": summary.get("win_rate", 0.0),
                    "avg_turnover": round(_mean([float(row.get("turnover", 0.0)) for row in scoped_rows]), 6),
                    "avg_transaction_cost": round(_mean([float(row.get("transaction_cost", 0.0)) for row in scoped_rows]), 6),
                    "avg_missing_weight": summary.get("avg_missing_weight", 0.0),
                    "low_confidence_month_count": summary.get("low_confidence_month_count", 0),
                }
            )
    return rows


def _build_month_contribution_rows(backtest_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, float]]:
    """构建月度超额收益贡献表，并输出去掉极端月份后的敏感性摘要。"""
    rows: list[dict[str, object]] = []
    ordered = []
    cumulative_excess = 0.0
    for row in backtest_rows:
        excess_return = round(float(row["portfolio_return_net"]) - float(row["benchmark_return"]), 6)
        cumulative_excess = round(cumulative_excess + excess_return, 6)
        ordered.append((str(row["execution_month"]), excess_return, cumulative_excess, row))
    ranked = sorted(ordered, key=lambda item: item[1], reverse=True)
    top_positive = {month for month, _, _, _ in ranked[:5]}
    top_negative = {month for month, _, _, _ in ranked[-5:]}
    rank_lookup = {month: index + 1 for index, (month, _, _, _) in enumerate(ranked)}
    for month, excess_return, cumulative_after, row in ordered:
        rows.append(
            {
                "month": month,
                "portfolio_return_net": row["portfolio_return_net"],
                "benchmark_return": row["benchmark_return"],
                "excess_return": excess_return,
                "cumulative_excess_return_after_month": cumulative_after,
                "excess_rank_desc": rank_lookup[month],
                "is_top_positive_contributor": 1 if month in top_positive else 0,
                "is_top_negative_contributor": 1 if month in top_negative else 0,
            }
        )
    return rows, _contribution_sensitivity_summary(backtest_rows, ranked)


def _build_portfolio_behavior_rows(
    candidate_portfolios: list[dict[str, object]],
    baseline_portfolios: list[dict[str, object]],
) -> list[dict[str, object]]:
    """按月汇总组合集中度、换仓和持仓重叠行为。"""
    rows: list[dict[str, object]] = []
    for scheme, portfolios in [("baseline", baseline_portfolios), ("candidate", candidate_portfolios)]:
        month_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in portfolios:
            month_groups[str(row["month"])].append(row)
        previous_weights: dict[str, float] = {}
        for month in sorted(month_groups):
            month_rows = sorted(month_groups[month], key=lambda item: float(item.get("target_weight", 0.0)), reverse=True)
            current_weights = {str(row["entity_id"]): float(row.get("target_weight", 0.0)) for row in month_rows}
            current_entities = set(current_weights)
            previous_entities = set(previous_weights)
            overlap_ratio = sum(min(current_weights.get(entity, 0.0), previous_weights.get(entity, 0.0)) for entity in current_entities | previous_entities)
            company_weights: dict[str, float] = defaultdict(float)
            for row in month_rows:
                company_weights[str(row.get("fund_company", ""))] += float(row.get("target_weight", 0.0))
            rows.append(
                {
                    "scheme": scheme,
                    "month": month,
                    "holdings": len(month_rows),
                    "top1_weight": round(float(month_rows[0].get("target_weight", 0.0)) if month_rows else 0.0, 6),
                    "top3_weight_sum": round(sum(float(row.get("target_weight", 0.0)) for row in month_rows[:3]), 6),
                    "company_count": len(company_weights),
                    "top_company_weight_proxy": round(max(company_weights.values()) if company_weights else 0.0, 6),
                    "new_entry_count": len(current_entities - previous_entities),
                    "dropped_count": len(previous_entities - current_entities),
                    "weight_overlap_ratio": round(overlap_ratio, 6),
                }
            )
            previous_weights = current_weights
    return rows


def _build_factor_regime_rows(
    score_rows: list[dict[str, object]],
    nav_rows: list[dict[str, object]],
    factor_fields: list[str],
) -> list[dict[str, object]]:
    """按阶段评估候选评分体系内部因子的方向稳定性。"""
    next_return_lookup = {(str(row["entity_id"]), str(row["month"])): float(row["return_1m"]) for row in nav_rows}
    eligible_by_month: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in score_rows:
        if int(row["is_eligible"]) == 1:
            eligible_by_month[str(row["month"])].append(row)
    months = sorted(eligible_by_month)
    rows: list[dict[str, object]] = []
    for slice_type, slice_label, slice_months in _factor_slice_definitions(months):
        for field in factor_fields:
            direction = _factor_direction(field)
            month_rankics: list[float] = []
            month_spreads: list[float] = []
            positive_months = 0
            for month in slice_months:
                samples = []
                next_month = add_months(month, 1)
                for row in eligible_by_month.get(month, []):
                    factor_value = _to_float(row.get(field))
                    next_return = next_return_lookup.get((str(row["entity_id"]), next_month))
                    if factor_value is None or next_return is None:
                        continue
                    samples.append(
                        {
                            "entity_id": str(row["entity_id"]),
                            "factor_value": factor_value,
                            "next_return_1m": next_return,
                        }
                    )
                if len(samples) < 2:
                    continue
                rankic = _rank_correlation(samples, "factor_value", "next_return_1m", ascending=(direction == "low"))
                spread = _top_bottom_spread(samples, ascending=(direction == "low"))
                month_rankics.append(rankic)
                month_spreads.append(spread)
                if rankic > 0:
                    positive_months += 1
            rows.append(
                {
                    "slice_type": slice_type,
                    "slice_label": slice_label,
                    "factor_name": field,
                    "evaluation_months": len(month_rankics),
                    "avg_rankic": round(_mean(month_rankics), 6),
                    "positive_rankic_ratio": round(positive_months / len(month_rankics), 6) if month_rankics else 0.0,
                    "avg_top_bottom_next_return": round(_mean(month_spreads), 6),
                }
            )
    return rows


def _build_robustness_summary(
    *,
    candidate_config: AppConfig,
    baseline_config: AppConfig,
    candidate_backtest_rows: list[dict[str, object]],
    baseline_backtest_rows: list[dict[str, object]],
    time_slice_rows: list[dict[str, object]],
    contribution_summary: dict[str, float],
    portfolio_behavior_rows: list[dict[str, object]],
    factor_regime_rows: list[dict[str, object]],
) -> dict[str, object]:
    """基于切片、贡献和行为数据生成稳健性摘要。"""
    candidate_summary = summarize_backtest(candidate_backtest_rows)
    baseline_summary = summarize_backtest(baseline_backtest_rows)
    yearly_candidate = {row["slice_label"]: row for row in time_slice_rows if row["scheme"] == "candidate" and row["slice_type"] == "calendar_year"}
    yearly_baseline = {row["slice_label"]: row for row in time_slice_rows if row["scheme"] == "baseline" and row["slice_type"] == "calendar_year"}
    winning_years = sum(
        1
        for label, row in yearly_candidate.items()
        if label in yearly_baseline and float(row["excess_cumulative_return"]) > float(yearly_baseline[label]["excess_cumulative_return"])
    )
    candidate_behavior = [row for row in portfolio_behavior_rows if row["scheme"] == "candidate"]
    baseline_behavior = [row for row in portfolio_behavior_rows if row["scheme"] == "baseline"]
    candidate_factor_rows = [row for row in factor_regime_rows if row["slice_type"] == "calendar_year" and int(row["evaluation_months"]) > 0]
    stable_factor_count = sum(1 for row in candidate_factor_rows if float(row["avg_rankic"]) > 0)
    time_slice_consistency_flag = 1 if winning_years >= max(len(yearly_candidate) - 1, 1) else 0
    return_concentration_flag = 1 if float(contribution_summary.get("top3_positive_excess_share", 0.0)) >= 0.5 else 0
    turnover_risk_flag = 1 if _mean([float(row["new_entry_count"]) for row in candidate_behavior]) > _mean([float(row["new_entry_count"]) for row in baseline_behavior]) else 0
    factor_stability_flag = 1 if candidate_factor_rows and stable_factor_count / len(candidate_factor_rows) >= 0.6 else 0
    overall_assessment = "keep_candidate" if time_slice_consistency_flag and factor_stability_flag and not return_concentration_flag else "needs_more_validation"
    return {
        "candidate_config": str(candidate_config.data_source),
        "baseline_config": str(baseline_config.data_source),
        "candidate_summary": candidate_summary,
        "baseline_summary": baseline_summary,
        "time_slice_consistency_flag": time_slice_consistency_flag,
        "return_concentration_flag": return_concentration_flag,
        "turnover_risk_flag": turnover_risk_flag,
        "factor_stability_flag": factor_stability_flag,
        "overall_assessment": overall_assessment,
        "key_findings": [
            f"candidate_excess_cumulative_return={candidate_summary.get('excess_cumulative_return', 0.0)}",
            f"baseline_excess_cumulative_return={baseline_summary.get('excess_cumulative_return', 0.0)}",
            f"top3_positive_excess_share={contribution_summary.get('top3_positive_excess_share', 0.0)}",
            f"candidate_avg_new_entry_count={round(_mean([float(row['new_entry_count']) for row in candidate_behavior]), 6) if candidate_behavior else 0.0}",
        ],
    }


def _build_monthly_portfolios(config: AppConfig, score_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """为每个研究月构建一份历史目标组合，用于行为诊断。"""
    rows: list[dict[str, object]] = []
    months = sorted({str(row["month"]) for row in score_rows})
    for month in months:
        month_rows = [row for row in score_rows if str(row["month"]) == month]
        for portfolio_row in build_portfolio(config, month_rows):
            annotated = dict(portfolio_row)
            annotated["month"] = month
            rows.append(annotated)
    return rows


def _time_slice_definitions(months: list[str]) -> list[tuple[str, str, list[str]]]:
    """构建回测时间切片定义。"""
    definitions: list[tuple[str, str, list[str]]] = []
    by_year: dict[str, list[str]] = defaultdict(list)
    for month in months:
        by_year[month[:4]].append(month)
    for year in sorted(by_year):
        definitions.append(("calendar_year", year, by_year[year]))
    for start in range(0, len(months), 6):
        segment = months[start : start + 6]
        if segment:
            definitions.append(("half_year", f"{segment[0]}~{segment[-1]}", segment))
    for end in range(11, len(months)):
        segment = months[end - 11 : end + 1]
        definitions.append(("rolling_12m", f"{segment[0]}~{segment[-1]}", segment))
    return definitions


def _factor_slice_definitions(months: list[str]) -> list[tuple[str, str, list[str]]]:
    """构建因子阶段稳定性切片定义。"""
    definitions: list[tuple[str, str, list[str]]] = []
    by_year: dict[str, list[str]] = defaultdict(list)
    for month in months:
        by_year[month[:4]].append(month)
    for year in sorted(by_year):
        definitions.append(("calendar_year", year, by_year[year]))
    for start in range(0, len(months), 6):
        segment = months[start : start + 6]
        if segment:
            definitions.append(("half_year", f"{segment[0]}~{segment[-1]}", segment))
    return definitions


def _contribution_sensitivity_summary(
    backtest_rows: list[dict[str, object]],
    ranked: list[tuple[str, float, float, dict[str, object]]],
) -> dict[str, float]:
    """对少数极端月份做删月敏感性摘要。"""
    positive_sum = sum(max(value, 0.0) for _, value, _, _ in ranked)
    top3_positive = sum(max(value, 0.0) for _, value, _, _ in ranked[:3])
    best_months = {month for month, _, _, _ in ranked[:3]}
    worst_months = {month for month, _, _, _ in ranked[-3:]}
    without_best = [row for row in backtest_rows if str(row["execution_month"]) not in best_months]
    without_worst = [row for row in backtest_rows if str(row["execution_month"]) not in worst_months]
    return {
        "top3_positive_excess_share": round(top3_positive / positive_sum, 6) if positive_sum > 0 else 0.0,
        "cumulative_return_without_best3": summarize_backtest(without_best).get("cumulative_return", 0.0),
        "cumulative_return_without_worst3": summarize_backtest(without_worst).get("cumulative_return", 0.0),
        "excess_return_without_best3": summarize_backtest(without_best).get("excess_cumulative_return", 0.0),
    }


def _candidate_factor_fields(config: AppConfig) -> list[str]:
    """提取候选评分体系中真正参与打分的原子因子字段。"""
    fields: list[str] = []
    for factor_weights in config.ranking.category_factors.values():
        for field in factor_weights:
            if field not in fields:
                fields.append(field)
    return fields


def _factor_direction(field: str) -> str:
    """返回稳健性分析中应使用的因子方向。"""
    low_fields = {
        "downside_vol_12m",
        "asset_stability_12m",
        "asset_flow_volatility_12m",
        "drawdown_duration_ratio_12m",
        "manager_post_change_downside_vol_delta_12m",
        "manager_change_count_24m",
        "tail_loss_ratio_12m",
        "vol_12m",
    }
    return "low" if field in low_fields else "high"


def default_baseline_config_path(config_path: Path, data_source: str) -> Path:
    """根据当前候选配置推断默认 baseline 配置路径。"""
    candidate = config_path.resolve()
    baseline_name = f"{data_source}.json"
    baseline_path = candidate.parent / baseline_name
    if baseline_path.exists() and baseline_path != candidate:
        return baseline_path
    fallback = candidate.parent / "default.json"
    return fallback if fallback.exists() else candidate


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
