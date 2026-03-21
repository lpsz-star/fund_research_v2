from __future__ import annotations

from pathlib import Path
from typing import Any

from fund_research_v2.common.io_utils import read_json


def build_experiment_comparison(records: list[dict[str, object]]) -> dict[str, object]:
    """比较最近两次实验记录，输出面向审计的结构化差异。"""
    if len(records) < 2:
        raise RuntimeError("experiment_registry.jsonl 中至少需要两次实验记录，才能执行对比。")
    previous = records[-2]
    current = records[-1]
    previous_label = _record_label(previous)
    current_label = _record_label(current)
    previous_config = previous.get("config", {}) if isinstance(previous.get("config"), dict) else {}
    current_config = current.get("config", {}) if isinstance(current.get("config"), dict) else {}
    previous_snapshot = previous.get("dataset_snapshot", {}) if isinstance(previous.get("dataset_snapshot"), dict) else {}
    current_snapshot = current.get("dataset_snapshot", {}) if isinstance(current.get("dataset_snapshot"), dict) else {}
    previous_type_baseline = previous.get("type_baseline", {}) if isinstance(previous.get("type_baseline"), dict) else {}
    current_type_baseline = current.get("type_baseline", {}) if isinstance(current.get("type_baseline"), dict) else {}
    previous_backtest = previous.get("backtest_summary", {}) if isinstance(previous.get("backtest_summary"), dict) else {}
    current_backtest = current.get("backtest_summary", {}) if isinstance(current.get("backtest_summary"), dict) else {}
    previous_factor = previous.get("factor_evaluation_summary", {}) if isinstance(previous.get("factor_evaluation_summary"), dict) else {}
    current_factor = current.get("factor_evaluation_summary", {}) if isinstance(current.get("factor_evaluation_summary"), dict) else {}
    previous_portfolio = previous.get("portfolio_snapshot_summary", {}) if isinstance(previous.get("portfolio_snapshot_summary"), dict) else {}
    current_portfolio = current.get("portfolio_snapshot_summary", {}) if isinstance(current.get("portfolio_snapshot_summary"), dict) else {}

    comparison = {
        "previous": {
            "label": previous_label,
            "generated_at": previous.get("generated_at", ""),
            "git_commit": previous.get("git_commit", ""),
        },
        "current": {
            "label": current_label,
            "generated_at": current.get("generated_at", ""),
            "git_commit": current.get("git_commit", ""),
        },
        "config_diff": _diff_nested(previous_config, current_config),
        "dataset_diff": _build_dataset_diff(previous_snapshot, current_snapshot),
        "type_baseline_diff": _build_type_baseline_diff(previous_type_baseline, current_type_baseline),
        "backtest_summary_diff": _build_numeric_diff(previous_backtest, current_backtest),
        "factor_evaluation_diff": _build_numeric_diff(previous_factor, current_factor),
        "portfolio_diff_rows": _build_portfolio_diff_rows(previous_portfolio, current_portfolio),
    }
    comparison["summary"] = _build_comparison_summary(comparison)
    return comparison


def read_experiment_records(path: Path) -> list[dict[str, object]]:
    """读取实验登记文件，过滤掉无效 JSONL 行。"""
    if not path.exists():
        raise RuntimeError(f"缺少实验登记文件: {path}")
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = line.strip()
        if not payload:
            continue
        row = read_json_line(payload)
        if isinstance(row, dict):
            records.append(row)
    return records


def read_json_line(payload: str) -> object:
    """解析单行 JSON，便于 JSONL 逐行恢复实验记录。"""
    import json

    return json.loads(payload)


def load_portfolio_snapshot(path: Path) -> dict[str, object]:
    """加载组合快照，供历史兼容场景补齐组合对比输入。"""
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def _record_label(record: dict[str, object]) -> str:
    """用实验标识和生成时间构造稳定标签，便于报告阅读。"""
    experiment_id = str(record.get("experiment_id") or "unknown")
    generated_at = str(record.get("generated_at") or "unknown")
    return f"{experiment_id}@{generated_at}"


def _diff_nested(previous: dict[str, object], current: dict[str, object], prefix: str = "") -> list[dict[str, object]]:
    """递归比较配置快照，输出字段级差异。"""
    rows: list[dict[str, object]] = []
    all_keys = sorted(set(previous) | set(current))
    for key in all_keys:
        previous_value = previous.get(key)
        current_value = current.get(key)
        field_name = f"{prefix}.{key}" if prefix else key
        if isinstance(previous_value, dict) and isinstance(current_value, dict):
            rows.extend(_diff_nested(previous_value, current_value, field_name))
            continue
        if previous_value != current_value:
            rows.append(
                {
                    "field": field_name,
                    "previous_value": _stringify(previous_value),
                    "current_value": _stringify(current_value),
                }
            )
    return rows


def _build_dataset_diff(previous: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    """提取最值得先看的数据快照变化，避免对整份 metadata 做无序 diff。"""
    previous_month_range = previous.get("month_range", {}) if isinstance(previous.get("month_range"), dict) else {}
    current_month_range = current.get("month_range", {}) if isinstance(current.get("month_range"), dict) else {}
    return {
        "source_name": {
            "previous": _stringify(previous.get("source_name")),
            "current": _stringify(current.get("source_name")),
        },
        "entity_count": _numeric_delta(previous.get("entity_count"), current.get("entity_count")),
        "share_class_count": _numeric_delta(previous.get("share_class_count"), current.get("share_class_count")),
        "benchmark_name": {
            "previous": _stringify(previous.get("benchmark_name")),
            "current": _stringify(current.get("benchmark_name")),
        },
        "month_range_start": {
            "previous": _stringify(previous_month_range.get("start")),
            "current": _stringify(current_month_range.get("start")),
        },
        "month_range_end": {
            "previous": _stringify(previous_month_range.get("end")),
            "current": _stringify(current_month_range.get("end")),
        },
        "retained_entity_count": _numeric_delta(
            _dig(previous, "ingestion_audit", "retained_entity_count"),
            _dig(current, "ingestion_audit", "retained_entity_count"),
        ),
        "benchmark_primary_type_map": {
            "previous": previous.get("benchmark_primary_type_map", {}),
            "current": current.get("benchmark_primary_type_map", {}),
        },
    }


def _build_type_baseline_diff(previous: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    """比较基金类型基线，回答样本结构是否发生迁移。"""
    return {
        "latest_month": {
            "previous": _stringify(previous.get("latest_month")),
            "current": _stringify(current.get("latest_month")),
        },
        "entity_count": _numeric_delta(previous.get("entity_count"), current.get("entity_count")),
        "latest_row_count": _numeric_delta(previous.get("latest_row_count"), current.get("latest_row_count")),
        "eligible_count": _numeric_delta(previous.get("eligible_count"), current.get("eligible_count")),
        "entity_type_count": _counter_delta(previous.get("entity_type_count"), current.get("entity_type_count")),
        "latest_type_count": _counter_delta(previous.get("latest_type_count"), current.get("latest_type_count")),
        "eligible_type_count": _counter_delta(previous.get("eligible_type_count"), current.get("eligible_type_count")),
    }


def _build_numeric_diff(previous: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    """比较摘要类数字字段，统一输出 previous/current/delta。"""
    rows: dict[str, object] = {}
    for key in sorted(set(previous) | set(current)):
        rows[key] = _numeric_delta(previous.get(key), current.get(key))
    return rows


def _build_portfolio_diff_rows(previous: dict[str, object], current: dict[str, object]) -> list[dict[str, object]]:
    """比较两次实验的最新组合持仓，回答“哪些基金进出组合”。"""
    previous_rows = previous.get("portfolio", []) if isinstance(previous.get("portfolio"), list) else []
    current_rows = current.get("portfolio", []) if isinstance(current.get("portfolio"), list) else []
    previous_map = {str(row.get("entity_id") or row.get("entity_name") or ""): row for row in previous_rows if isinstance(row, dict)}
    current_map = {str(row.get("entity_id") or row.get("entity_name") or ""): row for row in current_rows if isinstance(row, dict)}
    all_keys = sorted(set(previous_map) | set(current_map))
    diff_rows: list[dict[str, object]] = []
    for entity_key in all_keys:
        previous_row = previous_map.get(entity_key, {})
        current_row = current_map.get(entity_key, {})
        previous_weight = _to_float(previous_row.get("target_weight"))
        current_weight = _to_float(current_row.get("target_weight"))
        diff_rows.append(
            {
                "entity_id": entity_key,
                "entity_name": str(current_row.get("entity_name") or previous_row.get("entity_name") or entity_key),
                "fund_company": str(current_row.get("fund_company") or previous_row.get("fund_company") or ""),
                "change_type": _portfolio_change_type(previous_row, current_row),
                "previous_rank": _stringify(previous_row.get("rank")),
                "current_rank": _stringify(current_row.get("rank")),
                "previous_weight": round(previous_weight, 6),
                "current_weight": round(current_weight, 6),
                "weight_delta": round(current_weight - previous_weight, 6),
            }
        )
    return diff_rows


def _portfolio_change_type(previous_row: dict[str, object], current_row: dict[str, object]) -> str:
    """根据组合是否出现和权重变化，标记持仓变动类型。"""
    if previous_row and current_row:
        if _to_float(previous_row.get("target_weight")) == _to_float(current_row.get("target_weight")):
            return "unchanged"
        return "reweighted"
    if current_row:
        return "added"
    return "removed"


def _build_comparison_summary(comparison: dict[str, object]) -> dict[str, object]:
    """汇总最关键的变化计数，方便报告开头先给高层摘要。"""
    config_diff = comparison.get("config_diff", []) if isinstance(comparison.get("config_diff"), list) else []
    portfolio_diff_rows = comparison.get("portfolio_diff_rows", []) if isinstance(comparison.get("portfolio_diff_rows"), list) else []
    return {
        "config_change_count": len(config_diff),
        "portfolio_added_count": sum(1 for row in portfolio_diff_rows if row.get("change_type") == "added"),
        "portfolio_removed_count": sum(1 for row in portfolio_diff_rows if row.get("change_type") == "removed"),
        "portfolio_reweighted_count": sum(1 for row in portfolio_diff_rows if row.get("change_type") == "reweighted"),
        "entity_count_delta": _dig(comparison, "dataset_diff", "entity_count", "delta"),
        "eligible_count_delta": _dig(comparison, "type_baseline_diff", "eligible_count", "delta"),
        "cumulative_return_delta": _dig(comparison, "backtest_summary_diff", "cumulative_return", "delta"),
        "benchmark_cumulative_return_delta": _dig(comparison, "backtest_summary_diff", "benchmark_cumulative_return", "delta"),
        "excess_cumulative_return_delta": _dig(comparison, "backtest_summary_diff", "excess_cumulative_return", "delta"),
    }


def _counter_delta(previous: object, current: object) -> dict[str, dict[str, object]]:
    """比较类型计数器，保留各分类的增减幅度。"""
    previous_map = previous if isinstance(previous, dict) else {}
    current_map = current if isinstance(current, dict) else {}
    return {
        key: _numeric_delta(previous_map.get(key), current_map.get(key))
        for key in sorted(set(previous_map) | set(current_map))
    }


def _numeric_delta(previous: object, current: object) -> dict[str, object]:
    """统一表示数字型变化，非数字时保留原值但不计算 delta。"""
    previous_number = _to_optional_float(previous)
    current_number = _to_optional_float(current)
    if previous_number is None or current_number is None:
        return {
            "previous": _stringify(previous),
            "current": _stringify(current),
            "delta": "n/a",
        }
    return {
        "previous": round(previous_number, 6),
        "current": round(current_number, 6),
        "delta": round(current_number - previous_number, 6),
    }


def _to_optional_float(value: object) -> float | None:
    """安全把输入转成数字；不合法时返回 None。"""
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float:
    """组合权重差异需要一个稳定缺省值，因此无效输入直接视为 0。"""
    parsed = _to_optional_float(value)
    return 0.0 if parsed is None else parsed


def _stringify(value: object) -> str:
    """把复杂值转成稳定字符串，便于写入报告和 CSV。"""
    if isinstance(value, (dict, list)):
        return str(value)
    if value is None:
        return ""
    return str(value)


def _dig(payload: object, *keys: str) -> object:
    """安全读取多层嵌套字典，避免报告构建时出现 KeyError。"""
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
