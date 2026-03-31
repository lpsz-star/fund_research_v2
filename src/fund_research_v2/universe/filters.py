from __future__ import annotations

from collections import defaultdict

from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.contracts import DatasetSnapshot, UniverseSnapshot
from fund_research_v2.common.date_utils import add_months, decision_date_for_month, month_diff


def build_universe(config: AppConfig, dataset: DatasetSnapshot) -> UniverseSnapshot:
    """按月评估每只基金是否满足基金池准入条件。"""
    nav_by_entity: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in dataset.fund_nav_monthly:
        nav_by_entity[str(row["entity_id"])].append(row)
    coverage_lookup = _daily_nav_coverage_lookup(
        dataset.fund_nav_daily_coverage_monthly,
        config.universe.daily_nav_coverage_lookback_months,
    )
    needs_daily_fallback = not coverage_lookup
    daily_nav_by_entity: dict[str, list[dict[str, object]]] = defaultdict(list)
    if needs_daily_fallback:
        for row in dataset.fund_nav_pit_daily:
            daily_nav_by_entity[str(row["entity_id"])].append(row)
    rows: list[dict[str, object]] = []
    trade_calendar_rows = dataset.trade_calendar
    open_trade_dates_by_month = _open_trade_dates_by_month(trade_calendar_rows)
    decision_date_by_month = {
        month: decision_date_for_month(month, trade_calendar_rows)
        for month in sorted({str(row["month"]) for row in dataset.fund_nav_monthly})
    }
    for entity in dataset.fund_entity_master:
        entity_id = str(entity["entity_id"])
        entity_nav = sorted(nav_by_entity.get(entity_id, []), key=lambda item: str(item["month"]))
        entity_daily_nav = sorted(daily_nav_by_entity.get(entity_id, []), key=lambda item: str(item.get("trade_date", ""))) if needs_daily_fallback else []
        visible_nav_rows: list[dict[str, object]] = []
        visible_index = 0
        for nav_row in entity_nav:
            month = str(nav_row["month"])
            decision_date = decision_date_by_month[month]
            reasons = []
            while visible_index < len(entity_nav):
                candidate_row = entity_nav[visible_index]
                candidate_month = str(candidate_row["month"])
                if candidate_month > month:
                    break
                if str(candidate_row["available_date"]) > decision_date:
                    break
                visible_nav_rows.append(candidate_row)
                visible_index += 1
            current_visible_row = visible_nav_rows[-1] if visible_nav_rows and str(visible_nav_rows[-1]["month"]) == month else None
            visible_history_months = len(visible_nav_rows)
            fund_age_months = month_diff(month, str(entity["inception_month"]))
            visible_assets_cny_mn = 0.0 if current_visible_row is None else float(current_visible_row["assets_cny_mn"])
            # 基金池输出需要保留原因码，方便审计每只基金在哪个月为何被剔除。
            if str(entity["primary_type"]) not in config.universe.allowed_primary_types:
                reasons.append("primary_type_excluded")
            if any(keyword in str(entity["entity_name"]) for keyword in config.universe.exclude_name_keywords):
                reasons.append("name_keyword_excluded")
            if int(str(entity.get("liquidity_restricted") or "0")) == 1:
                # 当前策略优先保证月频调仓流动性，因此最低持有期基金直接在基金池层剔除，而不是在回测里复杂模拟锁定期。
                reasons.append("holding_period_restricted")
            trailing_coverage = coverage_lookup.get((entity_id, month))
            if trailing_coverage is None:
                trailing_coverage = _trailing_daily_nav_coverage(
                    entity_daily_nav,
                    month,
                    decision_date,
                    open_trade_dates_by_month,
                    config.universe.daily_nav_coverage_lookback_months,
                )
            trailing_nav_coverage_ratio, trailing_nav_coverage_months = trailing_coverage
            if trailing_nav_coverage_months > 0 and trailing_nav_coverage_ratio < config.universe.min_daily_nav_coverage_ratio:
                # 这里刻意只看 decision_date 前已可见的历史日频覆盖率，避免把未来持有期缺失“倒灌”到当前信号。
                reasons.append("sparse_daily_nav_coverage")
            if current_visible_row is None:
                reasons.append("nav_not_available_by_decision_date")
            if visible_history_months < config.universe.min_history_months:
                reasons.append("insufficient_history")
            if current_visible_row is None or visible_assets_cny_mn < config.universe.min_assets_cny_mn:
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
                    "visible_history_months": visible_history_months,
                    "fund_age_months": fund_age_months,
                    "visible_assets_cny_mn": round(visible_assets_cny_mn, 3),
                    "nav_available_date": "" if current_visible_row is None else str(current_visible_row["available_date"]),
                    "decision_date": decision_date,
                    "trailing_daily_nav_coverage_ratio": round(trailing_nav_coverage_ratio, 6),
                    "trailing_daily_nav_coverage_months": trailing_nav_coverage_months,
                }
            )
    return UniverseSnapshot(
        rows=rows,
        metadata={
            "eligible_rows": sum(int(row["is_eligible"]) for row in rows),
            "total_rows": len(rows),
        },
    )


def _daily_nav_coverage_lookup(
    coverage_rows: list[dict[str, object]],
    lookback_months: int,
) -> dict[tuple[str, str], tuple[float, int]]:
    """把预计算覆盖率月表转成基金池使用的快速查找结构。"""
    lookup: dict[tuple[str, str], tuple[float, int]] = {}
    for row in coverage_rows:
        if int(str(row.get("lookback_months") or "0")) != lookback_months:
            continue
        entity_id = str(row.get("entity_id") or "")
        month = str(row.get("month") or "")
        if not entity_id or not month:
            continue
        lookup[(entity_id, month)] = (
            float(str(row.get("trailing_daily_nav_coverage_ratio") or "0") or 0.0),
            int(str(row.get("trailing_daily_nav_coverage_months") or "0")),
        )
    return lookup


def _open_trade_dates_by_month(trade_calendar_rows: list[dict[str, object]]) -> dict[str, set[str]]:
    """构建每个月的开市日集合，供日频净值覆盖率审计使用。"""
    by_month: dict[str, set[str]] = defaultdict(set)
    for row in trade_calendar_rows:
        if int(str(row.get("is_open") or "0")) != 1:
            continue
        trade_date = str(row.get("cal_date") or "")
        if not trade_date:
            continue
        by_month[trade_date[:7]].add(trade_date)
    return by_month


def _trailing_daily_nav_coverage(
    entity_daily_nav: list[dict[str, object]],
    month: str,
    decision_date: str,
    open_trade_dates_by_month: dict[str, set[str]],
    lookback_months: int,
) -> tuple[float, int]:
    """只用当前决策日前可见的历史日频净值，估算基金过去一段时间的披露稠密度。"""
    if not entity_daily_nav or not open_trade_dates_by_month:
        return 0.0, 0
    visible_daily_rows = [
        row
        for row in entity_daily_nav
        if str(row.get("trade_date") or "")[:7] <= month and str(row.get("available_date") or "") <= decision_date
    ]
    if not visible_daily_rows:
        return 0.0, 0
    visible_days_by_month: dict[str, set[str]] = defaultdict(set)
    for row in visible_daily_rows:
        trade_date = str(row.get("trade_date") or "")
        if trade_date:
            visible_days_by_month[trade_date[:7]].add(trade_date)
    scoped_months = [add_months(month, -offset) for offset in range(lookback_months - 1, -1, -1)]
    coverage_values: list[float] = []
    for scoped_month in scoped_months:
        open_days = open_trade_dates_by_month.get(scoped_month, set())
        visible_days = visible_days_by_month.get(scoped_month, set())
        if not open_days or not visible_days:
            continue
        coverage_values.append(len(visible_days) / len(open_days))
    if not coverage_values:
        return 0.0, 0
    return sum(coverage_values) / len(coverage_values), len(coverage_values)
