from __future__ import annotations

from collections import Counter
import subprocess
from pathlib import Path

from fund_research_v2.backtest.engine import run_backtest
from fund_research_v2.common.config import AppConfig, load_config, scope_artifact_dir, to_serializable_dict
from fund_research_v2.common.date_utils import current_timestamp, latest_completed_month
from fund_research_v2.common.io_utils import append_jsonl, ensure_directories, write_csv, write_json
from fund_research_v2.data_ingestion.providers import fetch_and_cache_dataset, load_dataset, warm_failed_api_cache
from fund_research_v2.evaluation.experiment_comparator import build_experiment_comparison, load_portfolio_snapshot, read_experiment_records
from fund_research_v2.evaluation.robustness import build_robustness_analysis, default_baseline_config_path
from fund_research_v2.evaluation.metrics import summarize_backtest
from fund_research_v2.evaluation.factor_evaluator import evaluate_factors
from fund_research_v2.features.feature_builder import build_feature_rows
from fund_research_v2.portfolio.construction import build_portfolio
from fund_research_v2.ranking.scoring_engine import score_funds
from fund_research_v2.reporting.comparison_reports import render_comparison_report
from fund_research_v2.reporting.robustness_reports import render_robustness_report
from fund_research_v2.reporting.reports import (
    render_backtest_report,
    render_experiment_report,
    render_fetch_diagnostics_report,
    render_fetch_retry_report,
    render_factor_evaluation_report,
    render_fund_liquidity_audit_report,
    render_fund_type_audit_report,
    render_ingestion_audit_report,
    render_portfolio_report,
    render_universe_audit_report,
)
from fund_research_v2.universe.filters import build_universe


def fetch_command(config_path: Path) -> None:
    """只执行数据抓取与缓存，不触发研究和回测。"""
    config = load_config(config_path)
    project_root = resolve_project_root(config_path)
    ensure_directories(all_artifact_dirs(config, project_root))
    # fetch 只负责形成本地数据快照，不隐式触发后续研究步骤，避免更新数据与跑实验被混在一起。
    fetch_and_cache_dataset(config, project_root)


def fetch_failed_command(config_path: Path) -> None:
    """只重抓上一次失败的 ts_code，预热单接口缓存。"""
    config = load_config(config_path)
    project_root = resolve_project_root(config_path)
    ensure_directories(all_artifact_dirs(config, project_root))
    refresh_result = warm_failed_api_cache(config, project_root)
    report_dir = artifact_dir(config, project_root, config.paths.report_dir)
    result_dir = artifact_dir(config, project_root, config.paths.result_dir)
    write_json(result_dir / "fetch_retry_summary.json", refresh_result)
    render_fetch_retry_report(report_dir / "fetch_retry_report.md", refresh_result)


def compare_experiments_command(config_path: Path) -> None:
    """比较最近两次完整实验，输出结构化差异与审计报告。"""
    config = load_config(config_path)
    project_root = resolve_project_root(config_path)
    ensure_directories(all_artifact_dirs(config, project_root))
    _refresh_latest_comparison_outputs(config, project_root)


def analyze_robustness_command(config_path: Path) -> None:
    """对候选评分体系相对默认 baseline 做只读稳健性验证。"""
    config = load_config(config_path)
    baseline_config_path = default_baseline_config_path(config_path, config.data_source)
    candidate_bundle = prepare_bundle(config_path)
    baseline_bundle = prepare_bundle(baseline_config_path)
    candidate_config: AppConfig = candidate_bundle["config"]
    project_root: Path = candidate_bundle["project_root"]
    ensure_directories(all_artifact_dirs(candidate_config, project_root))
    analysis = build_robustness_analysis(
        candidate_config=candidate_bundle["config"],
        baseline_config=baseline_bundle["config"],
        dataset=candidate_bundle["dataset"],
        candidate_score_rows=candidate_bundle["score_rows"],
        baseline_score_rows=baseline_bundle["score_rows"],
    )
    result_dir = artifact_dir(candidate_config, project_root, candidate_config.paths.result_dir)
    report_dir = artifact_dir(candidate_config, project_root, candidate_config.paths.report_dir)
    write_json(result_dir / "robustness_summary.json", analysis.get("summary", {}))
    write_csv(result_dir / "robustness_time_slices.csv", analysis.get("time_slice_rows", []))
    write_csv(result_dir / "robustness_month_contribution.csv", analysis.get("month_contribution_rows", []))
    write_csv(result_dir / "robustness_portfolio_behavior.csv", analysis.get("portfolio_behavior_rows", []))
    write_csv(result_dir / "robustness_factor_regime.csv", analysis.get("factor_regime_rows", []))
    render_robustness_report(report_dir / "robustness_report.md", analysis)


def run_universe_command(config_path: Path) -> None:
    """执行到基金池阶段，并输出逐月基金池快照。"""
    bundle = prepare_bundle(config_path)
    write_clean_outputs(bundle)
    write_universe_audit_output(bundle)


def run_feature_command(config_path: Path) -> None:
    """执行到特征阶段，并输出 clean 层和 feature 层数据。"""
    bundle = prepare_bundle(config_path)
    write_clean_outputs(bundle)
    write_universe_audit_output(bundle)
    write_csv(
        artifact_dir(bundle["config"], bundle["project_root"], bundle["config"].paths.feature_dir) / "fund_feature_monthly.csv",
        _annotate_research_month_status(bundle["config"], bundle["feature_rows"]),
    )


def run_ranking_command(config_path: Path) -> None:
    """执行到评分阶段，并输出基金打分结果。"""
    bundle = prepare_bundle(config_path)
    write_clean_outputs(bundle)
    write_universe_audit_output(bundle)
    write_csv(
        artifact_dir(bundle["config"], bundle["project_root"], bundle["config"].paths.result_dir) / "fund_score_monthly.csv",
        _annotate_research_month_status(bundle["config"], bundle["score_rows"]),
    )


def run_portfolio_command(config_path: Path) -> None:
    """执行到组合阶段，并输出最新一期组合建议。"""
    bundle = prepare_bundle(config_path)
    config: AppConfig = bundle["config"]
    project_root: Path = bundle["project_root"]
    score_rows = bundle["score_rows"]
    latest_month = _latest_research_month(config, score_rows)
    latest_scores = [row for row in score_rows if str(row["month"]) == latest_month]
    portfolio_rows = build_portfolio(config, latest_scores)
    write_clean_outputs(bundle)
    write_universe_audit_output(bundle)
    write_csv(
        artifact_dir(config, project_root, config.paths.feature_dir) / "fund_feature_monthly.csv",
        _annotate_research_month_status(config, bundle["feature_rows"]),
    )
    write_csv(
        artifact_dir(config, project_root, config.paths.result_dir) / "fund_score_monthly.csv",
        _annotate_research_month_status(config, score_rows),
    )
    write_portfolio_outputs(bundle, latest_month, latest_scores, portfolio_rows)


def run_backtest_command(config_path: Path) -> None:
    """在统一数据快照上执行完整回测并写出结果。"""
    bundle = prepare_bundle(config_path)
    # 这里仍然复用同一份 bundle，是为了保证回测看到的基金池和评分结果与研究输出完全一致。
    backtest_rows, position_audit_rows = run_backtest(
        config=bundle["config"],
        score_rows=bundle["score_rows"],
        nav_rows=bundle["dataset"].fund_nav_monthly,
        benchmark_rows=bundle["dataset"].benchmark_monthly,
    )
    backtest_summary = summarize_backtest(backtest_rows)
    write_full_outputs(bundle, backtest_rows, position_audit_rows, backtest_summary, [])


def run_experiment_command(config_path: Path) -> None:
    """执行完整实验流程，包括组合、回测、报告和实验记录。"""
    bundle = prepare_bundle(config_path)
    latest_month = _latest_research_month(bundle["config"], bundle["score_rows"])
    # 组合只取最新月评分结果，是因为实验报告默认回答“如果今天运行系统，会给出什么建议”。
    latest_scores = [row for row in bundle["score_rows"] if str(row["month"]) == latest_month]
    portfolio_rows = build_portfolio(bundle["config"], latest_scores)
    backtest_rows, position_audit_rows = run_backtest(
        config=bundle["config"],
        score_rows=bundle["score_rows"],
        nav_rows=bundle["dataset"].fund_nav_monthly,
        benchmark_rows=bundle["dataset"].benchmark_monthly,
    )
    backtest_summary = summarize_backtest(backtest_rows)
    write_full_outputs(bundle, backtest_rows, position_audit_rows, backtest_summary, portfolio_rows)


def prepare_bundle(config_path: Path) -> dict[str, object]:
    """构建一份贯穿研究流程的统一输入包。"""
    config = load_config(config_path)
    project_root = resolve_project_root(config_path)
    ensure_directories(all_artifact_dirs(config, project_root))
    # 工作流统一从同一份数据快照出发，避免不同阶段读取到不一致数据。
    dataset = load_dataset(config, project_root)
    universe = build_universe(config, dataset)
    feature_rows = build_feature_rows(config, dataset, universe)
    score_rows = score_funds(config, feature_rows)
    return {
        "config": config,
        "project_root": project_root,
        "dataset": dataset,
        "universe": universe,
        "feature_rows": feature_rows,
        "score_rows": score_rows,
    }


def _latest_research_month(config: AppConfig, rows: list[dict[str, object]]) -> str:
    """返回研究主链路允许使用的最新正式月份。"""
    available_months = sorted({str(row.get("month", "")) for row in rows if str(row.get("month", ""))})
    if not available_months:
        return latest_completed_month(config.as_of_date)
    completed_cutoff = latest_completed_month(config.as_of_date)
    eligible_months = [month for month in available_months if month <= completed_cutoff]
    # 若快照只剩月内数据而没有完整月，则回退到实际可用的最后一个月，避免因为边界过严导致整条链路报空。
    return eligible_months[-1] if eligible_months else available_months[-1]


def _annotate_research_month_status(config: AppConfig, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """为月频结果增加“正式月 / 观察月”状态，避免把月内快照误读成正式信号。"""
    official_month = _latest_research_month(config, rows)
    completed_cutoff = latest_completed_month(config.as_of_date)
    annotated_rows: list[dict[str, object]] = []
    for row in rows:
        month = str(row.get("month", ""))
        annotated = dict(row)
        annotated["official_research_month"] = 1 if month == official_month else 0
        annotated["research_month_status"] = "official" if month and month <= completed_cutoff else "observation_only"
        annotated_rows.append(annotated)
    return annotated_rows


def write_clean_outputs(bundle: dict[str, object]) -> None:
    """把标准化后的 clean 层数据持久化到输出目录。"""
    config = bundle["config"]
    project_root = bundle["project_root"]
    dataset = bundle["dataset"]
    universe = bundle["universe"]
    # clean 层是后续所有研究步骤的共同输入，因此优先写出标准化结果而不是零散中间文件。
    clean_dir = artifact_dir(config, project_root, config.paths.clean_dir)
    write_csv(clean_dir / "fund_entity_master.csv", dataset.fund_entity_master)
    write_csv(clean_dir / "fund_share_class_map.csv", dataset.fund_share_class_map)
    write_csv(clean_dir / "fund_nav_monthly.csv", dataset.fund_nav_monthly)
    write_csv(clean_dir / "benchmark_monthly.csv", dataset.benchmark_monthly)
    write_csv(clean_dir / "manager_assignment_monthly.csv", dataset.manager_assignment_monthly)
    write_csv(clean_dir / "fund_type_audit.csv", dataset.fund_type_audit)
    write_csv(clean_dir / "fund_liquidity_audit.csv", dataset.fund_liquidity_audit)
    write_csv(clean_dir / "fund_universe_monthly.csv", universe.rows)
    write_json(clean_dir / "dataset_snapshot.json", dataset.metadata)
    ingestion_audit = dataset.metadata.get("ingestion_audit", {}) if isinstance(dataset.metadata.get("ingestion_audit"), dict) else {}
    dropped_entities = ingestion_audit.get("dropped_entities", []) if isinstance(ingestion_audit.get("dropped_entities"), list) else []
    write_csv(clean_dir / "dropped_entities.csv", dropped_entities)


def write_full_outputs(
    bundle: dict[str, object],
    backtest_rows: list[dict[str, object]],
    position_audit_rows: list[dict[str, object]],
    backtest_summary: dict[str, object],
    portfolio_rows: list[dict[str, object]],
) -> None:
    """把完整实验产生的特征、结果、报告和实验记录一次性写出。"""
    config: AppConfig = bundle["config"]
    project_root: Path = bundle["project_root"]
    dataset = bundle["dataset"]
    feature_rows = bundle["feature_rows"]
    score_rows = bundle["score_rows"]
    feature_rows_with_status = _annotate_research_month_status(config, feature_rows)
    score_rows_with_status = _annotate_research_month_status(config, score_rows)
    # 只有完整实验才同时产出 feature/result/report/experiment，这样可以把“研究快照”一次性固化下来。
    write_clean_outputs(bundle)
    write_universe_audit_output(bundle)
    write_csv(artifact_dir(config, project_root, config.paths.feature_dir) / "fund_feature_monthly.csv", feature_rows_with_status)
    write_csv(artifact_dir(config, project_root, config.paths.result_dir) / "fund_score_monthly.csv", score_rows_with_status)
    latest_month = _latest_research_month(config, score_rows)
    latest_scores = [row for row in score_rows if str(row["month"]) == latest_month]
    if portfolio_rows:
        write_portfolio_outputs(bundle, latest_month, latest_scores, portfolio_rows)
    result_dir = artifact_dir(config, project_root, config.paths.result_dir)
    write_csv(result_dir / "backtest_monthly.csv", backtest_rows)
    write_csv(result_dir / "backtest_position_audit.csv", position_audit_rows)
    write_json(result_dir / "backtest_summary.json", backtest_summary)
    factor_evaluation = evaluate_factors(feature_rows, dataset.fund_nav_monthly)
    write_json(result_dir / "factor_evaluation.json", factor_evaluation)
    write_csv(result_dir / "factor_evaluation.csv", factor_evaluation.get("factor_rows", []))
    write_csv(result_dir / "factor_distribution.csv", factor_evaluation.get("distribution_rows", []))
    write_csv(result_dir / "factor_bucket_performance.csv", factor_evaluation.get("bucket_rows", []))
    write_csv(result_dir / "factor_correlation.csv", factor_evaluation.get("correlation_rows", []))
    type_baseline = build_type_baseline_snapshot(
        dataset.fund_entity_master,
        bundle["universe"].rows,
        _latest_research_month(config, bundle["universe"].rows),
    )
    write_json(result_dir / "type_baseline_snapshot.json", type_baseline)
    experiment_record = build_experiment_record(config, project_root, dataset.metadata, backtest_summary, portfolio_rows, type_baseline, factor_evaluation)
    append_jsonl(artifact_dir(config, project_root, config.paths.experiment_dir) / "experiment_registry.jsonl", experiment_record)
    _refresh_latest_comparison_outputs(config, project_root)
    render_backtest_report(artifact_dir(config, project_root, config.paths.report_dir) / "backtest_report.md", backtest_rows, backtest_summary)
    render_factor_evaluation_report(artifact_dir(config, project_root, config.paths.report_dir) / "factor_evaluation_report.md", factor_evaluation)
    render_experiment_report(
        artifact_dir(config, project_root, config.paths.report_dir) / "experiment_report.md",
        config=config,
        dataset_metadata=dataset.metadata,
        score_rows=score_rows,
        portfolio_rows=portfolio_rows,
        backtest_rows=backtest_rows,
        backtest_summary=backtest_summary,
    )


def _refresh_latest_comparison_outputs(config: AppConfig, project_root: Path) -> None:
    """把最近两次完整实验的差异产物刷新到当前数据源的 comparison 文件。"""
    experiment_dir = artifact_dir(config, project_root, config.paths.experiment_dir)
    result_dir = artifact_dir(config, project_root, config.paths.result_dir)
    report_dir = artifact_dir(config, project_root, config.paths.report_dir)
    records = read_experiment_records(experiment_dir / "experiment_registry.jsonl")
    if len(records) < 2:
        return
    hydrated_records = _hydrate_portfolio_summary(records)
    comparison = build_experiment_comparison(hydrated_records)
    write_json(result_dir / "comparison_summary.json", comparison.get("summary", {}))
    write_json(result_dir / "backtest_summary_diff.json", comparison.get("backtest_summary_diff", {}))
    write_json(result_dir / "type_baseline_diff.json", comparison.get("type_baseline_diff", {}))
    write_csv(result_dir / "portfolio_diff.csv", comparison.get("portfolio_diff_rows", []))
    render_comparison_report(report_dir / "comparison_report.md", comparison)


def write_portfolio_outputs(
    bundle: dict[str, object],
    latest_month: str,
    latest_scores: list[dict[str, object]],
    portfolio_rows: list[dict[str, object]],
) -> None:
    """把最新一期组合建议的结果文件和报告保持为同一快照。"""
    config: AppConfig = bundle["config"]
    project_root: Path = bundle["project_root"]
    dataset = bundle["dataset"]
    # 组合 CSV、快照 JSON 和 Markdown 报告必须一起刷新，否则用户会看到同一期组合对应多份不同口径的解释。
    result_dir = artifact_dir(config, project_root, config.paths.result_dir)
    write_csv(result_dir / "portfolio_target_monthly.csv", portfolio_rows)
    write_json(
        result_dir / "portfolio_snapshot.json",
        {
            "generated_at": current_timestamp(),
            "as_of_date": config.as_of_date,
            "latest_month": latest_month,
            "data_source": config.data_source,
            "benchmark_name": dataset.metadata.get(
                "benchmark_name",
                config.benchmark.series_for_key(config.benchmark.default_key).name,
            ),
            "eligible_count": len(latest_scores),
            "portfolio_size": len(portfolio_rows),
            "portfolio": portfolio_rows,
        },
    )
    render_portfolio_report(
        artifact_dir(config, project_root, config.paths.report_dir) / "portfolio_report.md",
        config=config,
        dataset_metadata=dataset.metadata,
        latest_month=latest_month,
        latest_scores=latest_scores,
        portfolio_rows=portfolio_rows,
    )


def write_universe_audit_output(bundle: dict[str, object]) -> None:
    """写出最新月基金池漏斗与剔除原因审计报告。"""
    config: AppConfig = bundle["config"]
    project_root: Path = bundle["project_root"]
    dataset = bundle["dataset"]
    universe = bundle["universe"]
    render_universe_audit_report(
        artifact_dir(config, project_root, config.paths.report_dir) / "universe_audit_report.md",
        config=config,
        dataset_metadata=dataset.metadata,
        entity_rows=dataset.fund_entity_master,
        universe_rows=universe.rows,
    )
    render_ingestion_audit_report(
        artifact_dir(config, project_root, config.paths.report_dir) / "ingestion_audit_report.md",
        config=config,
        dataset_metadata=dataset.metadata,
    )
    render_fund_type_audit_report(
        artifact_dir(config, project_root, config.paths.report_dir) / "fund_type_audit_report.md",
        config=config,
        dataset_metadata=dataset.metadata,
        fund_type_rows=dataset.fund_type_audit,
    )
    render_fund_liquidity_audit_report(
        artifact_dir(config, project_root, config.paths.report_dir) / "fund_liquidity_audit_report.md",
        config=config,
        dataset_metadata=dataset.metadata,
        fund_liquidity_rows=dataset.fund_liquidity_audit,
    )
    render_fetch_diagnostics_report(
        artifact_dir(config, project_root, config.paths.report_dir) / "fetch_diagnostics_report.md",
        dataset_metadata=dataset.metadata,
    )


def build_experiment_record(
    config: AppConfig,
    project_root: Path,
    dataset_metadata: dict[str, object],
    backtest_summary: dict[str, object],
    portfolio_rows: list[dict[str, object]],
    type_baseline: dict[str, object],
    factor_evaluation: dict[str, object],
) -> dict[str, object]:
    """构建单次实验的可追踪记录。"""
    # 实验记录用于追踪“同一套代码+配置+数据快照”产生了什么结果。
    portfolio_latest_month = _latest_research_month(config, portfolio_rows) if portfolio_rows else latest_completed_month(config.as_of_date)
    return {
        "experiment_id": f"exp_{config.as_of_date.replace('-', '')}_{config.data_source}",
        "generated_at": current_timestamp(),
        "config": to_serializable_dict(config),
        "dataset_snapshot": dataset_metadata,
        "git_commit": git_commit_hash(project_root),
        "portfolio_size": len(portfolio_rows),
        "portfolio_snapshot_summary": {
            "latest_month": portfolio_latest_month,
            "portfolio": [
                {
                    "entity_id": str(row.get("entity_id", "")),
                    "entity_name": str(row.get("entity_name", "")),
                    "fund_company": str(row.get("fund_company", "")),
                    "rank": row.get("rank", ""),
                    "target_weight": row.get("target_weight", ""),
                }
                for row in portfolio_rows
            ],
        },
        "type_baseline": type_baseline,
        "factor_evaluation_summary": factor_evaluation.get("summary", {}),
        "backtest_summary": backtest_summary,
        "result_dir": str(artifact_dir(config, project_root, config.paths.result_dir)),
    }


def build_type_baseline_snapshot(
    entity_rows: list[dict[str, object]],
    universe_rows: list[dict[str, object]],
    latest_month: str,
) -> dict[str, object]:
    """构建一份便于跨实验比较的类型分布快照。"""
    latest_rows = [row for row in universe_rows if str(row["month"]) == latest_month]
    eligible_rows = [row for row in latest_rows if int(row["is_eligible"]) == 1]
    entity_type_counter = Counter(str(row.get("primary_type", "")) for row in entity_rows)
    latest_type_counter = Counter(str(row.get("primary_type", "")) for row in latest_rows)
    eligible_type_counter = Counter(str(row.get("primary_type", "")) for row in eligible_rows)
    return {
        "latest_month": latest_month,
        "entity_count": len(entity_rows),
        "latest_row_count": len(latest_rows),
        "eligible_count": len(eligible_rows),
        "entity_type_count": dict(sorted(entity_type_counter.items())),
        "latest_type_count": dict(sorted(latest_type_counter.items())),
        "eligible_type_count": dict(sorted(eligible_type_counter.items())),
    }


def resolve_project_root(config_path: Path) -> Path:
    """根据配置文件路径推断项目根目录。"""
    resolved = config_path.resolve()
    # 这里按 configs 目录反推项目根目录，是为了让命令既能在仓库根目录调用，也能直接传配置文件绝对路径调用。
    if resolved.parent.name == "configs":
        return resolved.parent.parent
    return resolved.parent


def all_artifact_dirs(config: AppConfig, project_root: Path) -> list[Path]:
    """返回当前配置下所有需要预先创建的输出目录。"""
    # 输出目录集中声明，避免不同命令因为忘记建目录而产生“部分成功”的脏状态。
    return [
        artifact_dir(config, project_root, config.paths.raw_dir),
        artifact_dir(config, project_root, config.paths.clean_dir),
        artifact_dir(config, project_root, config.paths.feature_dir),
        artifact_dir(config, project_root, config.paths.result_dir),
        artifact_dir(config, project_root, config.paths.report_dir),
        artifact_dir(config, project_root, config.paths.experiment_dir),
    ]


def artifact_dir(config: AppConfig, project_root: Path, base_dir: Path) -> Path:
    """解析某个配置目录在当前数据源下的真实目录。"""
    return project_root / scope_artifact_dir(base_dir, config.data_source)


def git_commit_hash(project_root: Path) -> str:
    """读取当前仓库的 git commit hash，失败时返回 unknown。"""
    try:
        output = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project_root, stderr=subprocess.DEVNULL)
    except Exception:
        return "unknown"
    return output.decode("utf-8").strip()


def _hydrate_portfolio_summary(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """为旧实验记录补齐组合摘要，避免共享 result 目录导致无法比较持仓。"""
    hydrated_records: list[dict[str, object]] = []
    for record in records:
        hydrated = dict(record)
        portfolio_summary = hydrated.get("portfolio_snapshot_summary")
        if isinstance(portfolio_summary, dict) and isinstance(portfolio_summary.get("portfolio"), list):
            hydrated_records.append(hydrated)
            continue
        result_dir = Path(str(hydrated.get("result_dir") or "")).expanduser()
        snapshot = load_portfolio_snapshot(result_dir / "portfolio_snapshot.json") if str(result_dir) else {}
        hydrated["portfolio_snapshot_summary"] = {
            "latest_month": snapshot.get("latest_month", ""),
            "portfolio": snapshot.get("portfolio", []) if isinstance(snapshot.get("portfolio"), list) else [],
        }
        hydrated_records.append(hydrated)
    return hydrated_records
