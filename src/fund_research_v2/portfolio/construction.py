from __future__ import annotations

from collections import Counter

from fund_research_v2.common.config import AppConfig


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
