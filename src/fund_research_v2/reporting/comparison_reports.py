from __future__ import annotations

from pathlib import Path


def render_comparison_report(path: Path, comparison: dict[str, object]) -> None:
    """把最近两次实验差异写成 Markdown 报告。"""
    summary = comparison.get("summary", {}) if isinstance(comparison.get("summary"), dict) else {}
    previous = comparison.get("previous", {}) if isinstance(comparison.get("previous"), dict) else {}
    current = comparison.get("current", {}) if isinstance(comparison.get("current"), dict) else {}
    config_diff = comparison.get("config_diff", []) if isinstance(comparison.get("config_diff"), list) else []
    portfolio_diff_rows = comparison.get("portfolio_diff_rows", []) if isinstance(comparison.get("portfolio_diff_rows"), list) else []
    lines = [
        "# Comparison Report",
        "",
        "## Comparison Context",
        "",
        f"- previous: {previous.get('label', 'n/a')}",
        f"- previous_git_commit: {previous.get('git_commit', 'n/a')}",
        f"- current: {current.get('label', 'n/a')}",
        f"- current_git_commit: {current.get('git_commit', 'n/a')}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Config Diff", ""])
    if config_diff:
        for row in config_diff:
            lines.append(
                f"- {row.get('field', '')}: previous={row.get('previous_value', '')} "
                f"current={row.get('current_value', '')}"
            )
    else:
        lines.append("- no_config_change")
    lines.extend(["", "## Dataset Diff", ""])
    for key, payload in (comparison.get("dataset_diff", {}) if isinstance(comparison.get("dataset_diff"), dict) else {}).items():
        lines.append(f"- {key}: {payload}")
    lines.extend(["", "## Type Baseline Diff", ""])
    for key, payload in (comparison.get("type_baseline_diff", {}) if isinstance(comparison.get("type_baseline_diff"), dict) else {}).items():
        lines.append(f"- {key}: {payload}")
    lines.extend(["", "## Backtest Summary Diff", ""])
    for key, payload in (comparison.get("backtest_summary_diff", {}) if isinstance(comparison.get("backtest_summary_diff"), dict) else {}).items():
        lines.append(f"- {key}: {payload}")
    lines.extend(["", "## Factor Evaluation Diff", ""])
    for key, payload in (comparison.get("factor_evaluation_diff", {}) if isinstance(comparison.get("factor_evaluation_diff"), dict) else {}).items():
        lines.append(f"- {key}: {payload}")
    lines.extend(["", "## Portfolio Diff", ""])
    if portfolio_diff_rows:
        for row in portfolio_diff_rows:
            lines.append(
                f"- {row.get('entity_name', row.get('entity_id', ''))}: change_type={row.get('change_type', '')} "
                f"previous_rank={row.get('previous_rank', '')} current_rank={row.get('current_rank', '')} "
                f"previous_weight={row.get('previous_weight', '')} current_weight={row.get('current_weight', '')}"
            )
    else:
        lines.append("- portfolio_diff_unavailable")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
