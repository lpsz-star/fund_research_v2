from __future__ import annotations

from pathlib import Path


def render_robustness_report(path: Path, analysis: dict[str, object]) -> None:
    """把稳健性验证结果写成 Markdown 报告。"""
    summary = analysis.get("summary", {}) if isinstance(analysis.get("summary"), dict) else {}
    time_slice_rows = analysis.get("time_slice_rows", []) if isinstance(analysis.get("time_slice_rows"), list) else []
    contribution_rows = analysis.get("month_contribution_rows", []) if isinstance(analysis.get("month_contribution_rows"), list) else []
    portfolio_behavior_rows = analysis.get("portfolio_behavior_rows", []) if isinstance(analysis.get("portfolio_behavior_rows"), list) else []
    factor_regime_rows = analysis.get("factor_regime_rows", []) if isinstance(analysis.get("factor_regime_rows"), list) else []
    lines = ["# Robustness Report", ""]
    lines.extend(_render_config_identity(summary))
    lines.extend(["## Executive Summary", ""])
    for key, value in summary.items():
        if key in {"candidate_config", "baseline_config"}:
            continue
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Time Slice Comparison", ""])
    for row in time_slice_rows[:40]:
        lines.append(
            f"- {row['scheme']} {row['slice_type']} {row['slice_label']}: "
            f"months={row['month_count']} excess={row['excess_cumulative_return']} "
            f"annualized_return={row['annualized_return']} max_drawdown={row['max_drawdown']} "
            f"avg_turnover={row['avg_turnover']}"
        )
    lines.extend(["", "## Return Concentration", ""])
    for row in sorted(contribution_rows, key=lambda item: abs(float(item.get("excess_return", 0.0))), reverse=True)[:10]:
        lines.append(
            f"- {row['month']}: excess={row['excess_return']} cumulative_excess={row['cumulative_excess_return_after_month']} "
            f"top_positive={row['is_top_positive_contributor']} top_negative={row['is_top_negative_contributor']}"
        )
    lines.extend(["", "## Portfolio Behavior", ""])
    for row in portfolio_behavior_rows[:30]:
        lines.append(
            f"- {row['scheme']} {row['month']}: holdings={row['holdings']} top1={row['top1_weight']} "
            f"top3={row['top3_weight_sum']} companies={row['company_count']} overlap={row['weight_overlap_ratio']}"
        )
    lines.extend(["", "## Factor Regime Stability", ""])
    for row in factor_regime_rows[:40]:
        lines.append(
            f"- {row['slice_type']} {row['slice_label']} {row['factor_name']}: "
            f"months={row['evaluation_months']} avg_rankic={row['avg_rankic']} "
            f"positive_ratio={row['positive_rankic_ratio']} top_bottom={row['avg_top_bottom_next_return']}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _render_config_identity(summary: dict[str, object]) -> list[str]:
    """优先把候选与 baseline 的配置身份写在报告开头，便于评审时直接核对。"""
    lines = ["## Config Identity", ""]
    for label, key in [("Candidate", "candidate_config"), ("Baseline", "baseline_config")]:
        value = summary.get(key, {})
        if isinstance(value, dict):
            lines.append(
                f"- {label}: path={value.get('config_path', '')} "
                f"fingerprint={value.get('config_fingerprint', '')} data_source={value.get('data_source', '')}"
            )
        else:
            lines.append(f"- {label}: {value}")
    lines.extend([""])
    return lines
