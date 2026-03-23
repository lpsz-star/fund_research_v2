from __future__ import annotations

from collections import defaultdict
from math import ceil, isfinite, sqrt

from fund_research_v2.common.date_utils import add_months

# 这里显式列出当前参与研究的原子因子与方向，避免评估口径悄悄漂移。
FACTOR_SPECS: list[dict[str, object]] = [
    {"field": "ret_12m", "direction": "high"},
    {"field": "ret_6m", "direction": "high"},
    {"field": "excess_ret_3m", "direction": "high"},
    {"field": "excess_ret_6m", "direction": "high"},
    {"field": "excess_ret_12m", "direction": "high"},
    {"field": "excess_consistency_12m", "direction": "high"},
    {"field": "excess_hit_rate_12m", "direction": "high"},
    {"field": "excess_streak_6m", "direction": "high"},
    {"field": "max_drawdown_12m", "direction": "high"},
    {"field": "drawdown_recovery_ratio_12m", "direction": "high"},
    {"field": "drawdown_duration_ratio_12m", "direction": "low"},
    {"field": "hit_rate_12m", "direction": "high"},
    {"field": "profit_loss_ratio_12m", "direction": "high"},
    {"field": "worst_3m_avg_return_12m", "direction": "high"},
    {"field": "manager_post_change_excess_delta_12m", "direction": "high"},
    {"field": "manager_post_change_downside_vol_delta_12m", "direction": "low"},
    {"field": "vol_12m", "direction": "low"},
    {"field": "downside_vol_12m", "direction": "low"},
    {"field": "tail_loss_ratio_12m", "direction": "low"},
    {"field": "manager_change_count_24m", "direction": "low"},
    {"field": "manager_tenure_months", "direction": "high"},
    {"field": "asset_stability_12m", "direction": "low"},
    {"field": "asset_growth_6m", "direction": "high"},
    {"field": "asset_flow_volatility_12m", "direction": "low"},
]


def evaluate_factors(
    feature_rows: list[dict[str, object]],
    nav_rows: list[dict[str, object]],
) -> dict[str, object]:
    """评估当前核心因子对下一月收益的区分度、方向性和稳定性。"""
    next_return_lookup = {(str(row["entity_id"]), str(row["month"])): float(row["return_1m"]) for row in nav_rows}
    eligible_by_month: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in feature_rows:
        if int(row["is_eligible"]) == 1:
            eligible_by_month[str(row["month"])].append(row)

    factor_rows: list[dict[str, object]] = []
    distribution_rows: list[dict[str, object]] = []
    bucket_rows: list[dict[str, object]] = []
    for spec in FACTOR_SPECS:
        field = str(spec["field"])
        direction = str(spec["direction"])
        month_rankics: list[float] = []
        month_spreads: list[float] = []
        bucket_months: list[dict[str, float]] = []
        positive_months = 0
        negative_months = 0
        evaluation_months = 0
        distribution_rows.append(_build_distribution_row(feature_rows, field))
        for month, rows in sorted(eligible_by_month.items()):
            samples = []
            next_month = add_months(month, 1)
            for row in rows:
                entity_id = str(row["entity_id"])
                next_return = next_return_lookup.get((entity_id, next_month))
                factor_value = _to_float(row.get(field))
                if next_return is None or factor_value is None:
                    continue
                samples.append(
                    {
                        "entity_id": entity_id,
                        "factor_value": factor_value,
                        "next_return_1m": float(next_return),
                    }
                )
            if len(samples) < 2:
                continue
            rankic = _rank_correlation(samples, "factor_value", "next_return_1m", ascending=(direction == "low"))
            spread = _top_bottom_spread(samples, ascending=(direction == "low"))
            month_rankics.append(rankic)
            month_spreads.append(spread)
            evaluation_months += 1
            if rankic > 0:
                positive_months += 1
            elif rankic < 0:
                negative_months += 1
            bucket_summary = _bucket_performance(samples, bucket_count=5, ascending=(direction == "low"))
            if bucket_summary is not None:
                bucket_months.append(bucket_summary)
        avg_rankic = _safe_mean(month_rankics)
        rankic_ir = _information_ratio(month_rankics)
        avg_spread = _safe_mean(month_spreads)
        factor_rows.append(
            {
                "factor_name": field,
                "direction": direction,
                "evaluation_months": evaluation_months,
                "avg_rankic": round(avg_rankic, 6),
                "rankic_ir": round(rankic_ir, 6),
                "positive_rankic_ratio": round(positive_months / evaluation_months, 6) if evaluation_months else 0.0,
                "negative_rankic_ratio": round(negative_months / evaluation_months, 6) if evaluation_months else 0.0,
                "avg_top_bottom_next_return": round(avg_spread, 6),
                "direction_ok": 1 if avg_rankic > 0 else 0,
            }
        )
        bucket_rows.append(_build_bucket_row(field, direction, bucket_months))

    factor_rows.sort(key=lambda item: (-float(item["avg_rankic"]), -float(item["avg_top_bottom_next_return"]), str(item["factor_name"])))
    distribution_rows.sort(key=lambda item: str(item["factor_name"]))
    bucket_rows.sort(key=lambda item: str(item["factor_name"]))
    correlation_rows = _build_correlation_rows(eligible_by_month)
    high_correlation_rows = [row for row in correlation_rows if int(row["high_correlation_flag"]) == 1]
    return {
        "factor_rows": factor_rows,
        "distribution_rows": distribution_rows,
        "bucket_rows": bucket_rows,
        "correlation_rows": correlation_rows,
        "summary": {
            "factor_count": len(factor_rows),
            "strong_factor_count": sum(1 for row in factor_rows if float(row["avg_rankic"]) > 0 and float(row["avg_top_bottom_next_return"]) > 0),
            "weak_factor_count": sum(1 for row in factor_rows if float(row["avg_rankic"]) <= 0),
            "high_correlation_pair_count": len(high_correlation_rows),
        },
    }


def _build_distribution_row(feature_rows: list[dict[str, object]], field: str) -> dict[str, object]:
    """汇总单个因子在可投样本中的分布特征，用于判断离散度和极端值风险。"""
    total_rows = 0
    values: list[float] = []
    for row in feature_rows:
        if int(row["is_eligible"]) != 1:
            continue
        total_rows += 1
        value = _to_float(row.get(field))
        if value is not None:
            values.append(value)
    missing_count = total_rows - len(values)
    return {
        "factor_name": field,
        "sample_count": len(values),
        "missing_count": missing_count,
        "missing_ratio": round(missing_count / total_rows, 6) if total_rows else 0.0,
        "mean": round(_safe_mean(values), 6),
        "std": round(_std(values), 6),
        "min": round(min(values), 6) if values else 0.0,
        "p10": round(_percentile(values, 0.10), 6),
        "p25": round(_percentile(values, 0.25), 6),
        "p50": round(_percentile(values, 0.50), 6),
        "p75": round(_percentile(values, 0.75), 6),
        "p90": round(_percentile(values, 0.90), 6),
        "max": round(max(values), 6) if values else 0.0,
    }


def _build_bucket_row(
    field: str,
    direction: str,
    bucket_months: list[dict[str, float]],
) -> dict[str, object]:
    """汇总单因子分层收益，检验高分组是否持续优于低分组。"""
    bucket_averages = {
        f"bucket_{index}_avg_next_return": round(_safe_mean([row[f"bucket_{index}"] for row in bucket_months]), 6)
        for index in range(1, 6)
    }
    monotonic_months = sum(1 for row in bucket_months if int(row["is_monotonic"]) == 1)
    return {
        "factor_name": field,
        "direction": direction,
        "bucket_evaluation_months": len(bucket_months),
        **bucket_averages,
        "avg_top_bottom_next_return": round(_safe_mean([row["top_bottom_spread"] for row in bucket_months]), 6),
        "monotonic_month_ratio": round(monotonic_months / len(bucket_months), 6) if bucket_months else 0.0,
    }


def _build_correlation_rows(
    eligible_by_month: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    """按月计算因子两两 Spearman 相关，识别信息重复较高的因子对。"""
    rows: list[dict[str, object]] = []
    for left_index, left_spec in enumerate(FACTOR_SPECS):
        left_field = str(left_spec["field"])
        for right_spec in FACTOR_SPECS[left_index + 1:]:
            right_field = str(right_spec["field"])
            correlations: list[float] = []
            positive_months = 0
            negative_months = 0
            for month_rows in eligible_by_month.values():
                samples = []
                for row in month_rows:
                    left_value = _to_float(row.get(left_field))
                    right_value = _to_float(row.get(right_field))
                    if left_value is None or right_value is None:
                        continue
                    samples.append(
                        {
                            "entity_id": str(row["entity_id"]),
                            "left_value": left_value,
                            "right_value": right_value,
                        }
                    )
                if len(samples) < 2:
                    continue
                correlation = _rank_correlation(samples, "left_value", "right_value", ascending=False)
                correlations.append(correlation)
                if correlation > 0:
                    positive_months += 1
                elif correlation < 0:
                    negative_months += 1
            avg_correlation = _safe_mean(correlations)
            rows.append(
                {
                    "factor_left": left_field,
                    "factor_right": right_field,
                    "evaluation_months": len(correlations),
                    "avg_spearman_corr": round(avg_correlation, 6),
                    "positive_corr_ratio": round(positive_months / len(correlations), 6) if correlations else 0.0,
                    "negative_corr_ratio": round(negative_months / len(correlations), 6) if correlations else 0.0,
                    "high_correlation_flag": 1 if abs(avg_correlation) >= 0.8 else 0,
                }
            )
    rows.sort(key=lambda item: (-abs(float(item["avg_spearman_corr"])), str(item["factor_left"]), str(item["factor_right"])))
    return rows


def _bucket_performance(
    rows: list[dict[str, float | str]],
    *,
    bucket_count: int,
    ascending: bool,
) -> dict[str, float] | None:
    """把单月样本切成固定分层，避免只靠相关系数判断是否具备投资排序含义。"""
    if len(rows) < bucket_count:
        return None
    ordered = sorted(rows, key=lambda item: float(item["factor_value"]), reverse=not ascending)
    bucket_size = ceil(len(ordered) / bucket_count)
    bucket_returns: list[float] = []
    for index in range(bucket_count):
        bucket = ordered[index * bucket_size:(index + 1) * bucket_size]
        if not bucket:
            return None
        bucket_returns.append(_safe_mean([float(row["next_return_1m"]) for row in bucket]))
    return {
        "bucket_1": bucket_returns[0],
        "bucket_2": bucket_returns[1],
        "bucket_3": bucket_returns[2],
        "bucket_4": bucket_returns[3],
        "bucket_5": bucket_returns[4],
        "top_bottom_spread": bucket_returns[0] - bucket_returns[4],
        "is_monotonic": 1.0 if all(left >= right for left, right in zip(bucket_returns, bucket_returns[1:])) else 0.0,
    }


def _rank_correlation(
    rows: list[dict[str, float | str]],
    left_field: str,
    right_field: str,
    *,
    ascending: bool,
) -> float:
    """计算两个字段之间的 Spearman 秩相关。"""
    left_ranks = _rank_map(rows, left_field, ascending=ascending)
    right_ranks = _rank_map(rows, right_field, ascending=False)
    keys = [str(row["entity_id"]) for row in rows]
    left_values = [left_ranks[key] for key in keys]
    right_values = [right_ranks[key] for key in keys]
    return _pearson(left_values, right_values)


def _top_bottom_spread(rows: list[dict[str, float | str]], *, ascending: bool) -> float:
    """计算单因子 top-half 与 bottom-half 的下一月收益差。"""
    ordered = sorted(rows, key=lambda item: float(item["factor_value"]), reverse=not ascending)
    split_index = max(len(ordered) // 2, 1)
    top_group = ordered[:split_index]
    bottom_group = ordered[-split_index:]
    top_return = _safe_mean([float(row["next_return_1m"]) for row in top_group])
    bottom_return = _safe_mean([float(row["next_return_1m"]) for row in bottom_group])
    return top_return - bottom_return


def _rank_map(rows: list[dict[str, float | str]], field: str, *, ascending: bool) -> dict[str, float]:
    """把一组样本映射为 0 到 1 的秩分位。"""
    ordered = sorted(rows, key=lambda item: float(item[field]), reverse=not ascending)
    size = max(len(ordered) - 1, 1)
    return {
        str(row["entity_id"]): (size - index) / size if len(ordered) > 1 else 1.0
        for index, row in enumerate(ordered)
    }


def _pearson(left: list[float], right: list[float]) -> float:
    """计算两个等长序列的 Pearson 相关系数。"""
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = _safe_mean(left)
    right_mean = _safe_mean(right)
    numerator = sum((l - left_mean) * (r - right_mean) for l, r in zip(left, right))
    left_var = sum((value - left_mean) ** 2 for value in left)
    right_var = sum((value - right_mean) ** 2 for value in right)
    if left_var <= 0 or right_var <= 0:
        return 0.0
    return numerator / sqrt(left_var * right_var)


def _safe_mean(values: list[float]) -> float:
    """在空样本时安全返回 0。"""
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    """计算总体标准差，用于识别近似常数因子和极度离散因子。"""
    if len(values) < 2:
        return 0.0
    mean_value = _safe_mean(values)
    return sqrt(sum((value - mean_value) ** 2 for value in values) / len(values))


def _percentile(values: list[float], ratio: float) -> float:
    """在不引入第三方依赖的前提下计算简单分位点，满足研究报告的粗粒度分布诊断。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = ratio * (len(ordered) - 1)
    lower_index = int(index)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    weight = index - lower_index
    return ordered[lower_index] * (1 - weight) + ordered[upper_index] * weight


def _to_float(value: object) -> float | None:
    """把特征值安全转成有限浮点数，避免缺失值或异常值悄悄污染评估结果。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _information_ratio(values: list[float]) -> float:
    """计算一组月度统计值的均值/波动比。"""
    if len(values) < 2:
        return 0.0
    mean_value = _safe_mean(values)
    variance = sum((value - mean_value) ** 2 for value in values) / len(values)
    # 样例数据或极稳定因子上，浮点噪声会让“几乎零波动”表现成极大 IR，实际并无解释价值。
    if variance <= 1e-12:
        return 0.0
    return mean_value / sqrt(variance)
