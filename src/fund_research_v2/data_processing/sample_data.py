from __future__ import annotations

from fund_research_v2.common.config import BenchmarkConfig, benchmark_to_serializable_dict
from fund_research_v2.common.contracts import DatasetSnapshot
from fund_research_v2.common.date_utils import current_timestamp
from fund_research_v2.data_processing.fund_liquidity_classifier import classify_fund_liquidity
from fund_research_v2.data_processing.fund_type_classifier import classify_fund_type


def generate_sample_dataset(lookback_months: int, benchmark_config: BenchmarkConfig) -> DatasetSnapshot:
    """生成一套可复现的样例基金数据，用于开发和测试。"""
    months = _generate_months("2022-03", lookback_months)
    # 样例数据不是随机噪声，而是刻意构造出“强者、更稳者、新基金、小规模基金”等可验证场景。
    entities = [
        ("E001", "景行成长", "主动股票", "远见基金", "经理甲", "2020-01", "2021-03", 900.0, 0.017),
        ("E002", "稳健价值", "主动股票", "远见基金", "经理乙", "2019-08", "2020-06", 750.0, 0.013),
        ("E003", "均衡精选", "灵活配置混合", "启明基金", "经理丙", "2018-05", "2018-05", 620.0, 0.011),
        ("E004", "制造先锋", "主动股票", "启明基金", "经理丁", "2021-06", "2024-01", 480.0, 0.016),
        ("E005", "红利低波", "偏股混合", "星河基金", "经理戊", "2017-11", "2026-12", 680.0, 0.010),
        ("E006", "行业轮动一年持有", "主动股票", "海岳基金", "经理己", "2021-11", "", 260.0, 0.008),
        ("E007", "新锐成长", "主动股票", "海岳基金", "经理庚", "2025-08", "2025-08", 0.0, 0.020),
    ]
    fund_entity_master = []
    share_class_map = []
    nav_rows = []
    benchmark_rows = []
    manager_rows = []
    fund_type_audit_rows = []
    fund_liquidity_audit_rows = []
    for entity_id, entity_name, primary_type, company, manager, inception_month, manager_start_month, assets, drift in entities:
        classification = classify_fund_type(
            fund_type=primary_type,
            invest_type=primary_type,
            fund_name=entity_name,
            benchmark_text="",
        )
        liquidity = classify_fund_liquidity(entity_name)
        fund_entity_master.append(
            {
                "entity_id": entity_id,
                "entity_name": entity_name,
                "primary_type": classification["primary_type"],
                "fund_company": company,
                "manager_name": manager,
                "manager_start_month": manager_start_month,
                "inception_month": inception_month,
                "latest_assets_cny_mn": assets,
                "liquidity_restricted": int(liquidity["liquidity_restricted"]),
                "holding_lock_months": int(liquidity["holding_lock_months"]),
                "status": "L",
            }
        )
        fund_type_audit_rows.append(
            {
                "entity_id": entity_id,
                "entity_name": entity_name,
                "share_class_id": f"{entity_id}A",
                "fund_name": entity_name,
                "raw_fund_type": classification["raw_fund_type"],
                "raw_invest_type": classification["raw_invest_type"],
                "benchmark_text": "",
                "primary_type": classification["primary_type"],
                "rule_code": classification["rule_code"],
                "confidence": classification["confidence"],
                "reason": classification["reason"],
            }
        )
        fund_liquidity_audit_rows.append(
            {
                "entity_id": entity_id,
                "entity_name": entity_name,
                "share_class_id": f"{entity_id}A",
                "fund_name": entity_name,
                "liquidity_restricted": int(liquidity["liquidity_restricted"]),
                "holding_lock_months": int(liquidity["holding_lock_months"]),
                "rule_code": str(liquidity["rule_code"]),
                "confidence": str(liquidity["confidence"]),
                "reason": str(liquidity["reason"]),
            }
        )
        share_class_map.extend(
            [
                # sample 模式也保留 A/C 映射，是为了让测试环境和真实环境共享同一份份额归并语义。
                {
                    "entity_id": entity_id,
                    "share_class_id": f"{entity_id}A",
                    "share_class_name": f"{entity_name}A",
                    "is_primary_share_class": 1,
                },
                {
                    "entity_id": entity_id,
                    "share_class_id": f"{entity_id}C",
                    "share_class_name": f"{entity_name}C",
                    "is_primary_share_class": 0,
                },
            ]
        )
        nav = 1.0
        for index, month in enumerate(months):
            # 这里人为叠加季节性、动量、回撤和新基金扰动，用于测试基金池和评分是否按预期区分样本。
            seasonal = ((index % 6) - 2) * 0.002
            momentum = 0.002 if entity_id in {"E001", "E004"} and index > len(months) // 2 else 0.0
            drawdown = -0.012 if entity_id == "E006" and index % 9 == 0 else 0.0
            new_fund_bump = 0.005 if entity_id == "E007" else 0.0
            monthly_return = round(drift + seasonal + momentum + drawdown + new_fund_bump, 6)
            nav = round(nav * (1 + monthly_return), 6)
            nav_rows.append(
                {
                    "entity_id": entity_id,
                    "month": month,
                    "nav_date": f"{month}-28",
                    "available_date": f"{month}-28",
                    "nav": nav,
                    "return_1m": monthly_return,
                    "assets_cny_mn": round(assets + index * 4.0, 3),
                }
            )
            active_manager_start = manager_start_month if manager_start_month and manager_start_month <= month else inception_month
            manager_rows.append(
                {
                    "entity_id": entity_id,
                    "month": month,
                    "manager_name": manager,
                    "manager_start_month": active_manager_start,
                    "manager_end_month": "",
                }
            )

    benchmark_offsets = {
        benchmark_config.default_key: 0.0,
        "large_cap_equity": -0.001,
        "broad_equity": 0.0,
    }
    for index, month in enumerate(months):
        # sample benchmark 不是要拟合真实市场，而是要稳定模拟“不同基金类型对应不同基准收益”的代码路径。
        base_return = round(0.009 + ((index % 5) - 2) * 0.0015, 6)
        for benchmark_key, series in benchmark_config.series.items():
            benchmark_rows.append(
                {
                    "month": month,
                    "benchmark_key": benchmark_key,
                    "benchmark_name": series.name,
                    "benchmark_ts_code": series.ts_code or "",
                    "benchmark_return_1m": round(base_return + benchmark_offsets.get(benchmark_key, 0.0), 6),
                    "available_date": f"{month}-28",
                }
            )

    return DatasetSnapshot(
        fund_entity_master=fund_entity_master,
        fund_share_class_map=share_class_map,
        fund_nav_monthly=nav_rows,
        benchmark_monthly=benchmark_rows,
        manager_assignment_monthly=manager_rows,
        fund_type_audit=fund_type_audit_rows,
        fund_liquidity_audit=fund_liquidity_audit_rows,
        metadata={
            "source_name": "sample",
            "generated_at": current_timestamp(),
            "entity_count": len(fund_entity_master),
            "share_class_count": len(share_class_map),
            "ingestion_audit": {
                "selected_share_class_count": len(share_class_map),
                "grouped_entity_count": len(fund_entity_master),
                "retained_entity_count": len(fund_entity_master),
                "retained_share_class_count": len(share_class_map),
                "dropped_entity_count": 0,
                "dropped_entities": [],
            },
            "month_range": {"start": months[0], "end": months[-1]},
            "field_status": {
                "latest_assets_cny_mn": "realistic_sample",
                "manager_name": "sample",
                "return_1m": "sample",
                "benchmark_return_1m": "sample_multi_benchmark",
            },
            "benchmark_config": benchmark_to_serializable_dict(benchmark_config),
            "benchmark_default_key": benchmark_config.default_key,
            "benchmark_series": {
                key: {"name": series.name, "ts_code": series.ts_code}
                for key, series in benchmark_config.series.items()
            },
            "benchmark_primary_type_map": benchmark_config.primary_type_map,
            "fund_type_audit_summary": {
                "entity_count": len(fund_type_audit_rows),
                "by_primary_type": {
                    primary_type_name: sum(1 for row in fund_type_audit_rows if row["primary_type"] == primary_type_name)
                    for primary_type_name in sorted({str(row["primary_type"]) for row in fund_type_audit_rows})
                },
            },
            "fund_liquidity_audit_summary": {
                "entity_count": len(fund_liquidity_audit_rows),
                "restricted_entity_count": sum(int(row["liquidity_restricted"]) for row in fund_liquidity_audit_rows),
                "restricted_by_rule": {
                    rule_code: sum(1 for row in fund_liquidity_audit_rows if int(row["liquidity_restricted"]) == 1 and row["rule_code"] == rule_code)
                    for rule_code in sorted({str(row["rule_code"]) for row in fund_liquidity_audit_rows if int(row["liquidity_restricted"]) == 1})
                },
            },
        },
    )


def _generate_months(start_month: str, periods: int) -> list[str]:
    """从起始月份生成连续月序列。"""
    year = int(start_month[:4])
    month = int(start_month[5:7])
    months = []
    for _ in range(periods):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return months
