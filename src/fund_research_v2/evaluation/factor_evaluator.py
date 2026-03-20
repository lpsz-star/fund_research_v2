from __future__ import annotations

from collections import defaultdict
from math import sqrt

from fund_research_v2.common.date_utils import add_months

# 这里显式列出当前参与研究的原子因子与方向，避免评估口径悄悄漂移。
FACTOR_SPECS: list[dict[str, object]] = [
    {"field": "ret_12m", "direction": "high"},
    {"field": "ret_6m", "direction": "high"},
    {"field": "excess_ret_12m", "direction": "high"},
    {"field": "max_drawdown_12m", "direction": "high"},
    {"field": "vol_12m", "direction": "low"},
    {"field": "downside_vol_12m", "direction": "low"},
    {"field": "manager_tenure_months", "direction": "high"},
    {"field": "asset_stability_12m", "direction": "low"},
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
    for spec in FACTOR_SPECS:
        field = str(spec["field"])
        direction = str(spec["direction"])
        month_rankics: list[float] = []
        month_spreads: list[float] = []
        positive_months = 0
        negative_months = 0
        evaluation_months = 0
        for month, rows in sorted(eligible_by_month.items()):
            samples = []
            next_month = add_months(month, 1)
            for row in rows:
                entity_id = str(row["entity_id"])
                next_return = next_return_lookup.get((entity_id, next_month))
                if next_return is None:
                    continue
                samples.append(
                    {
                        "entity_id": entity_id,
                        "factor_value": float(row[field]),
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

    factor_rows.sort(key=lambda item: (-float(item["avg_rankic"]), -float(item["avg_top_bottom_next_return"]), str(item["factor_name"])))
    return {
        "factor_rows": factor_rows,
        "summary": {
            "factor_count": len(factor_rows),
            "strong_factor_count": sum(1 for row in factor_rows if float(row["avg_rankic"]) > 0 and float(row["avg_top_bottom_next_return"]) > 0),
            "weak_factor_count": sum(1 for row in factor_rows if float(row["avg_rankic"]) <= 0),
        },
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
