from __future__ import annotations

from collections import defaultdict

from fund_research_v2.common.date_utils import add_months, decision_date_for_month


def build_daily_nav_coverage_monthly(
    nav_monthly_rows: list[dict[str, object]],
    nav_daily_rows: list[dict[str, object]],
    trade_calendar_rows: list[dict[str, object]],
    lookback_months: int,
) -> list[dict[str, object]]:
    """预计算逐实体逐月的历史日频净值覆盖率月表。"""
    if lookback_months <= 0 or not nav_monthly_rows or not trade_calendar_rows:
        return []
    open_day_count_by_month = _open_day_count_by_month(trade_calendar_rows)
    if not open_day_count_by_month:
        return []

    months_by_entity: dict[str, list[str]] = defaultdict(list)
    for row in nav_monthly_rows:
        entity_id = str(row.get("entity_id") or "")
        month = str(row.get("month") or "")
        if entity_id and month:
            months_by_entity[entity_id].append(month)

    daily_rows_by_entity: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in nav_daily_rows:
        entity_id = str(row.get("entity_id") or "")
        trade_date = str(row.get("trade_date") or "")
        available_date = str(row.get("available_date") or "")
        if entity_id and trade_date and available_date:
            daily_rows_by_entity[entity_id].append(
                {
                    "trade_date": trade_date,
                    "available_date": available_date,
                }
            )

    coverage_rows: list[dict[str, object]] = []
    for entity_id, months in months_by_entity.items():
        scoped_months = sorted(set(months))
        entity_daily_rows = sorted(
            daily_rows_by_entity.get(entity_id, []),
            key=lambda item: (item["available_date"], item["trade_date"]),
        )
        next_visible_index = 0
        visible_trade_dates_by_month: dict[str, set[str]] = defaultdict(set)
        for month in scoped_months:
            decision_date = decision_date_for_month(month, trade_calendar_rows)
            while next_visible_index < len(entity_daily_rows):
                daily_row = entity_daily_rows[next_visible_index]
                if daily_row["available_date"] > decision_date:
                    break
                trade_date = daily_row["trade_date"]
                trade_month = trade_date[:7]
                if trade_month <= month:
                    visible_trade_dates_by_month[trade_month].add(trade_date)
                next_visible_index += 1

            coverage_ratio, observed_months = _compute_trailing_coverage(
                month=month,
                lookback_months=lookback_months,
                open_day_count_by_month=open_day_count_by_month,
                visible_trade_dates_by_month=visible_trade_dates_by_month,
            )
            coverage_rows.append(
                {
                    "entity_id": entity_id,
                    "month": month,
                    "decision_date": decision_date,
                    "lookback_months": lookback_months,
                    "trailing_daily_nav_coverage_ratio": round(coverage_ratio, 6),
                    "trailing_daily_nav_coverage_months": observed_months,
                }
            )
    return coverage_rows


def _open_day_count_by_month(trade_calendar_rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in trade_calendar_rows:
        if int(str(row.get("is_open") or "0")) != 1:
            continue
        trade_date = str(row.get("cal_date") or "")
        if trade_date:
            counts[trade_date[:7]] += 1
    return counts


def _compute_trailing_coverage(
    month: str,
    lookback_months: int,
    open_day_count_by_month: dict[str, int],
    visible_trade_dates_by_month: dict[str, set[str]],
) -> tuple[float, int]:
    coverage_values: list[float] = []
    for offset in range(lookback_months - 1, -1, -1):
        scoped_month = add_months(month, -offset)
        open_day_count = open_day_count_by_month.get(scoped_month, 0)
        visible_day_count = len(visible_trade_dates_by_month.get(scoped_month, set()))
        if open_day_count <= 0 or visible_day_count <= 0:
            continue
        coverage_values.append(visible_day_count / open_day_count)
    if not coverage_values:
        return 0.0, 0
    return sum(coverage_values) / len(coverage_values), len(coverage_values)
