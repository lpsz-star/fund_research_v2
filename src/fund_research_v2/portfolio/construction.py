from __future__ import annotations

from collections import Counter

from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.date_utils import is_rebalance_month


def build_portfolio(config: AppConfig, score_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """根据评分结果和约束构建单期目标组合。"""
    ordered = sorted(score_rows, key=lambda item: float(item["total_score"]), reverse=True)
    selected = []
    company_counter: Counter[str] = Counter()
    for row in ordered:
        company = str(row["fund_company"])
        # 当前先用简单公司分散约束，避免组合过度集中到同一家基金公司。
        if company_counter[company] >= config.portfolio.single_company_max:
            continue
        selected.append(row)
        company_counter[company] += 1
        if len(selected) >= config.portfolio.portfolio_size:
            break
    if not selected:
        return []
    # 当前默认等权，是为了让组合表现更多反映选基质量，而不是被复杂权重优化器主导。
    raw_weight = min(1.0 / len(selected), config.portfolio.single_fund_cap)
    portfolio = []
    for row in selected:
        portfolio.append(
            {
                "month": row["month"],
                "entity_id": row["entity_id"],
                "entity_name": row["entity_name"],
                "fund_company": row["fund_company"],
                "rank": row["rank"],
                "total_score": row["total_score"],
                "target_weight": round(raw_weight, 6),
            }
        )
    residual = round(1.0 - sum(float(row["target_weight"]) for row in portfolio), 6)
    index = 0
    # 若单基金上限导致等权后总权重不足 1，则顺序补足剩余权重，保持组合总权重尽量接近满仓。
    while residual > 0.000001 and portfolio:
        room = round(config.portfolio.single_fund_cap - float(portfolio[index]["target_weight"]), 6)
        if room > 0:
            step = min(room, residual)
            portfolio[index]["target_weight"] = round(float(portfolio[index]["target_weight"]) + step, 6)
            residual = round(residual - step, 6)
        index = (index + 1) % len(portfolio)
        if index == 0 and all(float(item["target_weight"]) >= config.portfolio.single_fund_cap for item in portfolio):
            break
    return portfolio


def build_portfolio_trajectory(
    config: AppConfig,
    score_rows: list[dict[str, object]],
    months: list[str] | None = None,
) -> list[dict[str, object]]:
    """构建逐月组合轨迹，让组合、回测和稳健性共享同一调仓语义。"""
    months_to_build = sorted(set(months or [str(row.get("month") or "") for row in score_rows if str(row.get("month") or "")]))
    if not months_to_build:
        return []
    scores_by_month: dict[str, list[dict[str, object]]] = {}
    for month in months_to_build:
        scores_by_month[month] = [row for row in score_rows if str(row.get("month") or "") == month]

    trajectory: list[dict[str, object]] = []
    prior_template: list[dict[str, object]] = []
    prior_signal_month = ""
    frequency = config.portfolio.rebalance_frequency

    for month in months_to_build:
        rebalance_flag = is_rebalance_month(month, frequency)
        if rebalance_flag:
            prior_template = build_portfolio(config, scores_by_month.get(month, []))
            prior_signal_month = month
            month_rows = _annotate_portfolio_rows(
                prior_template,
                month=month,
                source_signal_month=month,
                rebalance_frequency=frequency,
                rebalance_flag=1,
                generation_mode="rebalance_new",
            )
        else:
            month_rows = _annotate_portfolio_rows(
                prior_template,
                month=month,
                source_signal_month=prior_signal_month,
                rebalance_frequency=frequency,
                rebalance_flag=0,
                generation_mode="carry_forward",
            )
        trajectory.extend(month_rows)
    return trajectory


def _annotate_portfolio_rows(
    template_rows: list[dict[str, object]],
    *,
    month: str,
    source_signal_month: str,
    rebalance_frequency: str,
    rebalance_flag: int,
    generation_mode: str,
) -> list[dict[str, object]]:
    """把单期组合模板映射成某个月实际生效的组合轨迹行。"""
    rows: list[dict[str, object]] = []
    for row in template_rows:
        annotated = dict(row)
        annotated["month"] = month
        annotated["source_signal_month"] = source_signal_month
        annotated["is_rebalance_month"] = rebalance_flag
        annotated["rebalance_frequency"] = rebalance_frequency
        annotated["portfolio_generation_mode"] = generation_mode
        rows.append(annotated)
    return rows
