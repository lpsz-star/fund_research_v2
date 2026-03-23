from __future__ import annotations

from collections import defaultdict

from fund_research_v2.common.config import AppConfig


_FACTOR_DIRECTIONS = {
    "ret_3m": "high",
    "ret_6m": "high",
    "ret_12m": "high",
    "excess_ret_3m": "high",
    "excess_ret_6m": "high",
    "excess_ret_12m": "high",
    "excess_consistency_12m": "high",
    "excess_hit_rate_12m": "high",
    "excess_streak_6m": "high",
    "vol_12m": "low",
    "downside_vol_12m": "low",
    "max_drawdown_12m": "high",
    "drawdown_recovery_ratio_12m": "high",
    "drawdown_duration_ratio_12m": "low",
    "months_since_drawdown_low_12m": "high",
    "hit_rate_12m": "high",
    "profit_loss_ratio_12m": "high",
    "worst_3m_avg_return_12m": "high",
    "manager_post_change_excess_delta_12m": "high",
    "manager_post_change_downside_vol_delta_12m": "low",
    "manager_change_count_24m": "low",
    "manager_tenure_months": "high",
    "asset_stability_12m": "low",
    "asset_growth_6m": "high",
    "asset_flow_volatility_12m": "low",
    "tail_loss_ratio_12m": "low",
}


def score_funds(config: AppConfig, feature_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """把月频特征转换为横截面因子分、总分和排名。"""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in feature_rows:
        # 评分阶段只对当月可投资基金做横截面比较，不把不可投样本混入分位次。
        if int(row["is_eligible"]) == 1:
            grouped[str(row["month"])].append(row)
    scored_rows = []
    for month, rows in grouped.items():
        # 评分始终是“同月横截面比较”，这样不同市场环境下的绝对收益水平不会直接混在一起。
        category_score_maps = {
            category: _category_score_map(rows, factor_weights)
            for category, factor_weights in config.ranking.category_factors.items()
        }
        month_rows = []
        for row in rows:
            entity_id = str(row["entity_id"])
            performance_quality = category_score_maps["performance_quality"][entity_id]
            risk_control = category_score_maps["risk_control"][entity_id]
            stability_quality = category_score_maps["stability_quality"][entity_id]
            total_score = round(
                performance_quality * config.ranking.factor_weights["performance_quality"]
                + risk_control * config.ranking.factor_weights["risk_control"]
                + stability_quality * config.ranking.factor_weights["stability_quality"],
                6,
            )
            # 三类因子先分开计算再汇总，是为了让后续分析时能明确知道基金是靠收益、风险还是稳定性胜出。
            scored = dict(row)
            scored.update(
                {
                    "performance_quality": performance_quality,
                    "risk_control": risk_control,
                    "stability_quality": stability_quality,
                    "total_score": total_score,
                }
            )
            month_rows.append(scored)
        month_rows.sort(key=lambda item: float(item["total_score"]), reverse=True)
        for index, row in enumerate(month_rows, start=1):
            row["rank"] = index
        scored_rows.extend(month_rows)
    return sorted(scored_rows, key=lambda item: (str(item["month"]), int(item["rank"])))


def _category_score_map(rows: list[dict[str, object]], factor_weights: dict[str, float]) -> dict[str, float]:
    """按配置中的因子集合与权重合成某一评分大类的横截面分数。"""
    normalized_maps = {
        field: _normalized_single_field_map(rows, field, _FACTOR_DIRECTIONS.get(field, "high"))
        for field in factor_weights
    }
    weight_sum = sum(factor_weights.values())
    result: dict[str, float] = {}
    for row in rows:
        entity_id = str(row["entity_id"])
        result[entity_id] = round(
            sum(normalized_maps[field][entity_id] * weight for field, weight in factor_weights.items()) / weight_sum,
            6,
        )
    return result


def _normalized_score_map(
    rows: list[dict[str, object]],
    *fields: str,
    invert: bool = False,
    invert_last: bool = False,
) -> dict[str, dict[str, float]]:
    """把若干字段按同月横截面排序映射成 0 到 1 的分位得分。"""
    result: dict[str, dict[str, float]] = {}
    for field in fields:
        values = {str(row["entity_id"]): float(row[field]) for row in rows}
        # 这里用排序位置映射到 [0, 1]，目的是先提供稳定可解释的基础评分口径。
        ordered = sorted(values.items(), key=lambda item: item[1], reverse=not invert)
        if invert_last and field == fields[-1]:
            # asset_stability_12m 数值越大越不稳定，因此稳定性因子里的最后一个字段需要反向排序。
            ordered = sorted(values.items(), key=lambda item: item[1], reverse=False)
        size = max(len(ordered) - 1, 1)
        result[field] = {
            entity_id: round((size - index) / size, 6) if len(ordered) > 1 else 1.0
            for index, (entity_id, _) in enumerate(ordered)
        }
    return result


def _normalized_single_field_map(rows: list[dict[str, object]], field: str, direction: str) -> dict[str, float]:
    """把单个字段按方向映射到 0 到 1 的横截面分位得分。"""
    values: dict[str, float] = {}
    missing_entity_ids: list[str] = []
    for row in rows:
        entity_id = str(row["entity_id"])
        raw_value = row.get(field)
        if raw_value is None or raw_value == "":
            missing_entity_ids.append(entity_id)
            continue
        values[entity_id] = float(raw_value)
    if not values:
        return {str(row["entity_id"]): 0.5 for row in rows}
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=(direction == "high"))
    size = max(len(ordered) - 1, 1)
    result = {
        entity_id: round((size - index) / size, 6) if len(ordered) > 1 else 1.0
        for index, (entity_id, _) in enumerate(ordered)
    }
    # 事件类因子在部分基金上天然缺观测值；这里给中性分，避免“没发生事件”被机械地奖惩。
    for entity_id in missing_entity_ids:
        result[entity_id] = 0.5
    return result
