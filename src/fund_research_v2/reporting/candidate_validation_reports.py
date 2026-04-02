from __future__ import annotations

from pathlib import Path


def render_candidate_validation_report(path: Path, validation: dict[str, object]) -> None:
    """把候选补证结果写成 Markdown 摘要报告。"""
    summary = validation.get("summary", {}) if isinstance(validation.get("summary"), dict) else {}
    style_phase_summary = validation.get("style_phase_summary", {}) if isinstance(validation.get("style_phase_summary"), dict) else {}
    attribution_summary = validation.get("attribution_summary", {}) if isinstance(validation.get("attribution_summary"), dict) else {}
    lines = ["# Candidate Validation Report", ""]
    lines.extend(_render_config_identity(summary))
    lines.extend(["## Executive Summary", ""])
    for key, value in summary.items():
        if key in {"candidate_config", "baseline_config"}:
            continue
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Style Phase Conclusion", ""])
    for key, value in style_phase_summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Excess Attribution Conclusion", ""])
    for key, value in attribution_summary.items():
        lines.append(f"- {key}: {value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_style_phase_report(path: Path, validation: dict[str, object]) -> None:
    """把阶段稳定性验证写成 Markdown 报告。"""
    summary = validation.get("style_phase_summary", {}) if isinstance(validation.get("style_phase_summary"), dict) else {}
    detail_rows = validation.get("style_phase_detail_rows", []) if isinstance(validation.get("style_phase_detail_rows"), list) else []
    window_rows = validation.get("style_phase_window_rows", []) if isinstance(validation.get("style_phase_window_rows"), list) else []
    summary_rows = validation.get("style_phase_summary_rows", []) if isinstance(validation.get("style_phase_summary_rows"), list) else []
    lines = ["# Style Phase Report", "", "## Summary", ""]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Phase Summary", ""])
    for row in summary_rows:
        lines.append(
            f"- {row['phase_dimension']} {row['phase_label']}: months={row['month_count']} "
            f"baseline_excess={row['baseline_excess_return']} candidate_excess={row['candidate_excess_return']} "
            f"delta={row['excess_delta']} win={row['candidate_win_flag']}"
        )
    lines.extend(["", "## Rolling Windows", ""])
    for row in window_rows[:40]:
        lines.append(
            f"- {row['window_type']} {row['start_month']}~{row['end_month']}: months={row['month_count']} "
            f"baseline_excess={row['baseline_excess_return']} candidate_excess={row['candidate_excess_return']} "
            f"delta={row['excess_delta']} win={row['candidate_win_flag']}"
        )
    lines.extend(["", "## Monthly Detail", ""])
    for row in detail_rows[:40]:
        lines.append(
            f"- {row['execution_month']}: market={row['market_direction']} size={row['size_leadership']} "
            f"rebound={row['rebound_state']} baseline_excess={row['baseline_excess_return']} "
            f"candidate_excess={row['candidate_excess_return']} delta={row['excess_delta']}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_excess_attribution_report(path: Path, validation: dict[str, object]) -> None:
    """把超额归因验证写成 Markdown 报告。"""
    summary = validation.get("attribution_summary", {}) if isinstance(validation.get("attribution_summary"), dict) else {}
    monthly_rows = validation.get("attribution_monthly_rows", []) if isinstance(validation.get("attribution_monthly_rows"), list) else []
    lines = ["# Excess Attribution Report", "", "## Summary", ""]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Monthly Attribution", ""])
    for row in monthly_rows[:40]:
        lines.append(
            f"- {row['execution_month']}: baseline_excess={row['baseline_excess_return']} "
            f"candidate_excess={row['candidate_excess_return']} total_delta={row['total_return_delta']} "
            f"benchmark_driven={row['benchmark_driven_delta']} selection_driven={row['selection_driven_delta']}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _render_config_identity(summary: dict[str, object]) -> list[str]:
    """把 candidate 与 baseline 的配置身份固定展示在报告顶部。"""
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
