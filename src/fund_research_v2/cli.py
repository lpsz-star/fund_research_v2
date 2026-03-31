from __future__ import annotations

import argparse
from pathlib import Path

from fund_research_v2.common.config import load_config
from fund_research_v2.common.workflows import (
    analyze_robustness_command,
    audit_field_availability_command,
    compare_experiments_command,
    fetch_command,
    fetch_failed_command,
    run_backtest_command,
    run_experiment_command,
    run_feature_command,
    run_portfolio_command,
    run_ranking_command,
    run_universe_command,
    validate_baseline_candidate_command,
)
from fund_research_v2.web.viewer import serve_web_command


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 解析器，显式暴露当前支持的研究工作流命令。"""
    parser = argparse.ArgumentParser(description="Fund Research V2")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name in [
        "fetch",
        "fetch-failed",
        "compare-experiments",
        "analyze-robustness",
        "audit-field-availability",
        "validate-baseline-candidate",
        "build-universe",
        "compute-features",
        "run-ranking",
        "run-portfolio",
        "run-backtest",
        "run-experiment",
        "serve-web",
    ]:
        command_parser = subparsers.add_parser(command_name)
        command_parser.add_argument("--config", default="configs/default.json")
        if command_name == "run-experiment":
            command_parser.add_argument(
                "--fast",
                action="store_true",
                help="跳过因子评估与最近两次实验对比刷新，只保留主链路产物。",
            )
        if command_name == "serve-web":
            command_parser.add_argument("--host", default="127.0.0.1")
            command_parser.add_argument("--port", type=int, default=8000)
    return parser


def main() -> int:
    """解析命令行并分发到对应工作流入口。"""
    parser = build_parser()
    args = parser.parse_args()
    config_path = Path(args.config)
    load_config(config_path)
    command_map = {
        "fetch": fetch_command,
        "fetch-failed": fetch_failed_command,
        "compare-experiments": compare_experiments_command,
        "analyze-robustness": analyze_robustness_command,
        "audit-field-availability": audit_field_availability_command,
        "validate-baseline-candidate": validate_baseline_candidate_command,
        "build-universe": run_universe_command,
        "compute-features": run_feature_command,
        "run-ranking": run_ranking_command,
        "run-portfolio": run_portfolio_command,
        "run-backtest": run_backtest_command,
    }
    if args.command == "serve-web":
        serve_web_command(config_path, host=args.host, port=args.port)
        return 0
    if args.command == "run-experiment":
        run_experiment_command(config_path, fast_mode=bool(getattr(args, "fast", False)))
        return 0
    command_map[args.command](config_path)
    return 0
