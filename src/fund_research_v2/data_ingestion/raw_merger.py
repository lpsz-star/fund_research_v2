from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fund_research_v2.common.config import AppConfig, benchmark_to_serializable_dict
from fund_research_v2.common.contracts import DatasetSnapshot
from fund_research_v2.common.date_utils import add_months, current_timestamp, month_end
from fund_research_v2.data_processing.daily_nav_coverage import build_daily_nav_coverage_monthly


def merge_tushare_incremental_snapshot(
    *,
    config: AppConfig,
    primary_dataset: DatasetSnapshot,
    incremental_dataset: DatasetSnapshot,
    target_month: str,
    window_start: str,
    window_end: str,
    temp_raw_dir: Path,
) -> tuple[DatasetSnapshot, dict[str, object]]:
    """把月份增量快照按主键 upsert 回主 raw，并重建依赖衍生表。"""
    merged_tables: dict[str, list[dict[str, object]]] = {}
    merge_stats: dict[str, dict[str, int]] = {}
    merge_plan = {
        "fund_entity_master": ("entity_id",),
        "fund_share_class_map": ("entity_id", "share_class_id"),
        "fund_nav_monthly": ("entity_id", "month"),
        "fund_nav_pit_daily": ("entity_id", "trade_date"),
        "benchmark_monthly": ("benchmark_key", "month"),
        "manager_assignment_monthly": ("entity_id", "month"),
        "fund_type_audit": ("entity_id",),
        "fund_liquidity_audit": ("entity_id",),
        "trade_calendar": ("exchange", "cal_date"),
    }
    for table_name, key_fields in merge_plan.items():
        merged_rows, stats = _upsert_rows(
            getattr(primary_dataset, table_name),
            getattr(incremental_dataset, table_name),
            key_fields,
        )
        merged_tables[table_name] = merged_rows
        merge_stats[table_name] = stats

    coverage_rows = build_daily_nav_coverage_monthly(
        nav_monthly_rows=merged_tables["fund_nav_monthly"],
        nav_daily_rows=merged_tables["fund_nav_pit_daily"],
        trade_calendar_rows=merged_tables["trade_calendar"],
        lookback_months=config.universe.daily_nav_coverage_lookback_months,
    )
    month_set = sorted({str(row.get("month") or "") for row in merged_tables["fund_nav_monthly"] if str(row.get("month") or "")})
    merged_metadata = _build_merged_metadata(
        config=config,
        primary_metadata=primary_dataset.metadata,
        incremental_metadata=incremental_dataset.metadata,
        merged_tables=merged_tables,
        coverage_rows=coverage_rows,
        target_month=target_month,
        window_start=window_start,
        window_end=window_end,
        temp_raw_dir=temp_raw_dir,
        merge_stats=merge_stats,
        month_set=month_set,
    )
    merged_dataset = DatasetSnapshot(
        fund_entity_master=merged_tables["fund_entity_master"],
        fund_share_class_map=merged_tables["fund_share_class_map"],
        fund_nav_monthly=merged_tables["fund_nav_monthly"],
        benchmark_monthly=merged_tables["benchmark_monthly"],
        manager_assignment_monthly=merged_tables["manager_assignment_monthly"],
        fund_type_audit=merged_tables["fund_type_audit"],
        metadata=merged_metadata,
        fund_liquidity_audit=merged_tables["fund_liquidity_audit"],
        trade_calendar=merged_tables["trade_calendar"],
        fund_nav_pit_daily=merged_tables["fund_nav_pit_daily"],
        fund_nav_daily_coverage_monthly=coverage_rows,
    )
    summary = {
        "merged_at": current_timestamp(),
        "target_month": target_month,
        "window_start": window_start,
        "window_end": window_end,
        "temp_raw_dir": str(temp_raw_dir),
        "merge_mode": "upsert",
        "table_stats": merge_stats,
        "coverage_row_count": len(coverage_rows),
        "entity_count": len(merged_tables["fund_entity_master"]),
        "share_class_count": len(merged_tables["fund_share_class_map"]),
        "month_range": merged_metadata.get("month_range", {}),
    }
    return merged_dataset, summary


def incremental_window_for_target_month(target_month: str) -> tuple[str, str]:
    """返回目标月 merge 所需的最小安全抓取窗口。"""
    previous_month = add_months(target_month, -1)
    return f"{previous_month}-01", month_end(target_month)


def _upsert_rows(
    primary_rows: list[dict[str, object]],
    incremental_rows: list[dict[str, object]],
    key_fields: tuple[str, ...],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """按主键把增量行覆盖进主表，并保留稳定顺序。"""
    merged: list[dict[str, object]] = []
    incremental_lookup: dict[tuple[str, ...], dict[str, object]] = {}
    for row in incremental_rows:
        incremental_lookup[_row_key(row, key_fields)] = dict(row)
    updated = 0
    seen_keys: set[tuple[str, ...]] = set()
    for row in primary_rows:
        key = _row_key(row, key_fields)
        replacement = incremental_lookup.get(key)
        if replacement is not None:
            merged.append(replacement)
            updated += 1
            seen_keys.add(key)
        else:
            merged.append(dict(row))
            seen_keys.add(key)
    inserted = 0
    for row in incremental_rows:
        key = _row_key(row, key_fields)
        if key in seen_keys:
            continue
        merged.append(dict(row))
        inserted += 1
    return merged, {
        "primary_rows": len(primary_rows),
        "incremental_rows": len(incremental_rows),
        "updated_rows": updated,
        "inserted_rows": inserted,
        "final_rows": len(merged),
    }


def _row_key(row: dict[str, object], key_fields: tuple[str, ...]) -> tuple[str, ...]:
    """把任意行按给定主键字段编码成稳定键。"""
    return tuple(str(row.get(field) or "") for field in key_fields)


def _build_merged_metadata(
    *,
    config: AppConfig,
    primary_metadata: dict[str, object],
    incremental_metadata: dict[str, object],
    merged_tables: dict[str, list[dict[str, object]]],
    coverage_rows: list[dict[str, object]],
    target_month: str,
    window_start: str,
    window_end: str,
    temp_raw_dir: Path,
    merge_stats: dict[str, dict[str, int]],
    month_set: list[str],
) -> dict[str, object]:
    """基于 merge 后的数据重建 raw snapshot metadata。"""
    metadata = dict(primary_metadata)
    if not metadata:
        metadata = dict(incremental_metadata)
    metadata["generated_at"] = current_timestamp()
    metadata["entity_count"] = len(merged_tables["fund_entity_master"])
    metadata["share_class_count"] = len(merged_tables["fund_share_class_map"])
    metadata["requested_max_funds"] = config.tushare.max_funds
    metadata["month_range"] = {
        "start": month_set[0] if month_set else None,
        "end": month_set[-1] if month_set else None,
    }
    metadata["benchmark_config"] = benchmark_to_serializable_dict(config.benchmark)
    metadata["benchmark_name"] = config.benchmark.series_for_key(config.benchmark.default_key).name
    metadata["benchmark_source"] = config.benchmark.source
    metadata["benchmark_ts_code"] = config.benchmark.series_for_key(config.benchmark.default_key).ts_code
    metadata["benchmark_default_key"] = config.benchmark.default_key
    metadata["benchmark_series"] = {
        key: {"name": series.name, "ts_code": series.ts_code}
        for key, series in config.benchmark.series.items()
    }
    metadata["benchmark_primary_type_map"] = config.benchmark.primary_type_map
    metadata["entity_asset_aggregation"] = "sum_of_share_classes"
    metadata["nav_monthly_anchor"] = "month_last_trading_day"
    metadata["trade_calendar"] = {
        "source": "tushare_trade_cal",
        "exchange": "SSE",
        "start_date": merged_tables["trade_calendar"][0]["cal_date"] if merged_tables["trade_calendar"] else "",
        "end_date": merged_tables["trade_calendar"][-1]["cal_date"] if merged_tables["trade_calendar"] else "",
        "open_day_count": sum(int(str(row.get("is_open") or "0")) for row in merged_tables["trade_calendar"]),
    }
    metadata["daily_nav_coverage_monthly"] = {
        "lookback_months": config.universe.daily_nav_coverage_lookback_months,
        "row_count": len(coverage_rows),
        "source": "precomputed_from_fund_nav_pit_daily",
    }
    metadata["fund_type_audit_summary"] = {
        "entity_count": len(merged_tables["fund_type_audit"]),
        "by_primary_type": _count_by_field(merged_tables["fund_type_audit"], "primary_type"),
        "by_confidence": _count_by_field(merged_tables["fund_type_audit"], "confidence"),
    }
    metadata["fund_liquidity_audit_summary"] = {
        "entity_count": len(merged_tables["fund_liquidity_audit"]),
        "restricted_entity_count": sum(int(str(row.get("liquidity_restricted") or "0")) for row in merged_tables["fund_liquidity_audit"]),
        "restricted_by_rule": {
            rule_code: sum(
                1
                for row in merged_tables["fund_liquidity_audit"]
                if int(str(row.get("liquidity_restricted") or "0")) == 1 and str(row.get("rule_code") or "") == rule_code
            )
            for rule_code in sorted({str(row.get("rule_code") or "") for row in merged_tables["fund_liquidity_audit"] if int(str(row.get("liquidity_restricted") or "0")) == 1})
        },
    }
    history = metadata.get("incremental_merge_history", [])
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "merged_at": current_timestamp(),
            "target_month": target_month,
            "window_start": window_start,
            "window_end": window_end,
            "temp_raw_dir": str(temp_raw_dir),
            "merge_mode": "upsert",
            "table_stats": merge_stats,
        }
    )
    metadata["incremental_merge_history"] = history
    return metadata


def _count_by_field(rows: list[dict[str, object]], field: str) -> dict[str, int]:
    """按字段值汇总数量，便于重建 audit summary。"""
    counter: dict[str, int] = defaultdict(int)
    for row in rows:
        counter[str(row.get(field) or "")] += 1
    return dict(sorted(counter.items()))
