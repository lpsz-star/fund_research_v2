from __future__ import annotations

import subprocess
from pathlib import Path

from fund_research_v2.backtest.engine import run_backtest
from fund_research_v2.common.config import AppConfig, load_config, to_serializable_dict
from fund_research_v2.common.date_utils import current_timestamp
from fund_research_v2.common.io_utils import append_jsonl, ensure_directories, write_csv, write_json
from fund_research_v2.data_ingestion.providers import fetch_and_cache_dataset, load_dataset
from fund_research_v2.evaluation.metrics import summarize_backtest
from fund_research_v2.features.feature_builder import build_feature_rows
from fund_research_v2.portfolio.construction import build_portfolio
from fund_research_v2.ranking.scoring_engine import score_funds
from fund_research_v2.reporting.reports import (
    render_backtest_report,
    render_experiment_report,
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
    write_csv(bundle["project_root"] / bundle["config"].paths.feature_dir / "fund_feature_monthly.csv", bundle["feature_rows"])


def run_ranking_command(config_path: Path) -> None:
    """执行到评分阶段，并输出基金打分结果。"""
    bundle = prepare_bundle(config_path)
    write_clean_outputs(bundle)
    write_universe_audit_output(bundle)
    write_csv(bundle["project_root"] / bundle["config"].paths.result_dir / "fund_score_monthly.csv", bundle["score_rows"])


def run_portfolio_command(config_path: Path) -> None:
    """执行到组合阶段，并输出最新一期组合建议。"""
    bundle = prepare_bundle(config_path)
    config: AppConfig = bundle["config"]
    project_root: Path = bundle["project_root"]
    score_rows = bundle["score_rows"]
    latest_month = max(str(row["month"]) for row in score_rows)
    latest_scores = [row for row in score_rows if str(row["month"]) == latest_month]
    portfolio_rows = build_portfolio(config, latest_scores)
    write_clean_outputs(bundle)
    write_universe_audit_output(bundle)
    write_csv(project_root / config.paths.feature_dir / "fund_feature_monthly.csv", bundle["feature_rows"])
    write_csv(project_root / config.paths.result_dir / "fund_score_monthly.csv", score_rows)
    write_portfolio_outputs(bundle, latest_month, latest_scores, portfolio_rows)


def run_backtest_command(config_path: Path) -> None:
    """在统一数据快照上执行完整回测并写出结果。"""
    bundle = prepare_bundle(config_path)
    # 这里仍然复用同一份 bundle，是为了保证回测看到的基金池和评分结果与研究输出完全一致。
    backtest_rows = run_backtest(
        config=bundle["config"],
        score_rows=bundle["score_rows"],
        nav_rows=bundle["dataset"].fund_nav_monthly,
        benchmark_rows=bundle["dataset"].benchmark_monthly,
    )
    backtest_summary = summarize_backtest(backtest_rows)
    write_full_outputs(bundle, backtest_rows, backtest_summary, [])


def run_experiment_command(config_path: Path) -> None:
    """执行完整实验流程，包括组合、回测、报告和实验记录。"""
    bundle = prepare_bundle(config_path)
    latest_month = max(str(row["month"]) for row in bundle["score_rows"])
    # 组合只取最新月评分结果，是因为实验报告默认回答“如果今天运行系统，会给出什么建议”。
    latest_scores = [row for row in bundle["score_rows"] if str(row["month"]) == latest_month]
    portfolio_rows = build_portfolio(bundle["config"], latest_scores)
    backtest_rows = run_backtest(
        config=bundle["config"],
        score_rows=bundle["score_rows"],
        nav_rows=bundle["dataset"].fund_nav_monthly,
        benchmark_rows=bundle["dataset"].benchmark_monthly,
    )
    backtest_summary = summarize_backtest(backtest_rows)
    write_full_outputs(bundle, backtest_rows, backtest_summary, portfolio_rows)


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


def write_clean_outputs(bundle: dict[str, object]) -> None:
    """把标准化后的 clean 层数据持久化到输出目录。"""
    config = bundle["config"]
    project_root = bundle["project_root"]
    dataset = bundle["dataset"]
    universe = bundle["universe"]
    # clean 层是后续所有研究步骤的共同输入，因此优先写出标准化结果而不是零散中间文件。
    write_csv(project_root / config.paths.clean_dir / "fund_entity_master.csv", dataset.fund_entity_master)
    write_csv(project_root / config.paths.clean_dir / "fund_share_class_map.csv", dataset.fund_share_class_map)
    write_csv(project_root / config.paths.clean_dir / "fund_nav_monthly.csv", dataset.fund_nav_monthly)
    write_csv(project_root / config.paths.clean_dir / "benchmark_monthly.csv", dataset.benchmark_monthly)
    write_csv(project_root / config.paths.clean_dir / "manager_assignment_monthly.csv", dataset.manager_assignment_monthly)
    write_csv(project_root / config.paths.clean_dir / "fund_universe_monthly.csv", universe.rows)
    write_json(project_root / config.paths.clean_dir / "dataset_snapshot.json", dataset.metadata)


def write_full_outputs(
    bundle: dict[str, object],
    backtest_rows: list[dict[str, object]],
    backtest_summary: dict[str, object],
    portfolio_rows: list[dict[str, object]],
) -> None:
    """把完整实验产生的特征、结果、报告和实验记录一次性写出。"""
    config: AppConfig = bundle["config"]
    project_root: Path = bundle["project_root"]
    dataset = bundle["dataset"]
    feature_rows = bundle["feature_rows"]
    score_rows = bundle["score_rows"]
    # 只有完整实验才同时产出 feature/result/report/experiment，这样可以把“研究快照”一次性固化下来。
    write_clean_outputs(bundle)
    write_universe_audit_output(bundle)
    write_csv(project_root / config.paths.feature_dir / "fund_feature_monthly.csv", feature_rows)
    write_csv(project_root / config.paths.result_dir / "fund_score_monthly.csv", score_rows)
    latest_month = max((str(row["month"]) for row in score_rows), default=config.as_of_date[:7])
    latest_scores = [row for row in score_rows if str(row["month"]) == latest_month]
    if portfolio_rows:
        write_portfolio_outputs(bundle, latest_month, latest_scores, portfolio_rows)
    write_csv(project_root / config.paths.result_dir / "backtest_monthly.csv", backtest_rows)
    write_json(project_root / config.paths.result_dir / "backtest_summary.json", backtest_summary)
    experiment_record = build_experiment_record(config, project_root, dataset.metadata, backtest_summary, portfolio_rows)
    append_jsonl(project_root / config.paths.experiment_dir / "experiment_registry.jsonl", experiment_record)
    render_backtest_report(project_root / config.paths.report_dir / "backtest_report.md", backtest_rows, backtest_summary)
    render_experiment_report(
        project_root / config.paths.report_dir / "experiment_report.md",
        config=config,
        dataset_metadata=dataset.metadata,
        score_rows=score_rows,
        portfolio_rows=portfolio_rows,
        backtest_summary=backtest_summary,
    )


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
    write_csv(project_root / config.paths.result_dir / "portfolio_target_monthly.csv", portfolio_rows)
    write_json(
        project_root / config.paths.result_dir / "portfolio_snapshot.json",
        {
            "generated_at": current_timestamp(),
            "as_of_date": config.as_of_date,
            "latest_month": latest_month,
            "data_source": config.data_source,
            "benchmark_name": dataset.metadata.get("benchmark_name", config.benchmark.name),
            "eligible_count": len(latest_scores),
            "portfolio_size": len(portfolio_rows),
            "portfolio": portfolio_rows,
        },
    )
    render_portfolio_report(
        project_root / config.paths.report_dir / "portfolio_report.md",
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
        project_root / config.paths.report_dir / "universe_audit_report.md",
        config=config,
        dataset_metadata=dataset.metadata,
        entity_rows=dataset.fund_entity_master,
        universe_rows=universe.rows,
    )


def build_experiment_record(
    config: AppConfig,
    project_root: Path,
    dataset_metadata: dict[str, object],
    backtest_summary: dict[str, object],
    portfolio_rows: list[dict[str, object]],
) -> dict[str, object]:
    """构建单次实验的可追踪记录。"""
    # 实验记录用于追踪“同一套代码+配置+数据快照”产生了什么结果。
    return {
        "experiment_id": f"exp_{config.as_of_date.replace('-', '')}_{config.data_source}",
        "generated_at": current_timestamp(),
        "config": to_serializable_dict(config),
        "dataset_snapshot": dataset_metadata,
        "git_commit": git_commit_hash(project_root),
        "portfolio_size": len(portfolio_rows),
        "backtest_summary": backtest_summary,
        "result_dir": str(project_root / config.paths.result_dir),
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
        project_root / config.paths.raw_dir,
        project_root / config.paths.clean_dir,
        project_root / config.paths.feature_dir,
        project_root / config.paths.result_dir,
        project_root / config.paths.report_dir,
        project_root / config.paths.experiment_dir,
    ]


def git_commit_hash(project_root: Path) -> str:
    """读取当前仓库的 git commit hash，失败时返回 unknown。"""
    try:
        output = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project_root, stderr=subprocess.DEVNULL)
    except Exception:
        return "unknown"
    return output.decode("utf-8").strip()
