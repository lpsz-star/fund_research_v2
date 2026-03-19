from __future__ import annotations

from collections import defaultdict

from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.contracts import DatasetSnapshot, UniverseSnapshot
from fund_research_v2.common.date_utils import month_diff


def build_universe(config: AppConfig, dataset: DatasetSnapshot) -> UniverseSnapshot:
    """按月评估每只基金是否满足基金池准入条件。"""
    nav_by_entity: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in dataset.fund_nav_monthly:
        nav_by_entity[str(row["entity_id"])].append(row)
    rows: list[dict[str, object]] = []
    for entity in dataset.fund_entity_master:
        entity_id = str(entity["entity_id"])
        entity_nav = sorted(nav_by_entity.get(entity_id, []), key=lambda item: str(item["month"]))
        history_count = 0
        for nav_row in entity_nav:
            history_count += 1
            month = str(nav_row["month"])
            reasons = []
            # 基金池输出需要保留原因码，方便审计每只基金在哪个月为何被剔除。
            if str(entity["primary_type"]) not in config.universe.allowed_primary_types:
                reasons.append("primary_type_excluded")
            if any(keyword in str(entity["entity_name"]) for keyword in config.universe.exclude_name_keywords):
                reasons.append("name_keyword_excluded")
            if history_count < config.universe.min_history_months:
                reasons.append("insufficient_history")
            if month_diff(month, str(entity["inception_month"])) < config.universe.min_fund_age_months:
                reasons.append("fund_too_new")
            if float(nav_row["assets_cny_mn"]) < config.universe.min_assets_cny_mn:
                reasons.append("assets_below_threshold")
            # 基金池是逐月构建的，而不是对基金打一个永久标签；同一只基金可以在不同月份进出基金池。
            rows.append(
                {
                    "entity_id": entity_id,
                    "month": month,
                    "is_eligible": 0 if reasons else 1,
                    "reason_codes": "|".join(reasons) if reasons else "eligible",
                    "fund_company": entity["fund_company"],
                    "primary_type": entity["primary_type"],
                }
            )
    return UniverseSnapshot(
        rows=rows,
        metadata={
            "eligible_rows": sum(int(row["is_eligible"]) for row in rows),
            "total_rows": len(rows),
        },
    )
