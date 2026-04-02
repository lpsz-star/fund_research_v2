from __future__ import annotations

import importlib
import hashlib
import json
import math
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from fund_research_v2.common.config import AppConfig, benchmark_to_serializable_dict, scope_artifact_dir
from fund_research_v2.common.contracts import DatasetSnapshot
from fund_research_v2.common.date_utils import add_months, current_timestamp, last_trading_day_of_month, month_end
from fund_research_v2.common.io_utils import read_csv, read_json, read_pickle, write_csv, write_json, write_pickle
from fund_research_v2.data_processing.daily_nav_coverage import build_daily_nav_coverage_monthly
from fund_research_v2.data_processing.fund_liquidity_classifier import classify_fund_liquidity
from fund_research_v2.data_processing.fund_type_classifier import classify_fund_type
from fund_research_v2.data_processing.sample_data import generate_sample_dataset


def load_dataset(config: AppConfig, project_root: Path) -> DatasetSnapshot:
    """按配置加载研究数据，必要时触发 sample 生成或 tushare 缓存读取。"""
    if config.data_source == "sample":
        dataset = generate_sample_dataset(config.lookback_months, config.benchmark)
        persist_dataset(config, project_root, dataset)
        return dataset
    # tushare 模式优先读缓存，是为了把“研究运行”与“联网抓数”解耦，减少每次实验对外部网络的依赖。
    if config.tushare.use_cached_raw:
        cached = load_cached_dataset(config, project_root)
        if cached is not None:
            return cached
    if not config.tushare.download_enabled:
        raise RuntimeError("当前 tushare.download_enabled=false，且本地缓存不存在。")
    return fetch_and_cache_dataset(config, project_root)


def fetch_and_cache_dataset(config: AppConfig, project_root: Path) -> DatasetSnapshot:
    """主动抓取数据并写入 raw 层缓存。"""
    if config.data_source == "sample":
        dataset = generate_sample_dataset(config.lookback_months, config.benchmark)
        persist_dataset(config, project_root, dataset)
        return dataset
    token = _load_tushare_token(project_root / config.local_secret_path)
    provider = TushareDataProvider(config, token, project_root)
    dataset = provider.fetch()
    # 真实接口抓到的数据必须先固化到 raw 层，后续流程都从快照出发，避免同一实验前后数据漂移。
    persist_dataset(config, project_root, dataset)
    return dataset


def warm_failed_api_cache(config: AppConfig, project_root: Path) -> dict[str, object]:
    """只针对上一次失败的 ts_code 预热单接口缓存，不重写整份 raw 快照。"""
    if config.data_source != "tushare":
        raise RuntimeError("仅 tushare 数据源支持失败项增量补抓。")
    raw_dir = project_root / scope_artifact_dir(config.paths.raw_dir, config.data_source)
    nav_pit_daily_path = raw_dir / "fund_nav_pit_daily.csv"
    snapshot_path = raw_dir / "dataset_snapshot.json"
    if not snapshot_path.exists():
        raise RuntimeError("缺少 raw 层 dataset_snapshot.json，无法定位失败项。")
    metadata = read_json(snapshot_path)
    if not isinstance(metadata, dict):
        raise RuntimeError("dataset_snapshot.json 结构无效，无法定位失败项。")
    diagnostics = metadata.get("fetch_diagnostics", {})
    if not isinstance(diagnostics, dict):
        raise RuntimeError("dataset_snapshot.json 中缺少 fetch_diagnostics，无法定位失败项。")
    error_samples = diagnostics.get("api_error_samples", [])
    if not isinstance(error_samples, list):
        raise RuntimeError("fetch_diagnostics.api_error_samples 结构无效。")
    failed_ts_codes = sorted({str(row.get("ts_code") or "").strip() for row in error_samples if isinstance(row, dict) and str(row.get("ts_code") or "").strip()})
    if not failed_ts_codes:
        return {
            "generated_at": current_timestamp(),
            "failed_ts_code_count": 0,
            "success_ts_code_count": 0,
            "failed_ts_codes": [],
            "fetch_diagnostics": {},
        }

    token = _load_tushare_token(project_root / config.local_secret_path)
    provider = TushareDataProvider(config, token, project_root)
    refresh_result = provider.warm_api_cache_for_ts_codes(failed_ts_codes)
    refresh_result["generated_at"] = current_timestamp()
    refresh_result["failed_ts_code_count"] = len(failed_ts_codes)
    return refresh_result


def load_cached_dataset(config: AppConfig, project_root: Path) -> DatasetSnapshot | None:
    """从 raw 层读取已缓存的数据快照。"""
    raw_dir = project_root / scope_artifact_dir(config.paths.raw_dir, config.data_source)
    binary_snapshot_path = raw_dir / "dataset_snapshot.pkl"
    entity_path = raw_dir / "fund_entity_master.csv"
    share_path = raw_dir / "fund_share_class_map.csv"
    nav_path = raw_dir / "fund_nav_monthly.csv"
    nav_pit_daily_path = raw_dir / "fund_nav_pit_daily.csv"
    benchmark_path = raw_dir / "benchmark_monthly.csv"
    manager_path = raw_dir / "manager_assignment_monthly.csv"
    fund_type_audit_path = raw_dir / "fund_type_audit.csv"
    fund_liquidity_audit_path = raw_dir / "fund_liquidity_audit.csv"
    trade_calendar_path = raw_dir / "trade_calendar.csv"
    coverage_path = raw_dir / "fund_nav_daily_coverage_monthly.csv"
    snapshot_path = raw_dir / "dataset_snapshot.json"
    required_paths = [entity_path, share_path, nav_path, benchmark_path, manager_path, snapshot_path]
    if not all(path.exists() for path in required_paths):
        return None
    metadata = read_json(snapshot_path)
    if not _cached_snapshot_matches_config(config, metadata):
        # raw 层是跨命令复用的共享缓存；这里必须先校验口径一致，否则 sample 与 tushare 会互相污染。
        return None
    aligned_metadata = _align_cached_snapshot_metadata(config, metadata)
    if aligned_metadata != metadata:
        write_json(snapshot_path, aligned_metadata)
    metadata = aligned_metadata
    if binary_snapshot_path.exists():
        cached_snapshot = read_pickle(binary_snapshot_path)
        if isinstance(cached_snapshot, DatasetSnapshot):
            return _ensure_daily_nav_coverage_cache(
                config=config,
                raw_dir=raw_dir,
                snapshot_path=snapshot_path,
                coverage_path=coverage_path,
                dataset=_align_binary_snapshot_metadata(cached_snapshot, metadata),
            )
    entity_rows = read_csv(entity_path)
    share_rows = read_csv(share_path)
    fund_type_audit_rows = read_csv(fund_type_audit_path) if fund_type_audit_path.exists() else _build_fund_type_audit_from_entity_cache(entity_rows, share_rows)
    fund_liquidity_audit_rows = read_csv(fund_liquidity_audit_path) if fund_liquidity_audit_path.exists() else _build_fund_liquidity_audit_from_entity_cache(entity_rows, share_rows)
    entity_rows = _hydrate_entity_liquidity_fields(entity_rows, fund_liquidity_audit_rows)
    if isinstance(metadata, dict) and not isinstance(metadata.get("fund_liquidity_audit_summary"), dict):
        metadata["fund_liquidity_audit_summary"] = _build_fund_liquidity_summary(fund_liquidity_audit_rows)
    dataset = DatasetSnapshot(
        fund_entity_master=entity_rows,
        fund_share_class_map=share_rows,
        fund_nav_monthly=read_csv(nav_path),
        fund_nav_pit_daily=read_csv(nav_pit_daily_path) if nav_pit_daily_path.exists() else [],
        benchmark_monthly=read_csv(benchmark_path),
        manager_assignment_monthly=read_csv(manager_path),
        fund_type_audit=fund_type_audit_rows,
        fund_liquidity_audit=fund_liquidity_audit_rows,
        trade_calendar=read_csv(trade_calendar_path) if trade_calendar_path.exists() else [],
        fund_nav_daily_coverage_monthly=read_csv(coverage_path) if coverage_path.exists() else [],
        metadata=metadata,
    )
    return _ensure_daily_nav_coverage_cache(
        config=config,
        raw_dir=raw_dir,
        snapshot_path=snapshot_path,
        coverage_path=coverage_path,
        dataset=dataset,
    )


def persist_dataset(config: AppConfig, project_root: Path, dataset: DatasetSnapshot) -> None:
    """把统一数据契约落盘到 raw 层。"""
    raw_dir = project_root / scope_artifact_dir(config.paths.raw_dir, config.data_source)
    # raw 层按“研究内部契约”落盘，而不是保存 tushare 原始 JSON；目的是保证后续模块不依赖外部字段细节。
    write_csv(raw_dir / "fund_entity_master.csv", dataset.fund_entity_master)
    write_csv(raw_dir / "fund_share_class_map.csv", dataset.fund_share_class_map)
    write_csv(raw_dir / "fund_nav_monthly.csv", dataset.fund_nav_monthly)
    write_csv(raw_dir / "fund_nav_pit_daily.csv", dataset.fund_nav_pit_daily)
    write_csv(raw_dir / "benchmark_monthly.csv", dataset.benchmark_monthly)
    write_csv(raw_dir / "manager_assignment_monthly.csv", dataset.manager_assignment_monthly)
    write_csv(raw_dir / "fund_type_audit.csv", dataset.fund_type_audit)
    write_csv(raw_dir / "fund_liquidity_audit.csv", dataset.fund_liquidity_audit)
    write_csv(raw_dir / "trade_calendar.csv", dataset.trade_calendar)
    write_csv(raw_dir / "fund_nav_daily_coverage_monthly.csv", dataset.fund_nav_daily_coverage_monthly)
    write_json(raw_dir / "dataset_snapshot.json", dataset.metadata)
    # CSV 继续作为可审计底稿保留，额外写一份二进制快照只用于加速本地加载。
    write_pickle(raw_dir / "dataset_snapshot.pkl", dataset)


def _load_tushare_token(path: Path) -> str:
    """从本地密钥文件读取 tushare token。"""
    if not path.exists():
        raise RuntimeError(f"缺少本地密钥文件: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    token = str(payload.get("tushare_token", "")).strip()
    if not token:
        raise RuntimeError(f"{path} 中缺少 tushare_token。")
    return token


def _cached_snapshot_matches_config(config: AppConfig, metadata: object) -> bool:
    """校验 raw 层缓存是否与当前配置属于同一研究口径。"""
    if not isinstance(metadata, dict):
        return False
    source_name = str(metadata.get("source_name") or "").strip()
    if source_name != config.data_source:
        return False
    if config.data_source == "sample":
        return True
    cached_requested_max_funds = metadata.get("requested_max_funds")
    if cached_requested_max_funds != config.tushare.max_funds:
        return False
    # 真实基金快照的规模口径升级后，需要主动淘汰旧缓存，否则会继续复用“代表份额规模”这一错误结果。
    if str(metadata.get("entity_asset_aggregation") or "").strip() != "sum_of_share_classes":
        return False
    if str(metadata.get("nav_monthly_anchor") or "").strip() != "month_last_trading_day":
        return False
    current_benchmark = benchmark_to_serializable_dict(config.benchmark)
    cached_benchmark = metadata.get("benchmark_config")
    if cached_benchmark == current_benchmark:
        return True
    benchmark_source = str(metadata.get("benchmark_source") or "").strip()
    if benchmark_source != config.benchmark.source:
        return False
    cached_default_key = str(metadata.get("benchmark_default_key") or "").strip()
    if cached_default_key and cached_default_key != config.benchmark.default_key:
        return False
    cached_series = metadata.get("benchmark_series")
    if isinstance(cached_series, dict) and cached_series != current_benchmark.get("series"):
        return False
    return True


def _align_cached_snapshot_metadata(config: AppConfig, metadata: object) -> dict[str, object]:
    """把可复用 raw 快照的 benchmark 元数据对齐到当前配置，避免 clean/report 继续展示旧映射。"""
    if not isinstance(metadata, dict):
        return {}
    aligned = dict(metadata)
    benchmark_config = benchmark_to_serializable_dict(config.benchmark)
    aligned["benchmark_config"] = benchmark_config
    aligned["benchmark_name"] = config.benchmark.series_for_key(config.benchmark.default_key).name
    aligned["benchmark_source"] = config.benchmark.source
    aligned["benchmark_ts_code"] = config.benchmark.series_for_key(config.benchmark.default_key).ts_code
    aligned["benchmark_default_key"] = config.benchmark.default_key
    aligned["benchmark_series"] = benchmark_config["series"]
    aligned["benchmark_primary_type_map"] = config.benchmark.primary_type_map
    return aligned


def _align_binary_snapshot_metadata(dataset: DatasetSnapshot, metadata: dict[str, object]) -> DatasetSnapshot:
    """把二进制快照的 metadata 对齐到当前配置校验后的 JSON 元信息。"""
    return DatasetSnapshot(
        fund_entity_master=dataset.fund_entity_master,
        fund_share_class_map=dataset.fund_share_class_map,
        fund_nav_monthly=dataset.fund_nav_monthly,
        benchmark_monthly=dataset.benchmark_monthly,
        manager_assignment_monthly=dataset.manager_assignment_monthly,
        fund_type_audit=dataset.fund_type_audit,
        metadata=metadata,
        fund_liquidity_audit=dataset.fund_liquidity_audit,
        trade_calendar=dataset.trade_calendar,
        fund_nav_pit_daily=dataset.fund_nav_pit_daily,
        fund_nav_daily_coverage_monthly=dataset.fund_nav_daily_coverage_monthly,
    )


def _ensure_daily_nav_coverage_cache(
    config: AppConfig,
    raw_dir: Path,
    snapshot_path: Path,
    coverage_path: Path,
    dataset: DatasetSnapshot,
) -> DatasetSnapshot:
    """为旧 raw 缓存补齐覆盖率月表，避免必须重新联网抓数才能提速。"""
    if dataset.fund_nav_daily_coverage_monthly:
        return dataset
    if not dataset.trade_calendar or not dataset.fund_nav_pit_daily or not dataset.fund_nav_monthly:
        return dataset
    coverage_rows = build_daily_nav_coverage_monthly(
        nav_monthly_rows=dataset.fund_nav_monthly,
        nav_daily_rows=dataset.fund_nav_pit_daily,
        trade_calendar_rows=dataset.trade_calendar,
        lookback_months=config.universe.daily_nav_coverage_lookback_months,
    )
    if not coverage_rows:
        return dataset
    metadata = dict(dataset.metadata)
    metadata["daily_nav_coverage_monthly"] = {
        "lookback_months": config.universe.daily_nav_coverage_lookback_months,
        "row_count": len(coverage_rows),
        "source": "precomputed_from_fund_nav_pit_daily",
    }
    enriched_dataset = DatasetSnapshot(
        fund_entity_master=dataset.fund_entity_master,
        fund_share_class_map=dataset.fund_share_class_map,
        fund_nav_monthly=dataset.fund_nav_monthly,
        benchmark_monthly=dataset.benchmark_monthly,
        manager_assignment_monthly=dataset.manager_assignment_monthly,
        fund_type_audit=dataset.fund_type_audit,
        metadata=metadata,
        fund_liquidity_audit=dataset.fund_liquidity_audit,
        trade_calendar=dataset.trade_calendar,
        fund_nav_pit_daily=dataset.fund_nav_pit_daily,
        fund_nav_daily_coverage_monthly=coverage_rows,
    )
    write_csv(coverage_path, coverage_rows)
    write_json(snapshot_path, metadata)
    write_pickle(raw_dir / "dataset_snapshot.pkl", enriched_dataset)
    return enriched_dataset


class TushareDataProvider:
    """把 tushare 基金接口映射为项目内部的数据快照。"""

    _force_refresh_api_names = {"fund_basic", "fund_company"}

    def __init__(self, config: AppConfig, token: str, project_root: Path) -> None:
        """初始化 tushare 客户端和依赖模块。"""
        self.config = config
        self.token = token
        self.project_root = project_root
        self.pd = _require_module("pandas")
        self.tushare = _require_module("tushare")
        self.client = self.tushare.pro_api(token)
        # 经理与净值接口是最慢的两类请求，缓存可以直接消除同一份额上的重复抓取。
        self._manager_df_cache: dict[str, Any] = {}
        self._monthly_nav_cache: dict[str, tuple[float, list[dict[str, object]], list[dict[str, object]]]] = {}
        self._api_call_stats: dict[str, dict[str, object]] = defaultdict(lambda: {"calls": 0, "failures": 0, "elapsed_seconds": 0.0})
        self._api_error_samples: list[dict[str, str]] = []
        self._api_last_call_at: dict[str, float] = {}
        # fund_nav 是当前最容易触发分钟限频的接口，默认先做轻度节流，避免无意义的失败重试。
        self._api_min_interval_seconds = {
            "fund_nav": 0.8,
        }
        self._api_cache_hits: dict[str, int] = defaultdict(int)
        self._api_cache_misses: dict[str, int] = defaultdict(int)

    def fetch(self) -> DatasetSnapshot:
        """抓取基金主数据、经理、净值和规模，并组装成研究快照。"""
        # fund_basic 是基金场景的主入口；先拿到基金全集，再决定哪些份额会被归并成同一实体。
        fetch_started_at = time.monotonic()
        fund_entity_master: list[dict[str, object]] = []
        share_class_map: list[dict[str, object]] = []
        nav_rows: list[dict[str, object]] = []
        nav_daily_rows: list[dict[str, object]] = []
        benchmark_rows: list[dict[str, object]] = []
        manager_rows: list[dict[str, object]] = []
        fund_type_audit_rows: list[dict[str, object]] = []
        fund_liquidity_audit_rows: list[dict[str, object]] = []
        trade_calendar_rows = self._fetch_trade_calendar_rows_for_config()
        dropped_entities: list[dict[str, object]] = []
        total_entities = 0
        selected_share_class_count = 0
        last_entity_id = ""
        try:
            fund_basic = self._call_api(
                "fund_basic",
                self.client.fund_basic,
                market=self.config.tushare.fund_market,
                status=self.config.tushare.fund_status,
            )
            if fund_basic is None or fund_basic.empty:
                raise RuntimeError("Tushare fund_basic 返回空结果。")
            company_df = self._call_api("fund_company", self.client.fund_company)
            company_lookup = _build_company_lookup(company_df)
            fund_basic = fund_basic.copy().sort_values("ts_code")
            if self.config.tushare.max_funds:
                fund_basic = fund_basic.head(self.config.tushare.max_funds)
            selected_share_class_count = len(fund_basic)

            grouped_rows = _group_share_classes(fund_basic.to_dict("records"))
            total_entities = len(grouped_rows)
            self._write_fetch_progress(
                status="running",
                processed_entities=0,
                total_entities=total_entities,
                retained_entities=0,
                dropped_entities=0,
                nav_rows=0,
                manager_rows=0,
                selected_share_class_count=selected_share_class_count,
                last_entity_id="",
                runtime_seconds=round(time.monotonic() - fetch_started_at, 3),
            )
            for index, (entity_id, rows) in enumerate(grouped_rows.items(), start=1):
                last_entity_id = entity_id
                representative_row = _select_representative_share_class(rows)
                classification = classify_fund_type(
                    fund_type=str(representative_row.get("fund_type") or ""),
                    invest_type=str(representative_row.get("invest_type") or ""),
                    fund_name=str(representative_row.get("name") or representative_row["ts_code"]),
                    benchmark_text=str(representative_row.get("benchmark") or ""),
                )
                liquidity = classify_fund_liquidity(str(representative_row.get("name") or representative_row["ts_code"]))
                # 后续特征和回测都以“基金实体”而不是份额类为单位，避免 A/C 份额重复入选。
                fund_company = str(representative_row.get("management") or "unknown")
                company_meta = company_lookup.get(fund_company, {})
                manager_name, manager_begin_date = self._fetch_current_manager(str(representative_row["ts_code"]))
                latest_assets_cny_mn, entity_daily_nav_rows, entity_nav_rows = self._fetch_entity_monthly_nav_rows(
                    rows,
                    entity_id,
                    trade_calendar_rows,
                )
                if not entity_nav_rows:
                    # 没有可用月频净值的基金不能进入研究层，否则后续收益窗口和回测口径都无法成立。
                    dropped_entities.append(
                        {
                            "entity_id": entity_id,
                            "entity_name": _normalize_entity_name(str(representative_row.get("name") or representative_row["ts_code"])),
                            "fund_company": str(representative_row.get("management") or "unknown"),
                            "primary_type": classification["primary_type"],
                            "share_class_ids": "|".join(str(row["ts_code"]) for row in rows),
                            "share_class_count": len(rows),
                            "drop_reason": "no_valid_entity_monthly_nav",
                            "representative_share_class_id": str(representative_row["ts_code"]),
                        }
                    )
                else:
                    manager_rows.extend(self._build_manager_assignment_rows(str(representative_row["ts_code"]), entity_id, entity_nav_rows))
                    normalized_name = _normalize_entity_name(str(representative_row.get("name") or representative_row["ts_code"]))
                    fund_entity_master.append(
                        {
                            "entity_id": entity_id,
                            "entity_name": normalized_name,
                            "primary_type": classification["primary_type"],
                            "fund_company": fund_company,
                            "fund_company_province": company_meta.get("province", ""),
                            "fund_company_city": company_meta.get("city", ""),
                            "fund_company_website": company_meta.get("website", ""),
                            "manager_name": manager_name,
                            "manager_start_month": _normalize_month(manager_begin_date),
                            "inception_month": _normalize_month(representative_row.get("found_date") or representative_row.get("issue_date") or "20000101"),
                            "latest_assets_cny_mn": latest_assets_cny_mn,
                            "liquidity_restricted": int(liquidity["liquidity_restricted"]),
                            "holding_lock_months": int(liquidity["holding_lock_months"]),
                            "status": representative_row.get("status") or "L",
                            "custodian": representative_row.get("custodian") or "",
                            "benchmark_text": representative_row.get("benchmark") or "",
                            "invest_type": representative_row.get("invest_type") or "",
                            "representative_share_class_id": representative_row["ts_code"],
                        }
                    )
                    fund_type_audit_rows.append(
                        {
                            "entity_id": entity_id,
                            "entity_name": normalized_name,
                            "share_class_id": str(representative_row["ts_code"]),
                            "fund_name": str(representative_row.get("name") or representative_row["ts_code"]),
                            "raw_fund_type": classification["raw_fund_type"],
                            "raw_invest_type": classification["raw_invest_type"],
                            "benchmark_text": str(representative_row.get("benchmark") or ""),
                            "primary_type": classification["primary_type"],
                            "rule_code": classification["rule_code"],
                            "confidence": classification["confidence"],
                            "reason": classification["reason"],
                        }
                    )
                    fund_liquidity_audit_rows.append(
                        {
                            "entity_id": entity_id,
                            "entity_name": normalized_name,
                            "share_class_id": str(representative_row["ts_code"]),
                            "fund_name": str(representative_row.get("name") or representative_row["ts_code"]),
                            "liquidity_restricted": int(liquidity["liquidity_restricted"]),
                            "holding_lock_months": int(liquidity["holding_lock_months"]),
                            "rule_code": str(liquidity["rule_code"]),
                            "confidence": str(liquidity["confidence"]),
                            "reason": str(liquidity["reason"]),
                        }
                    )
                    for row in rows:
                        share_class_map.append(
                            {
                                "entity_id": entity_id,
                                "share_class_id": row["ts_code"],
                                "share_class_name": row.get("name") or row["ts_code"],
                                "is_primary_share_class": 1 if row["ts_code"] == representative_row["ts_code"] else 0,
                            }
                        )
                    nav_daily_rows.extend(entity_daily_nav_rows)
                    nav_rows.extend(entity_nav_rows)
                if index % self.config.tushare.progress_every_entities == 0 or index == total_entities:
                    print(
                        f"[tushare] entities={index}/{total_entities} "
                        f"retained={len(fund_entity_master)} dropped={len(dropped_entities)} "
                        f"nav_rows={len(nav_rows)} manager_rows={len(manager_rows)}"
                    )
                    self._write_fetch_progress(
                        status="running",
                        processed_entities=index,
                        total_entities=total_entities,
                        retained_entities=len(fund_entity_master),
                        dropped_entities=len(dropped_entities),
                        nav_rows=len(nav_rows),
                        manager_rows=len(manager_rows),
                        selected_share_class_count=selected_share_class_count,
                        last_entity_id=entity_id,
                        runtime_seconds=round(time.monotonic() - fetch_started_at, 3),
                    )

            month_set = sorted({str(row["month"]) for row in nav_rows})
            daily_coverage_rows = build_daily_nav_coverage_monthly(
                nav_monthly_rows=nav_rows,
                nav_daily_rows=nav_daily_rows,
                trade_calendar_rows=trade_calendar_rows,
                lookback_months=self.config.universe.daily_nav_coverage_lookback_months,
            )
            benchmark_rows = self._fetch_benchmark_rows(month_set)
            if not fund_entity_master or not nav_rows:
                raise RuntimeError("Tushare 基金数据未形成有效的实体主表或月频净值表。")
            metadata = {
                "source_name": "tushare",
                "generated_at": current_timestamp(),
                "entity_count": len(fund_entity_master),
                "share_class_count": len(share_class_map),
                "requested_max_funds": self.config.tushare.max_funds,
                "ingestion_audit": {
                    "selected_share_class_count": selected_share_class_count,
                    "grouped_entity_count": total_entities,
                    "retained_entity_count": len(fund_entity_master),
                    "retained_share_class_count": len(share_class_map),
                    "dropped_entity_count": len(dropped_entities),
                    "dropped_entities": dropped_entities,
                },
                "month_range": {
                    "start": month_set[0] if month_set else None,
                    "end": month_set[-1] if month_set else None,
                },
                "field_status": {
                    "latest_assets_cny_mn": "real_from_fund_nav_or_fund_share",
                    "manager_name": "real_from_fund_manager",
                    "return_1m": "real",
                    "benchmark_return_1m": "real_from_tushare_index" if self.config.benchmark.source == "tushare_index" else "proxy_zero_pending_index_integration",
                },
                "benchmark_config": benchmark_to_serializable_dict(self.config.benchmark),
                "benchmark_name": self.config.benchmark.series_for_key(self.config.benchmark.default_key).name,
                "benchmark_source": self.config.benchmark.source,
                "benchmark_ts_code": self.config.benchmark.series_for_key(self.config.benchmark.default_key).ts_code,
                "benchmark_default_key": self.config.benchmark.default_key,
                "benchmark_series": {
                    key: {
                        "name": series.name,
                        "ts_code": series.ts_code,
                    }
                    for key, series in self.config.benchmark.series.items()
                },
                "benchmark_primary_type_map": self.config.benchmark.primary_type_map,
                "fund_type_audit_summary": {
                    "entity_count": len(fund_type_audit_rows),
                    "by_primary_type": {
                        primary_type_name: sum(1 for row in fund_type_audit_rows if row["primary_type"] == primary_type_name)
                        for primary_type_name in sorted({str(row["primary_type"]) for row in fund_type_audit_rows})
                    },
                    "by_confidence": {
                        confidence_name: sum(1 for row in fund_type_audit_rows if row["confidence"] == confidence_name)
                        for confidence_name in sorted({str(row["confidence"]) for row in fund_type_audit_rows})
                    },
                },
                "fund_liquidity_audit_summary": {
                    "entity_count": len(fund_liquidity_audit_rows),
                    "restricted_entity_count": sum(int(row["liquidity_restricted"]) for row in fund_liquidity_audit_rows),
                    "restricted_by_rule": {
                        rule_code: sum(1 for row in fund_liquidity_audit_rows if int(row["liquidity_restricted"]) == 1 and row["rule_code"] == rule_code)
                        for rule_code in sorted({str(row["rule_code"]) for row in fund_liquidity_audit_rows if int(row["liquidity_restricted"]) == 1})
                    },
                },
                "fetch_diagnostics": {
                    "runtime_seconds": round(time.monotonic() - fetch_started_at, 3),
                    "api_call_stats": self._api_call_stats_snapshot(),
                    "api_cache_stats": self._api_cache_stats_snapshot(),
                    "api_error_samples": self._api_error_samples,
                },
                "entity_asset_aggregation": "sum_of_share_classes",
                "nav_monthly_anchor": "month_last_trading_day",
                "trade_calendar": {
                    "source": "tushare_trade_cal",
                    "exchange": "SSE",
                    "start_date": trade_calendar_rows[0]["cal_date"] if trade_calendar_rows else "",
                    "end_date": trade_calendar_rows[-1]["cal_date"] if trade_calendar_rows else "",
                    "open_day_count": sum(int(str(row.get("is_open") or "0")) for row in trade_calendar_rows),
                },
                "daily_nav_coverage_monthly": {
                    "lookback_months": self.config.universe.daily_nav_coverage_lookback_months,
                    "row_count": len(daily_coverage_rows),
                    "source": "precomputed_from_fund_nav_pit_daily",
                },
            }
            self._write_fetch_progress(
                status="completed",
                processed_entities=total_entities,
                total_entities=total_entities,
                retained_entities=len(fund_entity_master),
                dropped_entities=len(dropped_entities),
                nav_rows=len(nav_rows),
                manager_rows=len(manager_rows),
                selected_share_class_count=selected_share_class_count,
                last_entity_id=last_entity_id,
                runtime_seconds=round(time.monotonic() - fetch_started_at, 3),
                entity_count=len(fund_entity_master),
                share_class_count=len(share_class_map),
                month_range=metadata["month_range"],
            )
            return DatasetSnapshot(
                fund_entity_master=fund_entity_master,
                fund_share_class_map=share_class_map,
                fund_nav_monthly=nav_rows,
                fund_nav_pit_daily=nav_daily_rows,
                benchmark_monthly=benchmark_rows,
                manager_assignment_monthly=manager_rows,
                fund_type_audit=fund_type_audit_rows,
                fund_liquidity_audit=fund_liquidity_audit_rows,
                trade_calendar=trade_calendar_rows,
                fund_nav_daily_coverage_monthly=daily_coverage_rows,
                metadata=metadata,
            )
        except Exception as exc:
            self._write_fetch_progress(
                status="failed",
                processed_entities=len(fund_entity_master) + len(dropped_entities),
                total_entities=total_entities,
                retained_entities=len(fund_entity_master),
                dropped_entities=len(dropped_entities),
                nav_rows=len(nav_rows),
                manager_rows=len(manager_rows),
                selected_share_class_count=selected_share_class_count,
                last_entity_id=last_entity_id,
                runtime_seconds=round(time.monotonic() - fetch_started_at, 3),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

    def warm_api_cache_for_ts_codes(self, ts_codes: list[str]) -> dict[str, object]:
        """只为指定失败份额补抓单接口缓存，供后续全量流程复用。"""
        started_at = time.monotonic()
        success_ts_codes: list[str] = []
        failed_ts_codes: list[str] = []
        trade_calendar_rows = self._fetch_trade_calendar_rows_for_config()
        for index, ts_code in enumerate(ts_codes, start=1):
            manager_df = self._fetch_manager_df(ts_code)
            _, _, nav_rows = self._fetch_monthly_nav_rows(ts_code, ts_code, trade_calendar_rows)
            if manager_df is None or nav_rows == []:
                failed_ts_codes.append(ts_code)
            else:
                success_ts_codes.append(ts_code)
            if index % self.config.tushare.progress_every_entities == 0 or index == len(ts_codes):
                print(
                    f"[tushare-retry] ts_codes={index}/{len(ts_codes)} "
                    f"success={len(success_ts_codes)} failed={len(failed_ts_codes)}"
                )
        return {
            "runtime_seconds": round(time.monotonic() - started_at, 3),
            "success_ts_code_count": len(success_ts_codes),
            "failed_ts_code_count_after_retry": len(failed_ts_codes),
            "success_ts_codes": success_ts_codes,
            "failed_ts_codes_after_retry": failed_ts_codes,
            "fetch_diagnostics": {
                "api_call_stats": self._api_call_stats_snapshot(),
                "api_cache_stats": self._api_cache_stats_snapshot(),
                "api_error_samples": self._api_error_samples,
            },
        }

    def _fetch_current_manager(self, ts_code: str) -> tuple[str, str]:
        """获取基金当前在任经理及其任职开始日期。"""
        manager_df = self._fetch_manager_df(ts_code)
        if manager_df is None or manager_df.empty:
            return "unknown", "20000101"
        manager_df = manager_df.copy()
        manager_df["begin_date"] = manager_df["begin_date"].fillna("")
        if "end_date" in manager_df.columns:
            # 优先取仍在任的经理，因为研究里使用的是当前管理责任人而不是历史任职全名单。
            current_df = manager_df[manager_df["end_date"].isna() | (manager_df["end_date"] == "")]
            if current_df.empty:
                current_df = manager_df
        else:
            current_df = manager_df
        current_df = current_df.sort_values("begin_date")
        row = current_df.iloc[-1].to_dict()
        return str(row.get("name") or "unknown"), str(row.get("begin_date") or "20000101")

    def _fetch_manager_df(self, ts_code: str) -> Any:
        """抓取基金经理历史明细，失败时返回 None。"""
        if ts_code in self._manager_df_cache:
            return self._manager_df_cache[ts_code]
        result = self._call_api("fund_manager", self.client.fund_manager, allow_failure=True, ts_code=ts_code)
        self._manager_df_cache[ts_code] = result
        return result

    def _build_manager_assignment_rows(
        self,
        ts_code: str,
        entity_id: str,
        entity_nav_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """把经理任职历史映射到实体的月频时间轴。"""
        manager_df = self._fetch_manager_df(ts_code)
        if manager_df is None or manager_df.empty:
            return []
        manager_df = manager_df.copy()
        manager_df["begin_date"] = manager_df["begin_date"].fillna("").astype(str)
        if "end_date" not in manager_df.columns:
            manager_df["end_date"] = ""
        manager_df["end_date"] = manager_df["end_date"].fillna("").astype(str)
        records = sorted(manager_df.to_dict("records"), key=lambda item: str(item.get("begin_date") or ""))
        assignment_rows: list[dict[str, object]] = []
        for nav_row in entity_nav_rows:
            month = str(nav_row["month"])
            active_records = [
                row for row in records
                if _manager_record_matches_month(row, month)
            ]
            if not active_records:
                active_records = [
                    row for row in records
                    if _normalize_month(row.get("begin_date")) <= month
                ]
            if not active_records:
                continue
            # 若同月存在多名在任经理，先用最近开始任职的经理承载稳定性口径，避免混入整段历史最早经理。
            selected = sorted(active_records, key=lambda item: str(item.get("begin_date") or ""))[-1]
            assignment_rows.append(
                {
                    "entity_id": entity_id,
                    "month": month,
                    "manager_name": str(selected.get("name") or "unknown"),
                    "manager_start_month": _normalize_month(selected.get("begin_date") or "20000101"),
                    "manager_end_month": _normalize_month(selected.get("end_date") or "") if str(selected.get("end_date") or "").strip() else "",
                }
            )
        return assignment_rows

    def _fetch_monthly_nav_rows(
        self,
        ts_code: str,
        entity_id: str,
        trade_calendar_rows: list[dict[str, object]] | None = None,
    ) -> tuple[float, list[dict[str, object]], list[dict[str, object]]]:
        """把单份额净值和份额数据整理为月频净值与规模序列。"""
        if ts_code in self._monthly_nav_cache:
            return self._monthly_nav_cache[ts_code]
        nav_df = self._call_api(
            "fund_nav",
            self.client.fund_nav,
            allow_failure=True,
            ts_code=ts_code,
            start_date=self.config.tushare.start_date,
            end_date=self.config.tushare.end_date,
        )
        if nav_df is None or nav_df.empty:
            self._monthly_nav_cache[ts_code] = (0.0, [], [])
            return self._monthly_nav_cache[ts_code]
        share_df = self._call_api(
            "fund_share",
            self.client.fund_share,
            allow_failure=True,
            ts_code=ts_code,
            start_date=self.config.tushare.start_date,
            end_date=self.config.tushare.end_date,
            market=self.config.tushare.fund_market,
        )
        share_lookup = _build_share_lookup(share_df)
        nav_df = nav_df.copy()
        nav_df["nav_date"] = nav_df["nav_date"].astype(str)
        nav_df["ann_date"] = nav_df["ann_date"].fillna("").astype(str)
        nav_df["update_flag"] = nav_df["update_flag"].fillna("0").astype(str)
        nav_df["nav_numeric"] = nav_df.apply(_preferred_nav_value, axis=1)
        nav_df["asset_numeric"] = nav_df.apply(lambda row: _preferred_asset_value(row, share_lookup), axis=1)
        nav_df["normalized_available_date"] = nav_df.apply(lambda row: _nav_effective_available_date(row), axis=1)
        selected_nav_df = _select_point_in_time_nav_rows(nav_df)
        daily_rows = _build_selected_daily_nav_rows(selected_nav_df, entity_id, ts_code)
        monthly_selected_nav_df = _select_month_end_trading_day_nav_rows(selected_nav_df, trade_calendar_rows or [])
        monthly_rows = []
        previous_nav = None
        for _, group in monthly_selected_nav_df.groupby(monthly_selected_nav_df["nav_date"].str.slice(0, 6), sort=True):
            record = group.sort_values(["nav_date", "normalized_available_date"]).iloc[-1]
            current_nav = float(record["nav_numeric"])
            if current_nav <= 0:
                continue
            month = _normalize_month(record["nav_date"])
            current_assets = float(record["asset_numeric"]) if not math.isnan(float(record["asset_numeric"])) else 0.0
            monthly_rows.append(
                {
                    "entity_id": entity_id,
                    "month": month,
                    "target_nav_date": _normalize_date(record["target_nav_date"]),
                    "nav_date": _normalize_date(record["nav_date"]),
                    # 研究口径固定使用“最早公告且净值有效”的首个可见版本。
                    "available_date": _normalize_date(record["normalized_available_date"]),
                    "nav": round(current_nav, 6),
                    "return_1m": round(0.0 if previous_nav in {None, 0} else current_nav / previous_nav - 1.0, 6),
                    "assets_cny_mn": round(current_assets, 3),
                    "selected_ann_date": _normalize_date(record["normalized_available_date"]),
                    "selected_update_flag": str(record.get("update_flag") or "0"),
                    "nav_selection_reason": "month_last_trading_day_only",
                }
            )
            previous_nav = current_nav
        latest_assets = monthly_rows[-1]["assets_cny_mn"] if monthly_rows else 0.0
        self._monthly_nav_cache[ts_code] = (float(latest_assets), daily_rows, monthly_rows)
        return self._monthly_nav_cache[ts_code]

    def _fetch_trade_calendar_rows_for_config(self) -> list[dict[str, object]]:
        """抓取覆盖研究区间的交易日日历，供净值锚点、决策日和收益归属规则使用。"""
        start_date = str(self.config.tushare.start_date or "").strip() or "20000101"
        if self.config.tushare.end_date:
            end_date = str(self.config.tushare.end_date).replace("-", "")
        else:
            calendar_end_month = add_months(self.config.as_of_date[:7], 2)
            end_date = month_end(calendar_end_month).replace("-", "")
        calendar_df = self._call_api(
            "trade_cal",
            self.client.trade_cal,
            exchange="SSE",
            start_date=start_date.replace("-", ""),
            end_date=end_date,
        )
        if calendar_df is None or calendar_df.empty:
            raise RuntimeError("Tushare trade_cal 未返回有效交易日历。")
        calendar_df = calendar_df.copy().sort_values("cal_date")
        rows: list[dict[str, object]] = []
        for record in calendar_df.to_dict("records"):
            rows.append(
                {
                    "exchange": str(record.get("exchange") or "SSE"),
                    "cal_date": _normalize_date(record.get("cal_date") or ""),
                    "is_open": int(str(record.get("is_open") or "0")),
                    "pretrade_date": _normalize_date(record.get("pretrade_date") or "") if str(record.get("pretrade_date") or "").strip() else "",
                }
            )
        return rows

    def _fetch_entity_monthly_nav_rows(
        self,
        share_class_rows: list[dict[str, object]],
        entity_id: str,
        trade_calendar_rows: list[dict[str, object]] | None = None,
    ) -> tuple[float, list[dict[str, object]], list[dict[str, object]]]:
        """以代表份额承载收益序列，并把同实体各份额规模汇总到实体层。"""
        representative_row = _select_representative_share_class(share_class_rows)
        representative_assets, representative_daily_rows, representative_nav_rows = self._fetch_monthly_nav_rows(
            str(representative_row["ts_code"]),
            entity_id,
            trade_calendar_rows,
        )
        if not representative_nav_rows:
            return representative_assets, [], []
        asset_rows_by_share_class: list[list[dict[str, object]]] = []
        asset_daily_rows_by_share_class: list[list[dict[str, object]]] = []
        for row in share_class_rows:
            _, share_daily_rows, share_nav_rows = self._fetch_monthly_nav_rows(
                str(row["ts_code"]),
                entity_id,
                trade_calendar_rows,
            )
            if share_nav_rows:
                asset_rows_by_share_class.append(share_nav_rows)
            if share_daily_rows:
                asset_daily_rows_by_share_class.append(share_daily_rows)
        if not asset_rows_by_share_class:
            return representative_assets, representative_daily_rows, representative_nav_rows
        # 基金池筛的是“基金实体”规模，不是某个 A/C 份额规模，因此这里按月汇总同实体全部份额的资产。
        asset_sum_by_month: dict[str, float] = defaultdict(float)
        for share_nav_rows in asset_rows_by_share_class:
            for nav_row in share_nav_rows:
                asset_sum_by_month[str(nav_row["month"])] += float(nav_row["assets_cny_mn"])
        merged_rows: list[dict[str, object]] = []
        for nav_row in representative_nav_rows:
            month = str(nav_row["month"])
            merged_row = dict(nav_row)
            merged_row["assets_cny_mn"] = round(asset_sum_by_month.get(month, float(nav_row["assets_cny_mn"])), 3)
            merged_rows.append(merged_row)
        asset_sum_by_trade_date: dict[str, float] = defaultdict(float)
        for share_daily_rows in asset_daily_rows_by_share_class:
            for nav_row in share_daily_rows:
                asset_sum_by_trade_date[str(nav_row["trade_date"])] += float(nav_row["assets_cny_mn"])
        merged_daily_rows: list[dict[str, object]] = []
        for nav_row in representative_daily_rows:
            trade_date = str(nav_row["trade_date"])
            merged_row = dict(nav_row)
            merged_row["assets_cny_mn"] = round(asset_sum_by_trade_date.get(trade_date, float(nav_row["assets_cny_mn"])), 3)
            merged_daily_rows.append(merged_row)
        latest_assets = merged_rows[-1]["assets_cny_mn"] if merged_rows else representative_assets
        return float(latest_assets), merged_daily_rows, merged_rows

    def _fetch_benchmark_rows(self, month_set: list[str]) -> list[dict[str, object]]:
        """抓取市场基准并转换成月频收益序列。"""
        if not month_set:
            return []
        if self.config.benchmark.source != "tushare_index":
            rows = []
            for benchmark_key, series in self.config.benchmark.series.items():
                for month in month_set:
                    rows.append(
                        {
                            "month": month,
                            "benchmark_key": benchmark_key,
                            "benchmark_return_1m": 0.0,
                            "benchmark_name": series.name,
                            "benchmark_ts_code": series.ts_code or "",
                            "available_date": _normalize_date(f"{month[:4]}{month[5:7]}28"),
                        }
                    )
            return rows

        rows: list[dict[str, object]] = []
        series_cache: dict[str, list[dict[str, object]]] = {}
        for benchmark_key, series in self.config.benchmark.series.items():
            ts_code = str(series.ts_code or "").strip()
            if not ts_code:
                raise RuntimeError(f"benchmark {benchmark_key} 缺少 ts_code，无法抓取真实指数行情。")
            if ts_code not in series_cache:
                series_cache[ts_code] = self._fetch_single_benchmark_series(month_set, ts_code)
            for row in series_cache[ts_code]:
                benchmark_row = dict(row)
                benchmark_row["benchmark_key"] = benchmark_key
                benchmark_row["benchmark_name"] = series.name
                benchmark_row["benchmark_ts_code"] = ts_code
                rows.append(benchmark_row)
        return rows

    def _fetch_single_benchmark_series(self, month_set: list[str], ts_code: str) -> list[dict[str, object]]:
        """抓取单条指数序列，并月度化成统一 benchmark 契约。"""
        start_date = f"{month_set[0][:4]}{month_set[0][5:7]}01"
        end_month = month_set[-1]
        end_date = f"{end_month[:4]}{end_month[5:7]}31"
        index_df = self._call_api(
            "index_daily",
            self.client.index_daily,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        if index_df is None or index_df.empty:
            raise RuntimeError(f"基准指数 {ts_code} 未返回有效行情数据。")
        index_df = index_df.copy()
        index_df["trade_date"] = index_df["trade_date"].astype(str)
        index_df = index_df.sort_values("trade_date")
        monthly_close: dict[str, float] = {}
        monthly_trade_date: dict[str, str] = {}
        for row in index_df.to_dict("records"):
            month = _normalize_month(row.get("trade_date"))
            close = row.get("close")
            if close is None or (isinstance(close, float) and math.isnan(close)):
                continue
            monthly_close[month] = float(close)
            monthly_trade_date[month] = str(row["trade_date"])
        rows = []
        previous_close = None
        for month in month_set:
            close = monthly_close.get(month)
            if close is None or close <= 0:
                rows.append(
                    {
                        "month": month,
                        "benchmark_return_1m": 0.0,
                        "benchmark_close": "",
                        "benchmark_trade_date": "",
                        "available_date": "",
                    }
                )
                continue
            rows.append(
                {
                    "month": month,
                    "benchmark_return_1m": round(0.0 if previous_close in {None, 0} else close / previous_close - 1.0, 6),
                    "benchmark_close": round(close, 4),
                    "benchmark_trade_date": _normalize_date(monthly_trade_date[month]),
                    "available_date": _normalize_date(monthly_trade_date[month]),
                }
            )
            previous_close = close
        return rows

    def _call_api(
        self,
        api_name: str,
        func: Any,
        allow_failure: bool = False,
        **kwargs: object,
    ) -> Any:
        """统一执行 Tushare 请求，记录耗时、失败和有限重试。"""
        use_cache = api_name not in self._force_refresh_api_names
        if use_cache:
            cached = self._read_api_cache(api_name, kwargs)
            if cached is not None:
                self._api_cache_hits[api_name] += 1
                return cached
        self._api_cache_misses[api_name] += 1
        attempts = self.config.tushare.request_retry_count + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            self._respect_api_interval(api_name)
            started_at = time.monotonic()
            try:
                result = func(**kwargs)
                self._record_api_call(api_name, time.monotonic() - started_at, failed=False)
                self._api_last_call_at[api_name] = time.monotonic()
                if use_cache:
                    self._write_api_cache(api_name, kwargs, result)
                if self.config.tushare.request_pause_ms > 0:
                    time.sleep(self.config.tushare.request_pause_ms / 1000.0)
                return result
            except Exception as exc:
                last_error = exc
                self._record_api_call(api_name, time.monotonic() - started_at, failed=True)
                self._api_last_call_at[api_name] = time.monotonic()
                self._record_api_error(api_name, kwargs, exc, attempt)
                if attempt < attempts:
                    time.sleep(self._retry_delay_seconds(exc, attempt))
                    continue
        if allow_failure:
            return None
        raise RuntimeError(f"Tushare 接口 {api_name} 调用失败: {last_error}") from last_error

    def _record_api_call(self, api_name: str, elapsed_seconds: float, *, failed: bool) -> None:
        """累计接口调用统计。"""
        stats = self._api_call_stats[api_name]
        stats["calls"] = int(stats["calls"]) + 1
        stats["elapsed_seconds"] = float(stats["elapsed_seconds"]) + elapsed_seconds
        if failed:
            stats["failures"] = int(stats["failures"]) + 1

    def _record_api_error(self, api_name: str, kwargs: dict[str, object], exc: Exception, attempt: int) -> None:
        """保留有限的错误样本，便于排查抓数阶段问题。"""
        if len(self._api_error_samples) >= 50:
            return
        ts_code = str(kwargs.get("ts_code") or "")
        self._api_error_samples.append(
            {
                "api_name": api_name,
                "ts_code": ts_code,
                "attempt": str(attempt),
                "error": str(exc)[:300],
            }
        )

    def _api_call_stats_snapshot(self) -> dict[str, dict[str, object]]:
        """输出接口统计快照，供 metadata 和报告使用。"""
        return {
            api_name: {
                "calls": int(payload["calls"]),
                "failures": int(payload["failures"]),
                "elapsed_seconds": round(float(payload["elapsed_seconds"]), 3),
            }
            for api_name, payload in sorted(self._api_call_stats.items())
        }

    def _api_cache_stats_snapshot(self) -> dict[str, dict[str, int]]:
        """输出单接口缓存命中情况。"""
        api_names = sorted(set(self._api_cache_hits) | set(self._api_cache_misses))
        return {
            api_name: {
                "hits": int(self._api_cache_hits.get(api_name, 0)),
                "misses": int(self._api_cache_misses.get(api_name, 0)),
            }
            for api_name in api_names
        }

    def _respect_api_interval(self, api_name: str) -> None:
        """在真正发请求前按接口节流，减少命中外部分钟频率上限。"""
        min_interval = self._api_min_interval_seconds.get(api_name, 0.0)
        if min_interval <= 0:
            return
        previous_call_at = self._api_last_call_at.get(api_name)
        if previous_call_at is None:
            return
        elapsed = time.monotonic() - previous_call_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

    def _retry_delay_seconds(self, exc: Exception, attempt: int) -> float:
        """根据错误类型决定重试等待时间。"""
        message = str(exc)
        if "每分钟最多访问该接口" in message:
            # 命中分钟限频时，短退避没有意义，直接拉长等待时间。
            return min(20.0 * attempt, 60.0)
        return min(0.5 * attempt, 2.0)

    def _api_cache_dir(self) -> Path:
        """返回单接口响应缓存目录。"""
        return self.project_root / scope_artifact_dir(self.config.paths.raw_dir, self.config.data_source) / "api_cache"

    def _fetch_progress_path(self) -> Path:
        """返回抓数进度文件路径。"""
        return self.project_root / scope_artifact_dir(self.config.paths.raw_dir, self.config.data_source) / "fetch_progress.json"

    def _write_fetch_progress(self, **payload: object) -> None:
        """把抓数阶段的心跳信息写入 raw 层，便于长任务期间观察进度。"""
        progress_payload = {
            "source_name": "tushare",
            "updated_at": current_timestamp(),
            "requested_max_funds": self.config.tushare.max_funds,
            **payload,
        }
        write_json(self._fetch_progress_path(), progress_payload)

    def _api_cache_path(self, api_name: str, kwargs: dict[str, object]) -> Path:
        """根据接口名和参数生成稳定缓存路径。"""
        normalized = json.dumps({key: kwargs[key] for key in sorted(kwargs)}, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha1(f"{api_name}|{normalized}".encode("utf-8")).hexdigest()[:16]
        return self._api_cache_dir() / f"{api_name}__{digest}.json"

    def _read_api_cache(self, api_name: str, kwargs: dict[str, object]) -> Any:
        """读取单接口响应缓存；不存在时返回 None。"""
        path = self._api_cache_path(api_name, kwargs)
        if not path.exists():
            return None
        payload = read_json(path)
        if not isinstance(payload, dict) or payload.get("kind") != "dataframe_records":
            return None
        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            return None
        return self.pd.DataFrame(rows)

    def _write_api_cache(self, api_name: str, kwargs: dict[str, object], result: Any) -> None:
        """把成功的单接口响应写入缓存，供后续增量复用。"""
        if result is None:
            return
        rows = result.to_dict("records") if hasattr(result, "to_dict") else None
        if rows is None:
            return
        write_json(
            self._api_cache_path(api_name, kwargs),
            {
                "kind": "dataframe_records",
                "api_name": api_name,
                "params": {key: str(value) for key, value in sorted(kwargs.items())},
                "rows": rows,
            },
        )


def _require_module(module_name: str) -> Any:
    """按需导入运行时依赖，缺失时抛出带语义的错误。"""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"缺少依赖模块 {module_name}。") from exc


def _build_company_lookup(company_df: Any) -> dict[str, dict[str, object]]:
    """把基金公司维表转换成便于查询的字典。"""
    if company_df is None or company_df.empty:
        return {}
    lookup: dict[str, dict[str, object]] = {}
    for row in company_df.to_dict("records"):
        payload = {
            "province": row.get("province") or "",
            "city": row.get("city") or "",
            "website": row.get("website") or "",
        }
        if row.get("name"):
            lookup[str(row["name"])] = payload
        if row.get("shortname"):
            lookup[str(row["shortname"])] = payload
    return lookup


def _build_fund_type_audit_from_entity_cache(
    entity_rows: list[dict[str, object]],
    share_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """兼容旧 raw 缓存缺少 fund_type_audit.csv 的情况，从实体快照回补类型审计表。"""
    primary_share_lookup = {
        str(row["entity_id"]): str(row["share_class_id"])
        for row in share_rows
        if int(str(row.get("is_primary_share_class") or "0")) == 1
    }
    audit_rows: list[dict[str, object]] = []
    for entity in entity_rows:
        classification = classify_fund_type(
            fund_type=str(entity.get("primary_type") or ""),
            invest_type=str(entity.get("invest_type") or ""),
            fund_name=str(entity.get("entity_name") or entity.get("entity_id") or ""),
            benchmark_text=str(entity.get("benchmark_text") or ""),
        )
        # 旧缓存已经丢失原始 fund_type，只能把当前实体类型当作一个弱代理值，因此置信度要主动下调。
        confidence = "low" if classification["confidence"] != "low" else classification["confidence"]
        audit_rows.append(
            {
                "entity_id": str(entity.get("entity_id") or ""),
                "entity_name": str(entity.get("entity_name") or ""),
                "share_class_id": primary_share_lookup.get(str(entity.get("entity_id") or ""), str(entity.get("representative_share_class_id") or "")),
                "fund_name": str(entity.get("entity_name") or ""),
                "raw_fund_type": str(entity.get("primary_type") or ""),
                "raw_invest_type": str(entity.get("invest_type") or ""),
                "benchmark_text": str(entity.get("benchmark_text") or ""),
                "primary_type": str(entity.get("primary_type") or classification["primary_type"]),
                "rule_code": "legacy_cache_backfill",
                "confidence": confidence,
                "reason": "旧 raw 缓存缺少原始类型审计表，本次由实体缓存字段回补，结论仅供过渡审计使用。",
            }
        )
    return audit_rows


def _build_fund_liquidity_audit_from_entity_cache(
    entity_rows: list[dict[str, object]],
    share_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """兼容旧 raw 缓存缺少 fund_liquidity_audit.csv 的情况，从实体名称回补流动性审计表。"""
    primary_share_lookup = {
        str(row["entity_id"]): str(row["share_class_id"])
        for row in share_rows
        if int(str(row.get("is_primary_share_class") or "0")) == 1
    }
    audit_rows: list[dict[str, object]] = []
    for entity in entity_rows:
        liquidity = classify_fund_liquidity(str(entity.get("entity_name") or entity.get("entity_id") or ""))
        audit_rows.append(
            {
                "entity_id": str(entity.get("entity_id") or ""),
                "entity_name": str(entity.get("entity_name") or ""),
                "share_class_id": primary_share_lookup.get(str(entity.get("entity_id") or ""), str(entity.get("representative_share_class_id") or "")),
                "fund_name": str(entity.get("entity_name") or ""),
                "liquidity_restricted": int(entity.get("liquidity_restricted") or liquidity["liquidity_restricted"]),
                "holding_lock_months": int(entity.get("holding_lock_months") or liquidity["holding_lock_months"]),
                "rule_code": "legacy_cache_backfill" if "liquidity_restricted" in entity else str(liquidity["rule_code"]),
                "confidence": "low" if "liquidity_restricted" in entity else str(liquidity["confidence"]),
                "reason": "旧 raw 缓存缺少流动性审计表，本次由实体名称规则回补，结论仅供过渡审计使用。" if "liquidity_restricted" in entity else str(liquidity["reason"]),
            }
        )
    return audit_rows


def _hydrate_entity_liquidity_fields(
    entity_rows: list[dict[str, object]],
    fund_liquidity_audit_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """把流动性审计结果补回实体主表，兼容旧 raw 缓存缺少相关字段的情况。"""
    liquidity_lookup = {
        str(row.get("entity_id") or ""): row
        for row in fund_liquidity_audit_rows
    }
    hydrated_rows: list[dict[str, object]] = []
    for entity in entity_rows:
        hydrated = dict(entity)
        liquidity_row = liquidity_lookup.get(str(entity.get("entity_id") or ""), {})
        hydrated["liquidity_restricted"] = int(str(hydrated.get("liquidity_restricted") or liquidity_row.get("liquidity_restricted") or "0"))
        hydrated["holding_lock_months"] = int(str(hydrated.get("holding_lock_months") or liquidity_row.get("holding_lock_months") or "0"))
        hydrated_rows.append(hydrated)
    return hydrated_rows


def _build_fund_liquidity_summary(fund_liquidity_audit_rows: list[dict[str, object]]) -> dict[str, object]:
    """从流动性审计表汇总 metadata 摘要，便于报告和缓存兼容复用。"""
    return {
        "entity_count": len(fund_liquidity_audit_rows),
        "restricted_entity_count": sum(int(str(row.get("liquidity_restricted") or "0")) for row in fund_liquidity_audit_rows),
        "restricted_by_rule": {
            rule_code: sum(
                1
                for row in fund_liquidity_audit_rows
                if int(str(row.get("liquidity_restricted") or "0")) == 1 and str(row.get("rule_code") or "") == rule_code
            )
            for rule_code in sorted({str(row.get("rule_code") or "") for row in fund_liquidity_audit_rows if int(str(row.get("liquidity_restricted") or "0")) == 1})
        },
    }


def _group_share_classes(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """把不同份额归并到同一基金实体。"""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        # 当前按“基金公司 + 去份额后名称”归并，是一个工程上可解释的折中方案，后续可升级为更严格主基金映射。
        entity_name = _normalize_entity_name(str(row.get("name") or row["ts_code"]))
        management = str(row.get("management") or "unknown")
        entity_id = f"{management}::{entity_name}"
        grouped[entity_id].append(row)
    return grouped


def _select_representative_share_class(rows: list[dict[str, object]]) -> dict[str, object]:
    """从同一实体的多个份额中选择一个代表份额。"""
    # 代表份额用于承载经理、净值和规模口径，优先选 A 类份额以减少申赎费差异带来的可比性噪声。
    return sorted(rows, key=_share_class_priority, reverse=True)[0]


def _share_class_priority(row: dict[str, object]) -> tuple[int, int, str]:
    """计算份额优先级，用于选择代表份额。"""
    name = str(row.get("name") or "")
    if re.search(r"(A类|A$)", name):
        share_score = 3
    elif re.search(r"(C类|C$)", name):
        share_score = 1
    else:
        share_score = 2
    found_date = str(row.get("found_date") or "")
    # 当 A/C 规则无法区分时，默认更偏向存续状态正常且成立时间更明确的份额。
    return share_score, 1 if row.get("status") == "L" else 0, found_date


def _normalize_entity_name(name: str) -> str:
    """去掉常见份额后缀，得到更稳定的基金实体名称。"""
    normalized = name.strip()
    normalized = re.sub(r"(A类|C类)$", "", normalized)
    normalized = re.sub(r"([AC])$", "", normalized)
    return normalized.strip()


def _normalize_month(raw: object) -> str:
    """把原始日期值标准化为 YYYY-MM。"""
    text = str(raw or "")
    if len(text) >= 6 and text[:6].isdigit():
        return f"{text[:4]}-{text[4:6]}"
    return "2000-01"


def _normalize_date(raw: object) -> str:
    """把原始日期值标准化为 YYYY-MM-DD。"""
    text = str(raw or "")
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    return "2000-01-01"


def _build_share_lookup(share_df: Any) -> list[tuple[str, float]]:
    """构建按日期排序的基金份额序列，供规模回推使用。"""
    if share_df is None or share_df.empty:
        return []
    share_df = share_df.copy().sort_values("trade_date")
    result = []
    for row in share_df.to_dict("records"):
        trade_date = str(row.get("trade_date") or "")
        fd_share = row.get("fd_share")
        if not trade_date or fd_share is None or (isinstance(fd_share, float) and math.isnan(fd_share)):
            continue
        result.append((trade_date, float(fd_share)))
    return result


def _preferred_nav_value(row: Any) -> float:
    """按优先级选择最适合做收益计算的净值字段。"""
    # 优先使用复权净值，是为了让分红等现金事件尽量不扭曲收益计算。
    for field in ["adj_nav", "unit_nav", "accum_nav"]:
        value = row.get(field)
        if value is not None and not (isinstance(value, float) and math.isnan(value)):
            return float(value)
    return 0.0


def _preferred_asset_value(row: Any, share_lookup: list[tuple[str, float]]) -> float:
    """优先从净资产字段读取规模，必要时再回退到份额乘净值近似估算。"""
    total_netasset = row.get("total_netasset")
    # 优先使用 fund_nav 自带净资产，因为它比“份额 * 净值”的回推更接近真实披露口径。
    if total_netasset is not None and not (isinstance(total_netasset, float) and math.isnan(total_netasset)):
        return float(total_netasset) / 1_000_000.0
    net_asset = row.get("net_asset")
    if net_asset is not None and not (isinstance(net_asset, float) and math.isnan(net_asset)):
        return float(net_asset) / 1_000_000.0
    nav_value = _preferred_nav_value(row)
    if nav_value <= 0:
        return 0.0
    nav_date = str(row.get("nav_date") or "")
    latest_share = None
    for trade_date, fd_share in share_lookup:
        if trade_date <= nav_date:
            latest_share = fd_share
        else:
            break
    if latest_share is None:
        return 0.0
    # fund_share 的 fd_share 单位为“万份”，因此资产规模近似换算为 百万元 = 份额(万) * 净值 / 100。
    return latest_share * nav_value / 100.0


def _build_selected_daily_nav_rows(
    selected_nav_df: Any,
    entity_id: str,
    ts_code: str,
) -> list[dict[str, object]]:
    """把选中的日频 PIT 净值版本转换成研究内部日频契约。"""
    if selected_nav_df is None or selected_nav_df.empty:
        return []
    ordered_df = selected_nav_df.copy().sort_values(["nav_date", "normalized_available_date"])
    daily_rows: list[dict[str, object]] = []
    previous_nav = None
    for record in ordered_df.to_dict("records"):
        current_nav = float(record.get("nav_numeric") or 0.0)
        if current_nav <= 0:
            continue
        trade_date = _normalize_date(record.get("nav_date") or "")
        if trade_date == "2000-01-01":
            continue
        if previous_nav in {None, 0}:
            daily_return = 0.0
        else:
            daily_return = current_nav / float(previous_nav) - 1.0
        daily_rows.append(
            {
                "entity_id": entity_id,
                "ts_code": ts_code,
                "trade_date": trade_date,
                "nav_date": trade_date,
                "available_date": _normalize_date(record.get("normalized_available_date") or ""),
                "nav": round(current_nav, 6),
                "daily_return": round(daily_return, 10),
                "assets_cny_mn": round(float(record.get("asset_numeric") or 0.0), 3),
                "selected_update_flag": str(record.get("update_flag") or "0"),
                "selection_reason": "earliest_valid_announcement",
            }
        )
        previous_nav = current_nav
    return daily_rows


def _select_point_in_time_nav_rows(nav_df: Any) -> Any:
    """对同一 ts_code + nav_date 只保留最早公告且净值有效的版本。"""
    if nav_df is None or nav_df.empty:
        return nav_df
    nav_df = nav_df.copy()
    nav_df["nav_date"] = nav_df["nav_date"].astype(str)
    nav_df["normalized_available_date"] = nav_df["normalized_available_date"].astype(str)
    nav_df["nav_completeness_score"] = nav_df.apply(_nav_completeness_score, axis=1)
    nav_df["asset_completeness_score"] = nav_df.apply(_asset_completeness_score, axis=1)
    nav_df["source_row_index"] = list(range(len(nav_df)))
    selected_rows = []
    for _, group in nav_df.groupby(["ts_code", "nav_date"], sort=False):
        valid_group = group[group["nav_numeric"] > 0]
        if valid_group.empty:
            continue
        ordered = valid_group.sort_values(
            [
                "normalized_available_date",
                "nav_completeness_score",
                "asset_completeness_score",
                "update_flag",
                "source_row_index",
            ],
            ascending=[True, False, False, True, True],
        )
        selected_rows.append(ordered.iloc[0].to_dict())
    return nav_df.iloc[0:0] if not selected_rows else nav_df.__class__(selected_rows)


def _select_month_end_trading_day_nav_rows(selected_nav_df: Any, trade_calendar_rows: list[dict[str, object]]) -> Any:
    """对月频研究层只保留每个月最后一个交易日对应的净值记录。"""
    if selected_nav_df is None or selected_nav_df.empty:
        return selected_nav_df
    if not trade_calendar_rows:
        return selected_nav_df
    selected_nav_df = selected_nav_df.copy()
    selected_nav_df["month"] = selected_nav_df["nav_date"].astype(str).str.slice(0, 6).apply(_normalize_month)
    selected_nav_df["normalized_nav_date"] = selected_nav_df["nav_date"].apply(_normalize_date)
    target_nav_date_by_month = {
        month: last_trading_day_of_month(month, trade_calendar_rows)
        for month in sorted({str(value) for value in selected_nav_df["month"].tolist()})
    }
    selected_nav_df["target_nav_date"] = selected_nav_df["month"].map(target_nav_date_by_month)
    filtered_df = selected_nav_df[selected_nav_df["normalized_nav_date"] == selected_nav_df["target_nav_date"]]
    return filtered_df.iloc[0:0] if filtered_df.empty else filtered_df


def _nav_effective_available_date(row: Any) -> str:
    """返回某条 fund_nav 记录在研究口径下的可见日期。"""
    ann_date = str(row.get("ann_date") or "").strip()
    if ann_date:
        return ann_date
    return str(row.get("nav_date") or "")


def _nav_completeness_score(row: Any) -> int:
    """根据净值字段完整程度给 fund_nav 记录打分。"""
    score = 0
    for field in ["adj_nav", "unit_nav", "accum_nav"]:
        value = row.get(field)
        if value is not None and not (isinstance(value, float) and math.isnan(value)):
            score += 1
    return score


def _asset_completeness_score(row: Any) -> int:
    """根据资产字段是否完整给记录打分。"""
    score = 0
    for field in ["total_netasset", "net_asset"]:
        value = row.get(field)
        if value is not None and not (isinstance(value, float) and math.isnan(value)):
            score += 1
    return score

def _manager_record_matches_month(row: dict[str, object], month: str) -> bool:
    """判断一条经理任职记录在某个月是否处于在任状态。"""
    begin_month = _normalize_month(row.get("begin_date") or "20000101")
    end_raw = str(row.get("end_date") or "").strip()
    if month < begin_month:
        return False
    if not end_raw:
        return True
    end_month = _normalize_month(end_raw)
    return month <= end_month
