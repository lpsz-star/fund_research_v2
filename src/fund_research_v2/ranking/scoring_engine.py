from __future__ import annotations

from collections import defaultdict

from fund_research_v2.common.config import AppConfig


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
        perf_map = _normalized_score_map(rows, "ret_12m", "ret_6m", "excess_ret_12m")
        risk_map = _normalized_score_map(rows, "max_drawdown_12m", "vol_12m", "downside_vol_12m", invert=True)
        stability_map = _normalized_score_map(rows, "manager_tenure_months", "asset_stability_12m", invert_last=True)
        month_rows = []
        for row in rows:
            entity_id = str(row["entity_id"])
            performance_quality = round(
                perf_map["ret_12m"][entity_id] * 0.5 + perf_map["ret_6m"][entity_id] * 0.3 + perf_map["excess_ret_12m"][entity_id] * 0.2,
                6,
            )
            risk_control = round(
                risk_map["max_drawdown_12m"][entity_id] * 0.4 + risk_map["vol_12m"][entity_id] * 0.3 + risk_map["downside_vol_12m"][entity_id] * 0.3,
                6,
            )
            stability_quality = round(
                stability_map["manager_tenure_months"][entity_id] * 0.7 + stability_map["asset_stability_12m"][entity_id] * 0.3,
                6,
            )
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
