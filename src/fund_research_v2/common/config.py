from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UniverseConfig:
    """描述基金池构造规则。"""
    # 基金池约束必须配置化，否则同一策略在不同实验之间会因硬编码而不可追踪。
    allowed_primary_types: list[str]
    exclude_name_keywords: list[str]
    min_history_months: int
    min_assets_cny_mn: float


@dataclass(frozen=True)
class RankingConfig:
    """描述评分阶段的候选数量和因子权重。"""
    # 因子权重属于策略定义的一部分，必须进入实验配置而不是埋在实现细节里。
    candidate_count: int
    factor_weights: dict[str, float]
    category_factors: dict[str, dict[str, float]]


@dataclass(frozen=True)
class PortfolioConfig:
    """描述组合构建时的持仓数量和约束。"""
    portfolio_size: int
    weighting_method: str
    single_fund_cap: float
    single_company_max: int


@dataclass(frozen=True)
class BacktestConfig:
    """描述回测区间、基准字段和成本假设。"""
    # benchmark 字段名通过配置传入，是为了允许未来替换真实指数序列而不改回测引擎。
    start_month: str | None
    end_month: str | None
    benchmark_field: str
    transaction_cost_bps: float


@dataclass(frozen=True)
class BenchmarkConfig:
    """描述市场基准的来源、序列集合与基金类型映射。"""
    # benchmark 不再是假设“全市场只用一条序列”，而是允许不同基金类型映射到不同的公开指数。
    source: str
    default_key: str
    series: dict[str, "BenchmarkSeriesConfig"]
    primary_type_map: dict[str, str]

    def key_for_primary_type(self, primary_type: str) -> str:
        """返回某类基金应使用的 benchmark key；未显式映射时回退到默认基准。"""
        mapped_key = self.primary_type_map.get(primary_type, self.default_key)
        if mapped_key in self.series:
            return mapped_key
        return self.default_key

    def series_for_key(self, key: str) -> "BenchmarkSeriesConfig":
        """根据 key 返回 benchmark 配置，并在异常 key 时安全回退。"""
        return self.series.get(key, self.series[self.default_key])


@dataclass(frozen=True)
class BenchmarkSeriesConfig:
    """描述单条 benchmark 序列的标识信息。"""
    ts_code: str | None
    name: str


@dataclass(frozen=True)
class ReportingConfig:
    """描述报告输出时的展示参数。"""
    top_ranked_limit: int


@dataclass(frozen=True)
class TushareConfig:
    """描述 tushare 数据接入时的抓取边界和缓存策略。"""
    fund_market: str
    fund_status: str
    download_enabled: bool
    use_cached_raw: bool
    start_date: str
    end_date: str | None
    max_funds: int | None
    request_retry_count: int
    request_pause_ms: int
    progress_every_entities: int


@dataclass(frozen=True)
class PathsConfig:
    """描述不同数据层和输出层的目录位置。"""
    raw_dir: Path
    clean_dir: Path
    feature_dir: Path
    result_dir: Path
    report_dir: Path
    experiment_dir: Path


@dataclass(frozen=True)
class AppConfig:
    """聚合整套研究实验所需的配置。"""
    as_of_date: str
    data_source: str
    lookback_months: int
    local_secret_path: Path
    universe: UniverseConfig
    ranking: RankingConfig
    portfolio: PortfolioConfig
    backtest: BacktestConfig
    benchmark: BenchmarkConfig
    reporting: ReportingConfig
    tushare: TushareConfig
    paths: PathsConfig


def scope_artifact_dir(base_path: Path, data_source: str) -> Path:
    """把原始配置目录映射到按数据源隔离后的实际目录。"""
    # sample 和 tushare 共用同一套目录名会互相覆盖产物；这里统一把数据源插入目录层级，避免调用方各自拼路径。
    parts = list(base_path.parts)
    if not parts:
        return base_path / data_source
    if "outputs" in parts:
        index = parts.index("outputs") + 1
        if index < len(parts) and parts[index] == data_source:
            return base_path
        return Path(*parts[:index], data_source, *parts[index:])
    for index in range(len(parts) - 1):
        if parts[index] == "data" and parts[index + 1] == "raw":
            insert_at = index + 2
            if insert_at < len(parts) and parts[insert_at] == data_source:
                return base_path
            return Path(*parts[:insert_at], data_source, *parts[insert_at:])
    return base_path / data_source


def load_config(path: Path) -> AppConfig:
    """从 JSON 文件加载并校验研究配置。"""
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    # 配置在加载时就转成强类型对象，目的是尽早暴露口径错误，而不是等流程跑到中途才失败。
    raw_benchmark = raw.get("benchmark", {})
    benchmark = _load_benchmark_config(raw_benchmark)
    config = AppConfig(
        as_of_date=raw["as_of_date"],
        data_source=raw.get("data_source", "sample"),
        lookback_months=int(raw.get("lookback_months", 48)),
        local_secret_path=Path(raw.get("local_secret_path", "configs/local.json")),
        universe=UniverseConfig(**raw["universe"]),
        ranking=RankingConfig(
            candidate_count=int(raw["ranking"]["candidate_count"]),
            factor_weights={key: float(value) for key, value in raw["ranking"]["factor_weights"].items()},
            category_factors={
                category: {field: float(weight) for field, weight in factors.items()}
                for category, factors in raw["ranking"].get("category_factors", _default_ranking_category_factors()).items()
            },
        ),
        portfolio=PortfolioConfig(
            portfolio_size=int(raw["portfolio"]["portfolio_size"]),
            weighting_method=raw["portfolio"].get("weighting_method", "equal_weight"),
            single_fund_cap=float(raw["portfolio"]["single_fund_cap"]),
            single_company_max=int(raw["portfolio"]["single_company_max"]),
        ),
        backtest=BacktestConfig(
            start_month=raw["backtest"].get("start_month"),
            end_month=raw["backtest"].get("end_month"),
            benchmark_field=raw["backtest"].get("benchmark_field", "benchmark_return_1m"),
            transaction_cost_bps=float(raw["backtest"].get("transaction_cost_bps", 10.0)),
        ),
        benchmark=benchmark,
        reporting=ReportingConfig(top_ranked_limit=int(raw["reporting"].get("top_ranked_limit", 10))),
        tushare=TushareConfig(
            fund_market=raw["tushare"].get("fund_market", "O"),
            fund_status=raw["tushare"].get("fund_status", "L"),
            download_enabled=bool(raw["tushare"].get("download_enabled", False)),
            use_cached_raw=bool(raw["tushare"].get("use_cached_raw", True)),
            start_date=raw["tushare"].get("start_date", "20180101"),
            end_date=raw["tushare"].get("end_date"),
            max_funds=raw["tushare"].get("max_funds"),
            request_retry_count=int(raw["tushare"].get("request_retry_count", 2)),
            request_pause_ms=int(raw["tushare"].get("request_pause_ms", 0)),
            progress_every_entities=int(raw["tushare"].get("progress_every_entities", 10)),
        ),
        paths=PathsConfig(
            raw_dir=Path(raw["paths"]["raw_dir"]),
            clean_dir=Path(raw["paths"]["clean_dir"]),
            feature_dir=Path(raw["paths"]["feature_dir"]),
            result_dir=Path(raw["paths"]["result_dir"]),
            report_dir=Path(raw["paths"]["report_dir"]),
            experiment_dir=Path(raw["paths"]["experiment_dir"]),
        ),
    )
    _validate(config)
    return config


def _validate(config: AppConfig) -> None:
    """在运行前校验配置，避免研究过程因明显口径错误半途失败。"""
    if config.data_source not in {"sample", "tushare"}:
        raise ValueError("data_source 必须是 sample 或 tushare。")
    if config.benchmark.source not in {"sample", "tushare_index"}:
        raise ValueError("benchmark.source 必须是 sample 或 tushare_index。")
    if config.tushare.request_retry_count < 0:
        raise ValueError("tushare.request_retry_count 不能小于 0。")
    if config.tushare.request_pause_ms < 0:
        raise ValueError("tushare.request_pause_ms 不能小于 0。")
    if config.tushare.progress_every_entities <= 0:
        raise ValueError("tushare.progress_every_entities 必须大于 0。")
    if not config.benchmark.series:
        raise ValueError("benchmark.series 不能为空。")
    if config.benchmark.default_key not in config.benchmark.series:
        raise ValueError("benchmark.default_key 必须存在于 benchmark.series 中。")
    for primary_type, benchmark_key in config.benchmark.primary_type_map.items():
        if benchmark_key not in config.benchmark.series:
            raise ValueError(f"benchmark.primary_type_map 中 {primary_type} -> {benchmark_key} 未在 benchmark.series 中定义。")
    if config.benchmark.source == "tushare_index":
        missing_codes = [key for key, series in config.benchmark.series.items() if not str(series.ts_code or "").strip()]
        if missing_codes:
            raise ValueError(f"benchmark.source=tushare_index 时，以下 benchmark 缺少 ts_code: {', '.join(missing_codes)}")
    # 当前只保留一种简单权重法，是为了先固定研究口径，避免组合层复杂度盖过数据与因子问题。
    if config.portfolio.weighting_method != "equal_weight":
        raise ValueError("当前仅支持 equal_weight 组合方法。")
    if config.portfolio.portfolio_size <= 0:
        raise ValueError("portfolio.portfolio_size 必须大于 0。")
    if config.portfolio.single_company_max <= 0:
        raise ValueError("portfolio.single_company_max 必须大于 0。")
    if config.portfolio.single_fund_cap <= 0 or config.portfolio.single_fund_cap > 1:
        raise ValueError("portfolio.single_fund_cap 必须位于 (0, 1]。")
    if sum(config.ranking.factor_weights.values()) <= 0:
        raise ValueError("ranking.factor_weights 总和必须大于 0。")
    if not config.ranking.category_factors:
        raise ValueError("ranking.category_factors 不能为空。")
    for category, factors in config.ranking.category_factors.items():
        if not factors:
            raise ValueError(f"ranking.category_factors.{category} 不能为空。")
        if sum(factors.values()) <= 0:
            raise ValueError(f"ranking.category_factors.{category} 权重和必须大于 0。")
    for field_name, value in {
        "backtest.start_month": config.backtest.start_month,
        "backtest.end_month": config.backtest.end_month,
    }.items():
        if value is not None:
            _validate_month(field_name, value)


def _validate_month(field_name: str, value: str) -> None:
    """校验月字符串是否满足 YYYY-MM 格式。"""
    if len(value) != 7 or value[4] != "-":
        raise ValueError(f"{field_name} 必须是 YYYY-MM 格式。")
    year, month = value[:4], value[5:7]
    if not year.isdigit() or not month.isdigit() or not 1 <= int(month) <= 12:
        raise ValueError(f"{field_name} 必须是 YYYY-MM 格式。")


def to_serializable_dict(config: AppConfig) -> dict[str, Any]:
    """把配置转换为适合落盘到实验记录的可序列化字典。"""
    # 实验记录里保存的是可 JSON 序列化的配置快照，而不是 dataclass 本身。
    return {
        "as_of_date": config.as_of_date,
        "data_source": config.data_source,
        "lookback_months": config.lookback_months,
        "local_secret_path": str(config.local_secret_path),
        "universe": config.universe.__dict__,
        "ranking": {
            "candidate_count": config.ranking.candidate_count,
            "factor_weights": config.ranking.factor_weights,
            "category_factors": config.ranking.category_factors,
        },
        "portfolio": config.portfolio.__dict__,
        "backtest": config.backtest.__dict__,
        "benchmark": benchmark_to_serializable_dict(config.benchmark),
        "reporting": config.reporting.__dict__,
        "tushare": config.tushare.__dict__,
        "paths": {key: str(value) for key, value in config.paths.__dict__.items()},
    }


def _load_benchmark_config(raw_benchmark: dict[str, Any]) -> BenchmarkConfig:
    """兼容旧版单 benchmark 配置与新版多 benchmark 映射配置。"""
    source = raw_benchmark.get("source", "sample")
    raw_series = raw_benchmark.get("series") or raw_benchmark.get("benchmarks")
    default_key = str(raw_benchmark.get("default_key") or "default")
    if isinstance(raw_series, dict) and raw_series:
        series = {
            str(key): BenchmarkSeriesConfig(
                ts_code=value.get("ts_code") if isinstance(value, dict) else None,
                name=str(value.get("name") or key) if isinstance(value, dict) else str(key),
            )
            for key, value in raw_series.items()
        }
    else:
        series = {
            default_key: BenchmarkSeriesConfig(
                ts_code=raw_benchmark.get("ts_code"),
                name=str(raw_benchmark.get("name", "sample_benchmark")),
            )
        }
    primary_type_map = {
        str(key): str(value)
        for key, value in (raw_benchmark.get("primary_type_map") or {}).items()
    }
    return BenchmarkConfig(
        source=source,
        default_key=default_key,
        series=series,
        primary_type_map=primary_type_map,
    )


def benchmark_to_serializable_dict(config: BenchmarkConfig) -> dict[str, Any]:
    """把 benchmark 配置转换成适合落盘和比对的字典。"""
    return {
        "source": config.source,
        "default_key": config.default_key,
        "series": {
            key: {
                "ts_code": series.ts_code,
                "name": series.name,
            }
            for key, series in config.series.items()
        },
        "primary_type_map": config.primary_type_map,
    }


def _default_ranking_category_factors() -> dict[str, dict[str, float]]:
    """返回默认评分体系，保证旧配置不写明细因子时也能按既有口径运行。"""
    return {
        "performance_quality": {
            "ret_12m": 0.5,
            "ret_6m": 0.3,
            "excess_ret_12m": 0.2,
        },
        "risk_control": {
            "max_drawdown_12m": 0.4,
            "vol_12m": 0.3,
            "downside_vol_12m": 0.3,
        },
        "stability_quality": {
            "manager_tenure_months": 0.7,
            "asset_stability_12m": 0.3,
        },
    }
