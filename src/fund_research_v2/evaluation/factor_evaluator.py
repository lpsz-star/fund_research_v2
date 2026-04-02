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

FACTOR_RESEARCH_METADATA: dict[str, dict[str, object]] = {
    "ret_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "长期收益延续性具备清晰金融语义，但与超额收益因子可能高度重合。",
        "time_boundary": "history_safe",
        "style_family": "absolute_momentum",
        "style_note": "代表基金自身长期趋势，风格上更接近绝对收益动量。",
        "role_hint": "primary",
        "redundancy_group": "ret_12m_cluster",
        "preference_rank": 2,
    },
    "ret_6m": {
        "semantic_rationality": "clear",
        "semantic_note": "中期收益延续性语义清晰，但通常只是长期动量的较短窗口变体。",
        "time_boundary": "history_safe",
        "style_family": "absolute_momentum",
        "style_note": "代表中期绝对收益趋势，更适合作为辅助动量观测。",
        "role_hint": "secondary",
        "redundancy_group": "ret_6m_cluster",
        "preference_rank": 2,
    },
    "excess_ret_3m": {
        "semantic_rationality": "clear",
        "semantic_note": "短期超额收益能刻画最近相对胜出，但窗口较短、噪声更高。",
        "time_boundary": "history_safe",
        "style_family": "excess_momentum",
        "style_note": "代表短期相对基准超额，更偏交易性风格。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "excess_ret_6m": {
        "semantic_rationality": "clear",
        "semantic_note": "中期超额收益能反映基金相对基准的持续胜出能力。",
        "time_boundary": "history_safe",
        "style_family": "excess_momentum",
        "style_note": "代表中期相对基准动量，适合作为辅助排序候选。",
        "role_hint": "secondary",
        "redundancy_group": "ret_6m_cluster",
        "preference_rank": 1,
    },
    "excess_ret_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "长期超额收益是最直接的相对选基信号之一，金融语义清晰。",
        "time_boundary": "history_safe",
        "style_family": "excess_momentum",
        "style_note": "代表长期相对基准动量，通常比绝对收益更适合主排序。",
        "role_hint": "primary",
        "redundancy_group": "ret_12m_cluster",
        "preference_rank": 1,
    },
    "excess_consistency_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "连续超额月份占比反映超额收益的稳定性，语义合理。",
        "time_boundary": "history_safe",
        "style_family": "consistency_quality",
        "style_note": "代表超额收益一致性，更像质量修正因子而非主轴收益因子。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "excess_hit_rate_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "超额胜率描述基金相对基准的月度胜率，解释性强。",
        "time_boundary": "history_safe",
        "style_family": "consistency_quality",
        "style_note": "代表月度超额胜率，适合作为稳定性修正因子。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "excess_streak_6m": {
        "semantic_rationality": "reasonable",
        "semantic_note": "连续超额月数能描述趋势持续性，但更容易受短期噪声驱动。",
        "time_boundary": "history_safe",
        "style_family": "consistency_quality",
        "style_note": "代表短期超额连续性，更适合作为观察或轻度修正。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "max_drawdown_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "最大回撤是成熟的风险暴露指标，但与其他回撤/波动因子重叠较高。",
        "time_boundary": "history_safe",
        "style_family": "drawdown_risk",
        "style_note": "代表极端回撤暴露，更适合作为风险约束而非主排序主轴。",
        "role_hint": "risk_control",
        "redundancy_group": "drawdown_risk_cluster",
        "preference_rank": 3,
    },
    "drawdown_recovery_ratio_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "回撤后恢复能力具备明确的韧性语义，能补充纯回撤水平指标。",
        "time_boundary": "history_safe",
        "style_family": "drawdown_resilience",
        "style_note": "代表回撤后的修复能力，偏质量修正而非风险惩罚。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "drawdown_duration_ratio_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "回撤持续时间比率比单一跌幅更接近投资者真实持有痛感。",
        "time_boundary": "history_safe",
        "style_family": "drawdown_risk",
        "style_note": "代表回撤拖延风险，通常比单纯波动更能解释持有体验。",
        "role_hint": "risk_control",
        "redundancy_group": "drawdown_risk_cluster",
        "preference_rank": 1,
    },
    "hit_rate_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "月度正收益胜率语义直观，但和超额胜率相比更容易混入市场 beta。",
        "time_boundary": "history_safe",
        "style_family": "consistency_quality",
        "style_note": "代表绝对收益胜率，更偏辅助质量因子。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 2,
    },
    "profit_loss_ratio_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "盈亏比可反映收益分布质量，但对极端值较敏感。",
        "time_boundary": "history_safe",
        "style_family": "distribution_quality",
        "style_note": "代表收益分布质量，更适合作为辅助修正因子。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "worst_3m_avg_return_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "最差三个月平均收益能够刻画左尾压力，但与波动/回撤指标往往高度重叠。",
        "time_boundary": "history_safe",
        "style_family": "drawdown_risk",
        "style_note": "代表左尾冲击风险，适合作为风险约束候选。",
        "role_hint": "risk_control",
        "redundancy_group": "drawdown_risk_cluster",
        "preference_rank": 2,
    },
    "manager_post_change_excess_delta_12m": {
        "semantic_rationality": "reasonable",
        "semantic_note": "经理变更后的超额改善具备事件语义，但依赖经理时点映射审计。",
        "time_boundary": "needs_audit",
        "style_family": "manager_event",
        "style_note": "代表经理更替后的业绩拐点，属于事件型特殊情景因子。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "manager_post_change_downside_vol_delta_12m": {
        "semantic_rationality": "reasonable",
        "semantic_note": "经理变更后下行波动变化具备事件语义，但依赖经理时点映射审计。",
        "time_boundary": "needs_audit",
        "style_family": "manager_event",
        "style_note": "代表经理更替后的风险改善，属于事件型特殊情景因子。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "vol_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "波动率是基础风险指标，但信息通常被下行波动等更针对性的风险因子覆盖。",
        "time_boundary": "history_safe",
        "style_family": "volatility_risk",
        "style_note": "代表总体波动暴露，适合作为基础风险约束。",
        "role_hint": "risk_control",
        "redundancy_group": "volatility_risk_cluster",
        "preference_rank": 2,
    },
    "downside_vol_12m": {
        "semantic_rationality": "clear",
        "semantic_note": "下行波动率更贴近投资者真实风险感知，通常优于总波动率。",
        "time_boundary": "history_safe",
        "style_family": "volatility_risk",
        "style_note": "代表下行风险暴露，通常比总波动率更具解释性。",
        "role_hint": "risk_control",
        "redundancy_group": "volatility_risk_cluster",
        "preference_rank": 1,
    },
    "tail_loss_ratio_12m": {
        "semantic_rationality": "reasonable",
        "semantic_note": "尾部亏损占比可描述左尾分布，但口径更抽象、解释成本更高。",
        "time_boundary": "history_safe",
        "style_family": "distribution_quality",
        "style_note": "代表尾部亏损暴露，属于收益分布质量的左尾视角。",
        "role_hint": "risk_control",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "manager_change_count_24m": {
        "semantic_rationality": "reasonable",
        "semantic_note": "经理频繁变更可能代表治理不稳定，但需要经理时点审计支撑。",
        "time_boundary": "needs_audit",
        "style_family": "manager_stability",
        "style_note": "代表团队稳定性，更接近治理质量因子。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "manager_tenure_months": {
        "semantic_rationality": "reasonable",
        "semantic_note": "经理任期能表达经验和策略稳定性，但依赖经理时点映射审计。",
        "time_boundary": "needs_audit",
        "style_family": "manager_stability",
        "style_note": "代表经理稳定性和经验累积，更适合作为辅助修正。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "asset_stability_12m": {
        "semantic_rationality": "reasonable",
        "semantic_note": "规模稳定性可以反映申赎扰动，但和规模波动率高度相关且经济含义不完全单向。",
        "time_boundary": "history_safe",
        "style_family": "asset_flow",
        "style_note": "代表规模稳定性，更偏申赎结构质量而非收益主轴。",
        "role_hint": "secondary",
        "redundancy_group": "asset_flow_cluster",
        "preference_rank": 2,
    },
    "asset_growth_6m": {
        "semantic_rationality": "reasonable",
        "semantic_note": "规模增长能反映资金偏好，但容易混入渠道效应和业绩追涨反馈。",
        "time_boundary": "history_safe",
        "style_family": "asset_flow",
        "style_note": "代表资金流入趋势，更适合作为观察因子。",
        "role_hint": "secondary",
        "redundancy_group": "",
        "preference_rank": 1,
    },
    "asset_flow_volatility_12m": {
        "semantic_rationality": "reasonable",
        "semantic_note": "规模波动率能描述资金流稳定性，但与其他规模扰动指标可能重叠。",
        "time_boundary": "history_safe",
        "style_family": "asset_flow",
        "style_note": "代表资金流稳定性风险，适合作为辅助稳定性约束。",
        "role_hint": "secondary",
        "redundancy_group": "asset_flow_cluster",
        "preference_rank": 1,
    },
}


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
    scorecard_rows = _build_scorecard_rows(factor_rows, distribution_rows, bucket_rows, correlation_rows)
    high_correlation_rows = [row for row in correlation_rows if int(row["high_correlation_flag"]) == 1]
    return {
        "factor_rows": factor_rows,
        "distribution_rows": distribution_rows,
        "bucket_rows": bucket_rows,
        "correlation_rows": correlation_rows,
        "scorecard_rows": scorecard_rows,
        "summary": {
            "factor_count": len(factor_rows),
            "strong_factor_count": sum(1 for row in factor_rows if float(row["avg_rankic"]) > 0 and float(row["avg_top_bottom_next_return"]) > 0),
            "weak_factor_count": sum(1 for row in factor_rows if float(row["avg_rankic"]) <= 0),
            "high_correlation_pair_count": len(high_correlation_rows),
            "primary_candidate_count": sum(1 for row in scorecard_rows if str(row["research_role"]) == "primary_candidate"),
            "secondary_candidate_count": sum(1 for row in scorecard_rows if str(row["research_role"]) == "secondary_candidate"),
            "risk_control_candidate_count": sum(1 for row in scorecard_rows if str(row["research_role"]) == "risk_control_candidate"),
            "observe_only_count": sum(1 for row in scorecard_rows if str(row["research_role"]) == "observe_only"),
            "drop_count": sum(1 for row in scorecard_rows if str(row["research_role"]) == "drop"),
        },
    }


def _build_scorecard_rows(
    factor_rows: list[dict[str, object]],
    distribution_rows: list[dict[str, object]],
    bucket_rows: list[dict[str, object]],
    correlation_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """把单因子统计诊断升级为可直接支撑准入判断的研究评分卡。"""
    distribution_map = {str(row["factor_name"]): row for row in distribution_rows}
    bucket_map = {str(row["factor_name"]): row for row in bucket_rows}
    overlap_map = _high_correlation_overlap_map(correlation_rows)
    factor_metric_map = {str(row["factor_name"]): row for row in factor_rows}
    scorecard_rows: list[dict[str, object]] = []
    for factor_row in factor_rows:
        factor_name = str(factor_row["factor_name"])
        metadata = FACTOR_RESEARCH_METADATA.get(factor_name, {})
        distribution_row = distribution_map.get(factor_name, {})
        bucket_row = bucket_map.get(factor_name, {})
        overlap_rows = overlap_map.get(factor_name, [])
        semantic_rationality, semantic_note = _semantic_assessment(metadata)
        time_boundary_cleanliness, time_boundary_note = _time_boundary_assessment(metadata)
        ranking_ability, ranking_note = _ranking_ability_assessment(factor_row)
        time_varying_stability, stability_note = _time_varying_stability_assessment(factor_row, bucket_row)
        coverage_quality, coverage_note = _coverage_quality_assessment(distribution_row)
        style_explanation, style_note = _style_explanation_assessment(metadata, overlap_rows)
        redundancy_flag = _is_redundant_factor(factor_name, factor_metric_map, overlap_rows)
        research_role, admission_conclusion = _research_conclusion(
            metadata=metadata,
            factor_row=factor_row,
            ranking_ability=ranking_ability,
            time_varying_stability=time_varying_stability,
            coverage_quality=coverage_quality,
            time_boundary_cleanliness=time_boundary_cleanliness,
            redundancy_flag=redundancy_flag,
        )
        scorecard_rows.append(
            {
                "factor_name": factor_name,
                "direction": factor_row["direction"],
                "style_family": metadata.get("style_family", "unknown"),
                "semantic_rationality": semantic_rationality,
                "semantic_note": semantic_note,
                "time_boundary_cleanliness": time_boundary_cleanliness,
                "time_boundary_note": time_boundary_note,
                "ranking_ability": ranking_ability,
                "ranking_note": ranking_note,
                "time_varying_stability": time_varying_stability,
                "stability_note": stability_note,
                "coverage_quality": coverage_quality,
                "coverage_note": coverage_note,
                "style_explanation": style_explanation,
                "style_note": style_note,
                "high_correlation_pair_count": len(overlap_rows),
                "high_correlation_partners": "|".join(sorted(str(row["partner"]) for row in overlap_rows)),
                "redundancy_flag": 1 if redundancy_flag else 0,
                "research_role": research_role,
                "admission_conclusion": admission_conclusion,
            }
        )
    scorecard_rows.sort(
        key=lambda item: (
            _research_role_rank(str(item["research_role"])),
            _qualitative_rank(str(item["ranking_ability"])),
            _qualitative_rank(str(item["time_varying_stability"])),
            str(item["factor_name"]),
        )
    )
    return scorecard_rows


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


def _high_correlation_overlap_map(correlation_rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """把高相关因子对转换成单因子视角，便于做结构重叠判断。"""
    result: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in correlation_rows:
        if int(row.get("high_correlation_flag", 0)) != 1:
            continue
        left = str(row["factor_left"])
        right = str(row["factor_right"])
        payload = {
            "partner": right,
            "avg_spearman_corr": float(row["avg_spearman_corr"]),
        }
        result[left].append(payload)
        payload = {
            "partner": left,
            "avg_spearman_corr": float(row["avg_spearman_corr"]),
        }
        result[right].append(payload)
    return result


def _semantic_assessment(metadata: dict[str, object]) -> tuple[str, str]:
    label = str(metadata.get("semantic_rationality", "reasonable"))
    note = str(metadata.get("semantic_note", "金融语义需要继续补充研究说明。"))
    return label, note


def _time_boundary_assessment(metadata: dict[str, object]) -> tuple[str, str]:
    raw = str(metadata.get("time_boundary", "needs_audit"))
    if raw == "history_safe":
        return "clean", "底层字段已接入点时可得主链路，可进入正式历史研究。"
    if raw == "snapshot_only":
        return "snapshot_only", "底层字段只适合解释当前快照，不应直接进入历史月份准入。"
    return "needs_audit", "底层字段金融语义合理，但尚未完成 decision_date 可得性审计。"


def _ranking_ability_assessment(factor_row: dict[str, object]) -> tuple[str, str]:
    avg_rankic = float(factor_row["avg_rankic"])
    avg_spread = float(factor_row["avg_top_bottom_next_return"])
    evaluation_months = int(factor_row["evaluation_months"])
    if evaluation_months < 12:
        return "insufficient", "有效评价月份不足 12，当前只能做观察。"
    if avg_rankic <= 0:
        return "weak", "平均 RankIC 非正，当前不支持正式准入。"
    if avg_rankic >= 0.03 and avg_spread > 0:
        return "strong", "平均 RankIC 和分层收益同时为正，具备较好的单因子排序能力。"
    if avg_rankic >= 0.015:
        return "moderate", "平均 RankIC 为正，但分层收益或强度仍需结合稳定性继续审查。"
    return "weak", "排序能力偏弱，当前更适合停留在观察层。"


def _time_varying_stability_assessment(
    factor_row: dict[str, object],
    bucket_row: dict[str, object],
) -> tuple[str, str]:
    evaluation_months = int(factor_row["evaluation_months"])
    rankic_ir = float(factor_row["rankic_ir"])
    positive_ratio = float(factor_row["positive_rankic_ratio"])
    monotonic_ratio = float(bucket_row.get("monotonic_month_ratio", 0.0) or 0.0)
    if evaluation_months < 12:
        return "insufficient", "有效评价月份不足，暂时无法判断时变稳定性。"
    if rankic_ir >= 0.15 and positive_ratio >= 0.55:
        return "strong", "RankIC 波动比和正向月份占比均较稳，时变稳定性较好。"
    if rankic_ir >= 0.05 and positive_ratio >= 0.5:
        if monotonic_ratio >= 0.1:
            return "moderate", "方向稳定性基本成立，但分层单调性仍不强。"
        return "moderate", "正向月份略占优，但结构稳定性仍需继续观察。"
    return "weak", "RankIC 稳定性不足，容易只在局部窗口有效。"


def _coverage_quality_assessment(distribution_row: dict[str, object]) -> tuple[str, str]:
    missing_ratio = float(distribution_row.get("missing_ratio", 1.0) or 0.0)
    sample_count = int(distribution_row.get("sample_count", 0) or 0)
    if sample_count == 0:
        return "weak", "当前没有可用样本，无法进入正式研究。"
    if missing_ratio <= 0.1 and sample_count >= 1000:
        return "strong", "缺失率较低，覆盖质量足以支持横截面研究。"
    if missing_ratio <= 0.35 and sample_count >= 300:
        return "moderate", "覆盖质量可用于研究，但需要关注缺失样本是否集中在特定类型。"
    return "weak", "缺失率较高或样本偏少，容易让研究结论失真。"


def _style_explanation_assessment(
    metadata: dict[str, object],
    overlap_rows: list[dict[str, object]],
) -> tuple[str, str]:
    style_note = str(metadata.get("style_note", "当前尚未补充风格解释。"))
    if any(abs(float(row["avg_spearman_corr"])) >= 0.95 for row in overlap_rows):
        return "clear_but_redundant", f"{style_note} 但与现有因子高度重复，结构上不宜重复加权。"
    if overlap_rows:
        return "clear_with_overlap", f"{style_note} 但与相近因子已有较强结构重叠。"
    if str(metadata.get("style_family", "")).startswith("manager_"):
        return "special_situation", f"{style_note} 更适合事件型或观察层研究。"
    return "clear", style_note


def _is_redundant_factor(
    factor_name: str,
    factor_metric_map: dict[str, dict[str, object]],
    overlap_rows: list[dict[str, object]],
) -> bool:
    metadata = FACTOR_RESEARCH_METADATA.get(factor_name, {})
    group = str(metadata.get("redundancy_group", ""))
    if not group:
        return False
    my_preference = int(metadata.get("preference_rank", 999))
    my_rankic = float(factor_metric_map[factor_name]["avg_rankic"])
    for row in overlap_rows:
        partner = str(row["partner"])
        partner_metadata = FACTOR_RESEARCH_METADATA.get(partner, {})
        if str(partner_metadata.get("redundancy_group", "")) != group:
            continue
        partner_preference = int(partner_metadata.get("preference_rank", 999))
        partner_rankic = float(factor_metric_map.get(partner, {}).get("avg_rankic", 0.0))
        if partner_preference < my_preference and partner_rankic >= my_rankic - 1e-6:
            return True
    return False


def _research_conclusion(
    *,
    metadata: dict[str, object],
    factor_row: dict[str, object],
    ranking_ability: str,
    time_varying_stability: str,
    coverage_quality: str,
    time_boundary_cleanliness: str,
    redundancy_flag: bool,
) -> tuple[str, str]:
    if time_boundary_cleanliness in {"needs_audit", "snapshot_only"}:
        return "observe_only", "observe_only_time_boundary_not_clean"
    if float(factor_row["avg_rankic"]) <= 0:
        return "drop", "drop_direction_or_rankic_conflict"
    if ranking_ability in {"insufficient", "weak"}:
        return "drop", "drop_ranking_ability_insufficient"
    if redundancy_flag:
        return "observe_only", "observe_only_redundant_with_stronger_peer"
    if coverage_quality == "weak":
        return "observe_only", "observe_only_low_coverage"
    if time_varying_stability == "weak":
        return "observe_only", "observe_only_time_variation_unstable"
    role_hint = str(metadata.get("role_hint", "secondary"))
    if role_hint == "risk_control":
        return "risk_control_candidate", "admit_risk_control_candidate"
    if role_hint == "primary" and ranking_ability == "strong":
        return "primary_candidate", "admit_primary_candidate"
    return "secondary_candidate", "admit_secondary_candidate"


def _research_role_rank(role: str) -> int:
    order = {
        "primary_candidate": 0,
        "risk_control_candidate": 1,
        "secondary_candidate": 2,
        "observe_only": 3,
        "drop": 4,
    }
    return order.get(role, 9)


def _qualitative_rank(label: str) -> int:
    order = {
        "strong": 0,
        "moderate": 1,
        "clear": 1,
        "reasonable": 2,
        "clean": 0,
        "clear_with_overlap": 2,
        "clear_but_redundant": 3,
        "special_situation": 3,
        "needs_audit": 4,
        "snapshot_only": 5,
        "weak": 6,
        "insufficient": 7,
    }
    return order.get(label, 8)


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
