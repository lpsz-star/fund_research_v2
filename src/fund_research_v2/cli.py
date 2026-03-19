from __future__ import annotations

import argparse
from pathlib import Path

from fund_research_v2.common.config import load_config
from fund_research_v2.common.workflows import (
    fetch_command,
    run_backtest_command,
    run_experiment_command,
    run_feature_command,
    run_portfolio_command,
    run_ranking_command,
    run_universe_command,
)


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 解析器，显式暴露当前支持的研究工作流命令。"""
    parser = argparse.ArgumentParser(description="Fund Research V2")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name in [
        "fetch",
        "build-universe",
        "compute-features",
        "run-ranking",
        "run-portfolio",
        "run-backtest",
        "run-experiment",
    ]:
        command_parser = subparsers.add_parser(command_name)
        command_parser.add_argument("--config", default="configs/default.json")
    return parser


def main() -> int:
    """解析命令行并分发到对应工作流入口。"""
    parser = build_parser()
    args = parser.parse_args()
    config_path = Path(args.config)
    load_config(config_path)
    command_map = {
        "fetch": fetch_command,
        "build-universe": run_universe_command,
        "compute-features": run_feature_command,
        "run-ranking": run_ranking_command,
        "run-portfolio": run_portfolio_command,
        "run-backtest": run_backtest_command,
        "run-experiment": run_experiment_command,
    }
    command_map[args.command](config_path)
    return 0
