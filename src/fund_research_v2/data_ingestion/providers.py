from __future__ import annotations

import importlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.contracts import DatasetSnapshot
from fund_research_v2.common.date_utils import current_timestamp
from fund_research_v2.common.io_utils import read_csv, read_json, write_csv, write_json
from fund_research_v2.data_processing.sample_data import generate_sample_dataset


def load_dataset(config: AppConfig, project_root: Path) -> DatasetSnapshot:
    """按配置加载研究数据，必要时触发 sample 生成或 tushare 缓存读取。"""
    if config.data_source == "sample":
        dataset = generate_sample_dataset(config.lookback_months)
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
        dataset = generate_sample_dataset(config.lookback_months)
        persist_dataset(config, project_root, dataset)
        return dataset
    token = _load_tushare_token(project_root / config.local_secret_path)
    provider = TushareDataProvider(config, token)
    dataset = provider.fetch()
    # 真实接口抓到的数据必须先固化到 raw 层，后续流程都从快照出发，避免同一实验前后数据漂移。
    persist_dataset(config, project_root, dataset)
    return dataset


def load_cached_dataset(config: AppConfig, project_root: Path) -> DatasetSnapshot | None:
    """从 raw 层读取已缓存的数据快照。"""
    raw_dir = project_root / config.paths.raw_dir
    entity_path = raw_dir / "fund_entity_master.csv"
    share_path = raw_dir / "fund_share_class_map.csv"
    nav_path = raw_dir / "fund_nav_monthly.csv"
    benchmark_path = raw_dir / "benchmark_monthly.csv"
    manager_path = raw_dir / "manager_assignment_monthly.csv"
    snapshot_path = raw_dir / "dataset_snapshot.json"
    if not all(path.exists() for path in [entity_path, share_path, nav_path, benchmark_path, manager_path, snapshot_path]):
        return None
    metadata = read_json(snapshot_path)
    if not _cached_snapshot_matches_config(config, metadata):
        # raw 层是跨命令复用的共享缓存；这里必须先校验口径一致，否则 sample 与 tushare 会互相污染。
        return None
    return DatasetSnapshot(
        fund_entity_master=read_csv(entity_path),
        fund_share_class_map=read_csv(share_path),
        fund_nav_monthly=read_csv(nav_path),
        benchmark_monthly=read_csv(benchmark_path),
        manager_assignment_monthly=read_csv(manager_path),
        metadata=metadata,
    )


def persist_dataset(config: AppConfig, project_root: Path, dataset: DatasetSnapshot) -> None:
    """把统一数据契约落盘到 raw 层。"""
    raw_dir = project_root / config.paths.raw_dir
    # raw 层按“研究内部契约”落盘，而不是保存 tushare 原始 JSON；目的是保证后续模块不依赖外部字段细节。
    write_csv(raw_dir / "fund_entity_master.csv", dataset.fund_entity_master)
    write_csv(raw_dir / "fund_share_class_map.csv", dataset.fund_share_class_map)
    write_csv(raw_dir / "fund_nav_monthly.csv", dataset.fund_nav_monthly)
    write_csv(raw_dir / "benchmark_monthly.csv", dataset.benchmark_monthly)
    write_csv(raw_dir / "manager_assignment_monthly.csv", dataset.manager_assignment_monthly)
    write_json(raw_dir / "dataset_snapshot.json", dataset.metadata)


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
    # 真实基金快照的规模口径升级后，需要主动淘汰旧缓存，否则会继续复用“代表份额规模”这一错误结果。
    if str(metadata.get("entity_asset_aggregation") or "").strip() != "sum_of_share_classes":
        return False
    benchmark_source = str(metadata.get("benchmark_source") or "").strip()
    if benchmark_source != config.benchmark.source:
        return False
    if config.benchmark.source == "tushare_index":
        cached_ts_code = str(metadata.get("benchmark_ts_code") or "").strip()
        expected_ts_code = str(config.benchmark.ts_code or "").strip()
        if cached_ts_code != expected_ts_code:
            return False
    return True


class TushareDataProvider:
    """把 tushare 基金接口映射为项目内部的数据快照。"""

    def __init__(self, config: AppConfig, token: str) -> None:
        """初始化 tushare 客户端和依赖模块。"""
        self.config = config
        self.token = token
        self.pd = _require_module("pandas")
        self.tushare = _require_module("tushare")
        self.client = self.tushare.pro_api(token)

    def fetch(self) -> DatasetSnapshot:
        """抓取基金主数据、经理、净值和规模，并组装成研究快照。"""
        # fund_basic 是基金场景的主入口；先拿到基金全集，再决定哪些份额会被归并成同一实体。
        fund_basic = self.client.fund_basic(market=self.config.tushare.fund_market, status=self.config.tushare.fund_status)
        if fund_basic is None or fund_basic.empty:
            raise RuntimeError("Tushare fund_basic 返回空结果。")
        company_df = self.client.fund_company()
        company_lookup = _build_company_lookup(company_df)
        fund_basic = fund_basic.copy().sort_values("ts_code")
        if self.config.tushare.max_funds:
            fund_basic = fund_basic.head(self.config.tushare.max_funds)

        fund_entity_master: list[dict[str, object]] = []
        share_class_map: list[dict[str, object]] = []
        nav_rows: list[dict[str, object]] = []
        benchmark_rows: list[dict[str, object]] = []
        manager_rows: list[dict[str, object]] = []
        grouped_rows = _group_share_classes(fund_basic.to_dict("records"))
        for entity_id, rows in grouped_rows.items():
            representative_row = _select_representative_share_class(rows)
            # 后续特征和回测都以“基金实体”而不是份额类为单位，避免 A/C 份额重复入选。
            fund_company = str(representative_row.get("management") or "unknown")
            company_meta = company_lookup.get(fund_company, {})
            manager_name, manager_begin_date = self._fetch_current_manager(str(representative_row["ts_code"]))
            latest_assets_cny_mn, entity_nav_rows = self._fetch_entity_monthly_nav_rows(rows, entity_id)
            if not entity_nav_rows:
                # 没有可用月频净值的基金不能进入研究层，否则后续收益窗口和回测口径都无法成立。
                continue
            manager_rows.extend(self._build_manager_assignment_rows(str(representative_row["ts_code"]), entity_id, entity_nav_rows))
            normalized_name = _normalize_entity_name(str(representative_row.get("name") or representative_row["ts_code"]))
            fund_entity_master.append(
                {
                    "entity_id": entity_id,
                    "entity_name": normalized_name,
                    "primary_type": _map_primary_type(str(representative_row.get("fund_type") or "")),
                    "fund_company": fund_company,
                    "fund_company_province": company_meta.get("province", ""),
                    "fund_company_city": company_meta.get("city", ""),
                    "fund_company_website": company_meta.get("website", ""),
                    "manager_name": manager_name,
                    "manager_start_month": _normalize_month(manager_begin_date),
                    "inception_month": _normalize_month(representative_row.get("found_date") or representative_row.get("issue_date") or "20000101"),
                    "latest_assets_cny_mn": latest_assets_cny_mn,
                    "status": representative_row.get("status") or "L",
                    "custodian": representative_row.get("custodian") or "",
                    "benchmark_text": representative_row.get("benchmark") or "",
                    "invest_type": representative_row.get("invest_type") or "",
                    "representative_share_class_id": representative_row["ts_code"],
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
            nav_rows.extend(entity_nav_rows)

        month_set = sorted({str(row["month"]) for row in nav_rows})
        benchmark_rows = self._fetch_benchmark_rows(month_set)
        if not fund_entity_master or not nav_rows:
            raise RuntimeError("Tushare 基金数据未形成有效的实体主表或月频净值表。")
        return DatasetSnapshot(
            fund_entity_master=fund_entity_master,
            fund_share_class_map=share_class_map,
            fund_nav_monthly=nav_rows,
            benchmark_monthly=benchmark_rows,
            manager_assignment_monthly=manager_rows,
            metadata={
                "source_name": "tushare",
                "generated_at": current_timestamp(),
                "entity_count": len(fund_entity_master),
                "share_class_count": len(share_class_map),
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
                "benchmark_name": self.config.benchmark.name,
                "benchmark_source": self.config.benchmark.source,
                "benchmark_ts_code": self.config.benchmark.ts_code,
                "entity_asset_aggregation": "sum_of_share_classes",
            },
        )

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
        try:
            return self.client.fund_manager(ts_code=ts_code)
        except Exception:
            return None

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

    def _fetch_monthly_nav_rows(self, ts_code: str, entity_id: str) -> tuple[float, list[dict[str, object]]]:
        """把单份额净值和份额数据整理为月频净值与规模序列。"""
        try:
            nav_df = self.client.fund_nav(
                ts_code=ts_code,
                start_date=self.config.tushare.start_date,
                end_date=self.config.tushare.end_date,
            )
        except Exception:
            return 0.0, []
        if nav_df is None or nav_df.empty:
            return 0.0, []
        try:
            share_df = self.client.fund_share(
                ts_code=ts_code,
                start_date=self.config.tushare.start_date,
                end_date=self.config.tushare.end_date,
                market=self.config.tushare.fund_market,
            )
        except Exception:
            share_df = None
        share_lookup = _build_share_lookup(share_df)
        nav_df = nav_df.copy()
        nav_df["nav_date"] = nav_df["nav_date"].astype(str)
        nav_df["ann_date"] = nav_df["ann_date"].fillna("").astype(str)
        nav_df["update_flag"] = nav_df["update_flag"].fillna("0").astype(str)
        nav_df["nav_numeric"] = nav_df.apply(_preferred_nav_value, axis=1)
        nav_df["asset_numeric"] = nav_df.apply(lambda row: _preferred_asset_value(row, share_lookup), axis=1)
        # 同一 nav_date 可能有多次更新；这里取排序后的最后一条，等价于尽量采用最新披露版本。
        nav_df = nav_df.sort_values(["nav_date", "update_flag", "ann_date"])
        monthly_rows = []
        previous_nav = None
        for _, group in nav_df.groupby(nav_df["nav_date"].str.slice(0, 6), sort=True):
            record = group.iloc[-1]
            current_nav = float(record["nav_numeric"])
            if current_nav <= 0:
                continue
            month = _normalize_month(record["nav_date"])
            # available_date 使用公告日优先，是为了给未来引入数据可得性约束预留真实时间边界。
            current_assets = float(record["asset_numeric"]) if not math.isnan(float(record["asset_numeric"])) else 0.0
            monthly_rows.append(
                {
                    "entity_id": entity_id,
                    "month": month,
                    "nav_date": _normalize_date(record["nav_date"]),
                    "available_date": _normalize_date(record["ann_date"] or record["nav_date"]),
                    "nav": round(current_nav, 6),
                    "return_1m": round(0.0 if previous_nav in {None, 0} else current_nav / previous_nav - 1.0, 6),
                    "assets_cny_mn": round(current_assets, 3),
                }
            )
            previous_nav = current_nav
        latest_assets = monthly_rows[-1]["assets_cny_mn"] if monthly_rows else 0.0
        return float(latest_assets), monthly_rows

    def _fetch_entity_monthly_nav_rows(self, share_class_rows: list[dict[str, object]], entity_id: str) -> tuple[float, list[dict[str, object]]]:
        """以代表份额承载收益序列，并把同实体各份额规模汇总到实体层。"""
        representative_row = _select_representative_share_class(share_class_rows)
        representative_assets, representative_nav_rows = self._fetch_monthly_nav_rows(str(representative_row["ts_code"]), entity_id)
        if not representative_nav_rows:
            return representative_assets, []
        asset_rows_by_share_class: list[list[dict[str, object]]] = []
        for row in share_class_rows:
            _, share_nav_rows = self._fetch_monthly_nav_rows(str(row["ts_code"]), entity_id)
            if share_nav_rows:
                asset_rows_by_share_class.append(share_nav_rows)
        if not asset_rows_by_share_class:
            return representative_assets, representative_nav_rows
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
        latest_assets = merged_rows[-1]["assets_cny_mn"] if merged_rows else representative_assets
        return float(latest_assets), merged_rows

    def _fetch_benchmark_rows(self, month_set: list[str]) -> list[dict[str, object]]:
        """抓取市场基准并转换成月频收益序列。"""
        if not month_set:
            return []
        if self.config.benchmark.source != "tushare_index" or not self.config.benchmark.ts_code:
            return [
                {
                    "month": month,
                    "benchmark_return_1m": 0.0,
                    "benchmark_name": self.config.benchmark.name,
                    "available_date": _normalize_date(f"{month[:4]}{month[5:7]}28"),
                }
                for month in month_set
            ]

        start_date = f"{month_set[0][:4]}{month_set[0][5:7]}01"
        end_month = month_set[-1]
        end_date = f"{end_month[:4]}{end_month[5:7]}31"
        index_df = self.client.index_daily(
            ts_code=self.config.benchmark.ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        if index_df is None or index_df.empty:
            raise RuntimeError(f"基准指数 {self.config.benchmark.ts_code} 未返回有效行情数据。")
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
                        "benchmark_name": self.config.benchmark.name,
                        "benchmark_ts_code": self.config.benchmark.ts_code,
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
                    "benchmark_name": self.config.benchmark.name,
                    "benchmark_ts_code": self.config.benchmark.ts_code,
                    "available_date": _normalize_date(monthly_trade_date[month]),
                }
            )
            previous_close = close
        return rows


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


def _map_primary_type(fund_type: str) -> str:
    """把 tushare 的基金类型粗映射到项目当前的研究类型。"""
    if "股票" in fund_type:
        return "主动股票"
    if "混合" in fund_type:
        return "偏股混合"
    return "其他"


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
