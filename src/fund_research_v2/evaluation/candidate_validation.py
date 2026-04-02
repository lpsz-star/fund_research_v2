from __future__ import annotations

from collections import defaultdict

from fund_research_v2.backtest.engine import BacktestExecutionCache, run_backtest
from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.contracts import DatasetSnapshot
from fund_research_v2.evaluation.metrics import summarize_backtest


def build_candidate_validation(
    *,
    candidate_config: AppConfig,
    baseline_config: AppConfig,
    dataset: DatasetSnapshot,
    candidate_score_rows: list[dict[str, object]],
    baseline_score_rows: list[dict[str, object]],
    candidate_execution_cache: BacktestExecutionCache | None = None,
    baseline_execution_cache: BacktestExecutionCache | None = None,
) -> dict[str, object]:
    """构建候选评分体系升级 baseline 前的最小补充验证结果。"""
    candidate_backtest_rows, _ = run_backtest(
        config=candidate_config,
        score_rows=candidate_score_rows,
        nav_rows=dataset.fund_nav_monthly,
        benchmark_rows=dataset.benchmark_monthly,
        trade_calendar_rows=dataset.trade_calendar,
        nav_daily_rows=dataset.fund_nav_pit_daily,
        prepared_execution_cache=candidate_execution_cache,
    )
    baseline_backtest_rows, _ = run_backtest(
        config=baseline_config,
        score_rows=baseline_score_rows,
        nav_rows=dataset.fund_nav_monthly,
        benchmark_rows=dataset.benchmark_monthly,
        trade_calendar_rows=dataset.trade_calendar,
        nav_daily_rows=dataset.fund_nav_pit_daily,
        prepared_execution_cache=baseline_execution_cache,
    )
    style_phase_detail_rows = _build_style_phase_detail_rows(
        candidate_backtest_rows=candidate_backtest_rows,
        baseline_backtest_rows=baseline_backtest_rows,
        benchmark_rows=dataset.benchmark_monthly,
    )
    style_phase_window_rows, style_phase_stability_summary = _build_style_phase_window_rows(style_phase_detail_rows)
    style_phase_summary_rows, style_phase_summary = _build_style_phase_summary(
        detail_rows=style_phase_detail_rows,
        window_rows=style_phase_window_rows,
        stability_summary=style_phase_stability_summary,
    )
    attribution_monthly_rows, attribution_summary = _build_excess_attribution_rows(
        candidate_backtest_rows=candidate_backtest_rows,
        baseline_backtest_rows=baseline_backtest_rows,
    )
    summary = _build_candidate_validation_summary(
        candidate_config=candidate_config,
        baseline_config=baseline_config,
        style_phase_summary=style_phase_summary,
        attribution_summary=attribution_summary,
        candidate_backtest_rows=candidate_backtest_rows,
        baseline_backtest_rows=baseline_backtest_rows,
    )
    return {
        "summary": summary,
        "style_phase_summary_rows": style_phase_summary_rows,
        "style_phase_detail_rows": style_phase_detail_rows,
        "style_phase_window_rows": style_phase_window_rows,
        "style_phase_summary": style_phase_summary,
        "style_phase_stability_summary": style_phase_stability_summary,
        "attribution_monthly_rows": attribution_monthly_rows,
        "attribution_summary": attribution_summary,
    }


def _build_style_phase_detail_rows(
    *,
    candidate_backtest_rows: list[dict[str, object]],
    baseline_backtest_rows: list[dict[str, object]],
    benchmark_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """生成按月阶段标签明细，回答候选胜出是否集中在少数阶段。"""
    candidate_map = {str(row["execution_month"]): row for row in candidate_backtest_rows}
    baseline_map = {str(row["execution_month"]): row for row in baseline_backtest_rows}
    benchmark_lookup: dict[str, dict[str, float]] = defaultdict(dict)
    for row in benchmark_rows:
        benchmark_lookup[str(row.get("benchmark_key", ""))][str(row["month"])] = float(row.get("benchmark_return_1m", 0.0))
    months = sorted(set(candidate_map) & set(baseline_map))
    rows: list[dict[str, object]] = []
    previous_broad_return = 0.0
    for month in months:
        candidate_row = candidate_map[month]
        baseline_row = baseline_map[month]
        broad_return = benchmark_lookup.get("broad_equity", {}).get(month, float(candidate_row.get("benchmark_return", 0.0)))
        large_cap_return = benchmark_lookup.get("large_cap_equity", {}).get(month, broad_return)
        candidate_excess = round(float(candidate_row["portfolio_return_net"]) - float(candidate_row["benchmark_return"]), 6)
        baseline_excess = round(float(baseline_row["portfolio_return_net"]) - float(baseline_row["benchmark_return"]), 6)
        excess_delta = round(candidate_excess - baseline_excess, 6)
        rows.append(
            {
                "execution_month": month,
                "broad_equity_return": round(broad_return, 6),
                "large_cap_equity_return": round(large_cap_return, 6),
                "market_direction": "market_up" if broad_return >= 0 else "market_down",
                "size_leadership": "large_cap_lead" if large_cap_return >= broad_return else "broad_equity_lead",
                "rebound_state": _rebound_state(previous_broad_return, broad_return),
                "baseline_excess_return": baseline_excess,
                "candidate_excess_return": candidate_excess,
                "excess_delta": excess_delta,
                "candidate_win_flag": 1 if excess_delta > 0 else 0,
            }
        )
        previous_broad_return = broad_return
    return rows


def _build_style_phase_window_rows(detail_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    """生成 rolling 窗口视角，回答候选优势是否集中在少数连续窗口。"""
    rows: list[dict[str, object]] = []
    windows = [6, 12]
    for window_size in windows:
        if len(detail_rows) < window_size:
            continue
        for start in range(len(detail_rows) - window_size + 1):
            scoped = detail_rows[start : start + window_size]
            delta_sum = round(sum(float(row["excess_delta"]) for row in scoped), 6)
            rows.append(
                {
                    "window_type": f"rolling_{window_size}m",
                    "start_month": str(scoped[0]["execution_month"]),
                    "end_month": str(scoped[-1]["execution_month"]),
                    "month_count": window_size,
                    "baseline_excess_return": round(sum(float(row["baseline_excess_return"]) for row in scoped), 6),
                    "candidate_excess_return": round(sum(float(row["candidate_excess_return"]) for row in scoped), 6),
                    "excess_delta": delta_sum,
                    "candidate_win_flag": 1 if delta_sum > 0 else 0,
                }
            )
    material_rows = [row for row in rows if row["window_type"] == "rolling_12m"] or rows
    positive_rows = [row for row in material_rows if float(row["excess_delta"]) > 0]
    positive_delta_sum = round(sum(float(row["excess_delta"]) for row in positive_rows), 6)
    strongest = max(positive_rows, key=lambda row: float(row["excess_delta"]), default=None)
    strongest_share = (
        round(float(strongest["excess_delta"]) / positive_delta_sum, 6)
        if strongest is not None and positive_delta_sum > 0
        else 0.0
    )
    positive_ratio = round(sum(int(row["candidate_win_flag"]) for row in material_rows) / len(material_rows), 6) if material_rows else 0.0
    if strongest_share >= 0.5:
        window_assessment = "window_concentrated"
    elif positive_ratio >= 0.6:
        window_assessment = "window_broad"
    else:
        window_assessment = "window_mixed"
    return rows, {
        "window_assessment": window_assessment,
        "material_window_type": material_rows[0]["window_type"] if material_rows else "",
        "material_window_count": len(material_rows),
        "positive_window_ratio": positive_ratio,
        "strongest_positive_window": (
            f"{strongest['start_month']}~{strongest['end_month']}" if strongest is not None else ""
        ),
        "strongest_positive_window_delta": round(float(strongest["excess_delta"]), 6) if strongest is not None else 0.0,
        "strongest_positive_window_share": strongest_share,
    }


def _build_style_phase_summary(
    *,
    detail_rows: list[dict[str, object]],
    window_rows: list[dict[str, object]],
    stability_summary: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """把阶段明细聚合成可评审的阶段摘要表与阶段结论。"""
    summary_rows: list[dict[str, object]] = []
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in detail_rows:
        for dimension in ["market_direction", "size_leadership", "rebound_state"]:
            grouped[(dimension, str(row[dimension]))].append(row)
    positive_deltas: list[float] = []
    material_phase_wins = 0
    material_phase_count = 0
    for (dimension, label), rows in sorted(grouped.items()):
        month_count = len(rows)
        baseline_excess_sum = round(sum(float(row["baseline_excess_return"]) for row in rows), 6)
        candidate_excess_sum = round(sum(float(row["candidate_excess_return"]) for row in rows), 6)
        delta = round(candidate_excess_sum - baseline_excess_sum, 6)
        if month_count >= 3:
            material_phase_count += 1
            if delta > 0:
                material_phase_wins += 1
        if delta > 0:
            positive_deltas.append(delta)
        summary_rows.append(
            {
                "phase_dimension": dimension,
                "phase_label": label,
                "month_count": month_count,
                "baseline_excess_return": baseline_excess_sum,
                "candidate_excess_return": candidate_excess_sum,
                "excess_delta": delta,
                "candidate_win_flag": 1 if delta > 0 else 0,
            }
        )
    positive_delta_sum = round(sum(positive_deltas), 6)
    max_positive_share = round(max(positive_deltas) / positive_delta_sum, 6) if positive_delta_sum > 0 else 0.0
    window_assessment = str(stability_summary.get("window_assessment", "window_mixed"))
    if positive_delta_sum <= 0 or material_phase_wins <= 1 or max_positive_share >= 0.65:
        assessment = "highly_concentrated"
    elif window_assessment == "window_concentrated":
        assessment = "window_concentrated"
    elif material_phase_count and material_phase_wins / material_phase_count >= 0.6 and max_positive_share < 0.5:
        assessment = "broadly_distributed"
    else:
        assessment = "partially_concentrated"
    conclusion = {
        "broadly_distributed": "候选配置的相对胜出分布在多数关键阶段，不属于单一风格集中。",
        "partially_concentrated": "候选配置的相对胜出并非只发生在单一阶段，但仍存在一定风格集中，需要结合归因结果一起判断。",
        "window_concentrated": "候选配置的相对胜出并不只落在单一风格标签上，但仍明显集中在少数连续窗口，当前不建议直接升级 baseline。",
        "highly_concentrated": "候选配置的相对胜出主要集中在少数阶段，当前不支持直接升级 baseline。",
    }[assessment]
    return summary_rows, {
        "style_phase_assessment": assessment,
        "material_phase_count": material_phase_count,
        "material_phase_win_count": material_phase_wins,
        "positive_excess_delta_sum": positive_delta_sum,
        "max_positive_phase_share": max_positive_share,
        "window_assessment": window_assessment,
        "material_window_count": stability_summary.get("material_window_count", 0),
        "positive_window_ratio": stability_summary.get("positive_window_ratio", 0.0),
        "strongest_positive_window": stability_summary.get("strongest_positive_window", ""),
        "strongest_positive_window_delta": stability_summary.get("strongest_positive_window_delta", 0.0),
        "strongest_positive_window_share": stability_summary.get("strongest_positive_window_share", 0.0),
        "conclusion": conclusion,
    }


def _build_excess_attribution_rows(
    *,
    candidate_backtest_rows: list[dict[str, object]],
    baseline_backtest_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """把候选相对 baseline 的收益变化拆成 benchmark 驱动与 selection 驱动。"""
    candidate_map = {str(row["execution_month"]): row for row in candidate_backtest_rows}
    baseline_map = {str(row["execution_month"]): row for row in baseline_backtest_rows}
    months = sorted(set(candidate_map) & set(baseline_map))
    rows: list[dict[str, object]] = []
    total_delta_sum = 0.0
    benchmark_driven_sum = 0.0
    selection_driven_sum = 0.0
    for month in months:
        candidate_row = candidate_map[month]
        baseline_row = baseline_map[month]
        candidate_net = float(candidate_row["portfolio_return_net"])
        baseline_net = float(baseline_row["portfolio_return_net"])
        candidate_benchmark = float(candidate_row["benchmark_return"])
        baseline_benchmark = float(baseline_row["benchmark_return"])
        candidate_excess = candidate_net - candidate_benchmark
        baseline_excess = baseline_net - baseline_benchmark
        total_delta = candidate_net - baseline_net
        benchmark_driven_delta = candidate_benchmark - baseline_benchmark
        selection_driven_delta = candidate_excess - baseline_excess
        total_delta_sum += total_delta
        benchmark_driven_sum += benchmark_driven_delta
        selection_driven_sum += selection_driven_delta
        rows.append(
            {
                "execution_month": month,
                "baseline_excess_return": round(baseline_excess, 6),
                "candidate_excess_return": round(candidate_excess, 6),
                "total_return_delta": round(total_delta, 6),
                "benchmark_driven_delta": round(benchmark_driven_delta, 6),
                "selection_driven_delta": round(selection_driven_delta, 6),
            }
        )
    total_delta_sum = round(total_delta_sum, 6)
    benchmark_driven_sum = round(benchmark_driven_sum, 6)
    selection_driven_sum = round(selection_driven_sum, 6)
    selection_share = round(selection_driven_sum / total_delta_sum, 6) if total_delta_sum != 0 else 0.0
    benchmark_share = round(benchmark_driven_sum / total_delta_sum, 6) if total_delta_sum != 0 else 0.0
    if selection_driven_sum > 0 and abs(selection_share) >= 0.6:
        assessment = "selection_dominant"
    elif benchmark_driven_sum > 0 and abs(benchmark_share) >= 0.6:
        assessment = "beta_dominant"
    else:
        assessment = "mixed"
    conclusion = {
        "selection_dominant": "候选配置相对 baseline 的收益改善主要来自 selection-driven excess，benchmark 驱动不是主因。",
        "mixed": "候选配置相对 baseline 的收益改善同时包含 selection 与 benchmark 驱动，当前仍需结合阶段表现谨慎判断。",
        "beta_dominant": "候选配置相对 baseline 的收益改善主要可由 benchmark 驱动解释，当前不适合直接升级 baseline。",
    }[assessment]
    return rows, {
        "attribution_assessment": assessment,
        "total_return_delta_sum": total_delta_sum,
        "benchmark_driven_delta_sum": benchmark_driven_sum,
        "selection_driven_delta_sum": selection_driven_sum,
        "benchmark_driven_share": benchmark_share,
        "selection_driven_share": selection_share,
        "conclusion": conclusion,
    }


def _build_candidate_validation_summary(
    *,
    candidate_config: AppConfig,
    baseline_config: AppConfig,
    style_phase_summary: dict[str, object],
    attribution_summary: dict[str, object],
    candidate_backtest_rows: list[dict[str, object]],
    baseline_backtest_rows: list[dict[str, object]],
) -> dict[str, object]:
    """汇总 A/B 两项验证，输出第二轮 baseline 评审可直接引用的判断。"""
    candidate_summary = summarize_backtest(candidate_backtest_rows)
    baseline_summary = summarize_backtest(baseline_backtest_rows)
    style_assessment = str(style_phase_summary.get("style_phase_assessment", "partially_concentrated"))
    attribution_assessment = str(attribution_summary.get("attribution_assessment", "mixed"))
    ready_for_review = style_assessment == "broadly_distributed" and attribution_assessment == "selection_dominant"
    recommended_decision = "ready_for_baseline_review" if ready_for_review else "keep_candidate_pending_more_validation"
    rationale = [
        str(style_phase_summary.get("conclusion", "")),
        str(attribution_summary.get("conclusion", "")),
    ]
    return {
        "candidate_config": str(candidate_config.data_source),
        "baseline_config": str(baseline_config.data_source),
        "candidate_excess_cumulative_return": candidate_summary.get("excess_cumulative_return", 0.0),
        "baseline_excess_cumulative_return": baseline_summary.get("excess_cumulative_return", 0.0),
        "style_phase_assessment": style_assessment,
        "excess_attribution_assessment": attribution_assessment,
        "recommended_decision": recommended_decision,
        "decision_rationale": rationale,
    }


def _rebound_state(previous_broad_return: float, current_broad_return: float) -> str:
    """用最小阶段标签区分延续下跌、反弹和其他月份。"""
    if previous_broad_return < 0 <= current_broad_return:
        return "rebound_window"
    if previous_broad_return < 0 and current_broad_return < 0:
        return "drawdown_window"
    return "neutral_window"
