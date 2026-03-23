from __future__ import annotations

from collections import Counter
from pathlib import Path

from fund_research_v2.common.config import AppConfig
from fund_research_v2.common.date_utils import latest_completed_month


def _latest_month_rows(score_rows: list[dict[str, object]], latest_month: str, limit: int) -> list[dict[str, object]]:
    """提取最新月前 N 名评分结果，确保不同报告使用同一排序口径。"""
    return [row for row in score_rows if str(row["month"]) == latest_month][:limit]


def _latest_research_month(config: AppConfig, rows: list[dict[str, object]]) -> str:
    """返回报告应展示的最新正式研究月份。"""
    available_months = sorted({str(row.get("month", "")) for row in rows if str(row.get("month", ""))})
    if not available_months:
        return latest_completed_month(config.as_of_date)
    completed_cutoff = latest_completed_month(config.as_of_date)
    eligible_months = [month for month in available_months if month <= completed_cutoff]
    return eligible_months[-1] if eligible_months else available_months[-1]


def _time_boundary_notes() -> list[str]:
    """返回当前研究报告应重复强调的时间边界说明。"""
    return [
        "- 基金池规模门槛解释应优先看 `visible_assets_cny_mn`，而不是实体主表中的 `latest_assets_cny_mn`。",
        "- 特征与评分只使用信号月月末前可见的净值和 benchmark 月收益。",
        "- `manager_tenure_months` 优先基于 `manager_assignment_monthly` 计算；实体主表中的经理字段只代表最新快照。",
        "- `fund_entity_master` 更适合解释最新实体画像，不适合直接回头解释历史月份状态。",
    ]


def _benchmark_summary_lines(config: AppConfig, dataset_metadata: dict[str, object]) -> list[str]:
    """返回 benchmark 配置摘要，便于报告解释当前比较基准口径。"""
    benchmark_series = dataset_metadata.get("benchmark_series")
    if not isinstance(benchmark_series, dict) or not benchmark_series:
        benchmark_series = {
            key: {
                "name": series.name,
                "ts_code": series.ts_code or "",
            }
            for key, series in config.benchmark.series.items()
        }
    primary_type_map = dataset_metadata.get("benchmark_primary_type_map")
    if not isinstance(primary_type_map, dict):
        primary_type_map = config.benchmark.primary_type_map
    default_key = str(dataset_metadata.get("benchmark_default_key") or config.benchmark.default_key)
    lines = [f"- benchmark_default_key: {default_key}", "- benchmark_series:"]
    for benchmark_key in sorted(benchmark_series):
        payload = benchmark_series[benchmark_key]
        if isinstance(payload, dict):
            name = payload.get("name", benchmark_key)
            ts_code = payload.get("ts_code", "") or "n/a"
        else:
            name = benchmark_key
            ts_code = "n/a"
        lines.append(f"-   {benchmark_key}: name={name}, ts_code={ts_code}")
    lines.append("- benchmark_primary_type_map:")
    for primary_type in sorted(primary_type_map):
        lines.append(f"-   {primary_type}: {primary_type_map[primary_type]}")
    return lines


def render_backtest_report(path: Path, backtest_rows: list[dict[str, object]], summary: dict[str, object]) -> None:
    """把回测结果写成简洁的 Markdown 报告。"""
    # 报告优先写成 Markdown，是为了让实验输出天然可版本化、可 diff，而不是锁死在 notebook 或富文本里。
    low_confidence_rows = [row for row in backtest_rows if int(row.get("low_confidence_flag", 0)) == 1]
    highest_missing_rows = sorted(
        [row for row in backtest_rows if float(row.get("missing_weight", 0.0)) > 0],
        key=lambda item: (-float(item.get("missing_weight", 0.0)), str(item.get("execution_month", ""))),
    )
    lines = ["# Backtest Report", "", "## Summary", ""]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Data Quality Diagnostics", ""])
    lines.append(f"- missing_month_count: {summary.get('missing_month_count', 0)}")
    lines.append(f"- low_confidence_month_count: {summary.get('low_confidence_month_count', 0)}")
    lines.append(f"- avg_missing_weight: {summary.get('avg_missing_weight', 0.0)}")
    lines.append(f"- max_missing_weight: {summary.get('max_missing_weight', 0.0)}")
    lines.extend(["", "## Low Confidence Months", ""])
    if low_confidence_rows:
        for row in low_confidence_rows[:12]:
            lines.append(
                f"- {row['execution_month']}: signal_month={row.get('signal_month', '')} "
                f"missing_weight={row.get('missing_weight', 0.0)} "
                f"missing_positions={row.get('missing_position_count', 0)} "
                f"validity={row.get('return_validity', '')} "
                f"net={row.get('portfolio_return_net', '')}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Highest Missing Weight Months", ""])
    if highest_missing_rows:
        for row in highest_missing_rows[:12]:
            lines.append(
                f"- {row['execution_month']}: signal_month={row.get('signal_month', '')} "
                f"missing_weight={row.get('missing_weight', 0.0)} "
                f"missing_positions={row.get('missing_position_count', 0)} "
                f"low_confidence={row.get('low_confidence_flag', 0)}"
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Execution Convention",
            "",
            "- 当前采用场外基金申购确认的月频代理口径。",
            "- `signal_month` 月末形成选基信号，`execution_month` 月初视为申购提交代理日。",
            "- `execution_effective_date_proxy` 当前与 `execution_request_date_proxy` 相同，表示从该月开始承担收益；这只是研究代理口径，不代表真实确认日。",
        ]
    )
    lines.extend(["", "## Monthly Results", ""])
    for row in backtest_rows[:24]:
        lines.append(
            f"- {row['execution_month']}: request_proxy={row.get('execution_request_date_proxy', '')}, "
            f"effective_proxy={row.get('execution_effective_date_proxy', '')}, "
            f"net={row['portfolio_return_net']}, "
            f"benchmark={row['benchmark_return']}, benchmark_mix={row.get('benchmark_mix', '')}, turnover={row['turnover']}, "
            f"missing_weight={row.get('missing_weight', 0.0)}, missing_positions={row.get('missing_position_count', 0)}, "
            f"validity={row.get('return_validity', '')}, low_confidence={row.get('low_confidence_flag', 0)}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_factor_evaluation_report(path: Path, evaluation: dict[str, object]) -> None:
    """把因子有效性评估结果写成 Markdown 报告。"""
    summary = evaluation.get("summary", {}) if isinstance(evaluation.get("summary"), dict) else {}
    factor_rows = evaluation.get("factor_rows", []) if isinstance(evaluation.get("factor_rows"), list) else []
    distribution_rows = evaluation.get("distribution_rows", []) if isinstance(evaluation.get("distribution_rows"), list) else []
    bucket_rows = evaluation.get("bucket_rows", []) if isinstance(evaluation.get("bucket_rows"), list) else []
    correlation_rows = evaluation.get("correlation_rows", []) if isinstance(evaluation.get("correlation_rows"), list) else []
    high_correlation_rows = [row for row in correlation_rows if int(row.get("high_correlation_flag", 0)) == 1]
    lines = [
        "# Factor Evaluation Report",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Factor Diagnostics", ""])
    for row in factor_rows:
        lines.append(
            f"- {row['factor_name']}: direction={row['direction']} "
            f"months={row['evaluation_months']} avg_rankic={row['avg_rankic']} "
            f"rankic_ir={row['rankic_ir']} "
            f"top_bottom_next_return={row['avg_top_bottom_next_return']} "
            f"direction_ok={row['direction_ok']}"
        )
    lines.extend(["", "## Distribution Diagnostics", ""])
    for row in distribution_rows:
        lines.append(
            f"- {row['factor_name']}: sample_count={row['sample_count']} "
            f"missing_ratio={row['missing_ratio']} mean={row['mean']} std={row['std']} "
            f"p10={row['p10']} p50={row['p50']} p90={row['p90']}"
        )
    lines.extend(["", "## Bucket Diagnostics", ""])
    for row in bucket_rows:
        lines.append(
            f"- {row['factor_name']}: months={row['bucket_evaluation_months']} "
            f"bucket1={row['bucket_1_avg_next_return']} bucket3={row['bucket_3_avg_next_return']} "
            f"bucket5={row['bucket_5_avg_next_return']} top_bottom={row['avg_top_bottom_next_return']} "
            f"monotonic_ratio={row['monotonic_month_ratio']}"
        )
    lines.extend(["", "## High Correlation Pairs", ""])
    if high_correlation_rows:
        for row in high_correlation_rows[:20]:
            lines.append(
                f"- {row['factor_left']} vs {row['factor_right']}: "
                f"months={row['evaluation_months']} avg_spearman_corr={row['avg_spearman_corr']} "
                f"positive_corr_ratio={row['positive_corr_ratio']}"
            )
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_ingestion_audit_report(path: Path, config: AppConfig, dataset_metadata: dict[str, object]) -> None:
    """把数据接入阶段的份额到实体漏斗写成审计报告。"""
    audit = dataset_metadata.get("ingestion_audit", {}) if isinstance(dataset_metadata.get("ingestion_audit"), dict) else {}
    dropped_entities = audit.get("dropped_entities", []) if isinstance(audit.get("dropped_entities"), list) else []
    lines = [
        "# Ingestion Audit Report",
        "",
        "## Audit Context",
        "",
        f"- as_of_date: {config.as_of_date}",
        f"- data_source: {config.data_source}",
        f"- dataset_source: {dataset_metadata.get('source_name', 'unknown')}",
        f"- selected_share_class_count: {audit.get('selected_share_class_count', 'n/a')}",
        f"- grouped_entity_count: {audit.get('grouped_entity_count', 'n/a')}",
        f"- retained_share_class_count: {audit.get('retained_share_class_count', 'n/a')}",
        f"- retained_entity_count: {audit.get('retained_entity_count', 'n/a')}",
        f"- dropped_entity_count: {audit.get('dropped_entity_count', 'n/a')}",
        "",
        "## Ingestion Funnel",
        "",
        f"- 初始选中份额类: {audit.get('selected_share_class_count', 'n/a')}",
        f"- 归并后基金实体: {audit.get('grouped_entity_count', 'n/a')}",
        f"- 成功进入 clean 的份额类: {audit.get('retained_share_class_count', 'n/a')}",
        f"- 成功进入 clean 的基金实体: {audit.get('retained_entity_count', 'n/a')}",
        f"- 在 clean 层之前被丢弃的基金实体: {audit.get('dropped_entity_count', 'n/a')}",
        "",
        "## Dropped Entities",
        "",
    ]
    for row in dropped_entities[:50]:
        lines.append(
            f"- {row.get('entity_name', row.get('entity_id', 'unknown'))}: "
            f"company={row.get('fund_company', '')} "
            f"type={row.get('primary_type', '')} "
            f"share_class_count={row.get('share_class_count', 'n/a')} "
            f"share_class_ids={row.get('share_class_ids', '')} "
            f"reason={row.get('drop_reason', 'unknown')}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_fund_type_audit_report(
    path: Path,
    config: AppConfig,
    dataset_metadata: dict[str, object],
    fund_type_rows: list[dict[str, object]],
) -> None:
    """把基金类型标准化结果写成审计报告。"""
    summary = dataset_metadata.get("fund_type_audit_summary", {}) if isinstance(dataset_metadata.get("fund_type_audit_summary"), dict) else {}
    by_primary_type = summary.get("by_primary_type", {}) if isinstance(summary.get("by_primary_type"), dict) else {}
    by_confidence = summary.get("by_confidence", {}) if isinstance(summary.get("by_confidence"), dict) else {}
    low_confidence_rows = [row for row in fund_type_rows if str(row.get("confidence", "")) == "low"]
    lines = [
        "# Fund Type Audit Report",
        "",
        "## Audit Context",
        "",
        f"- as_of_date: {config.as_of_date}",
        f"- data_source: {config.data_source}",
        f"- audited_entity_count: {summary.get('entity_count', len(fund_type_rows))}",
        "",
        "## By Primary Type",
        "",
    ]
    for primary_type in sorted(by_primary_type):
        lines.append(f"- {primary_type}: {by_primary_type[primary_type]}")
    lines.extend(["", "## By Confidence", ""])
    for confidence in sorted(by_confidence):
        lines.append(f"- {confidence}: {by_confidence[confidence]}")
    lines.extend(["", "## Low Confidence Or Fallback Cases", ""])
    for row in low_confidence_rows[:50]:
        lines.append(
            f"- {row.get('entity_name', row.get('entity_id', 'unknown'))}: "
            f"primary_type={row.get('primary_type', '')} "
            f"raw_fund_type={row.get('raw_fund_type', '')} "
            f"raw_invest_type={row.get('raw_invest_type', '')} "
            f"rule={row.get('rule_code', '')} "
            f"reason={row.get('reason', '')}"
        )
    lines.extend(["", "## Sample Rows", ""])
    for row in fund_type_rows[:50]:
        lines.append(
            f"- {row.get('entity_name', row.get('entity_id', 'unknown'))}: "
            f"primary_type={row.get('primary_type', '')} "
            f"confidence={row.get('confidence', '')} "
            f"rule={row.get('rule_code', '')} "
            f"raw_fund_type={row.get('raw_fund_type', '')}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_fund_liquidity_audit_report(
    path: Path,
    config: AppConfig,
    dataset_metadata: dict[str, object],
    fund_liquidity_rows: list[dict[str, object]],
) -> None:
    """把最低持有期识别结果写成审计报告。"""
    summary = dataset_metadata.get("fund_liquidity_audit_summary", {}) if isinstance(dataset_metadata.get("fund_liquidity_audit_summary"), dict) else {}
    restricted_rows = [row for row in fund_liquidity_rows if int(str(row.get("liquidity_restricted") or "0")) == 1]
    lines = [
        "# Fund Liquidity Audit Report",
        "",
        "## Audit Context",
        "",
        f"- as_of_date: {config.as_of_date}",
        f"- data_source: {config.data_source}",
        f"- audited_entity_count: {summary.get('entity_count', len(fund_liquidity_rows))}",
        f"- restricted_entity_count: {summary.get('restricted_entity_count', len(restricted_rows))}",
        "",
        "## Restricted By Rule",
        "",
    ]
    for rule_code, count in (summary.get("restricted_by_rule", {}) if isinstance(summary.get("restricted_by_rule"), dict) else {}).items():
        lines.append(f"- {rule_code}: {count}")
    lines.extend(["", "## Restricted Funds", ""])
    for row in restricted_rows[:100]:
        lines.append(
            f"- {row.get('entity_name', row.get('entity_id', 'unknown'))}: "
            f"holding_lock_months={row.get('holding_lock_months', '')} "
            f"rule={row.get('rule_code', '')} "
            f"confidence={row.get('confidence', '')} "
            f"reason={row.get('reason', '')}"
        )
    lines.extend(["", "## Sample Rows", ""])
    for row in fund_liquidity_rows[:50]:
        lines.append(
            f"- {row.get('entity_name', row.get('entity_id', 'unknown'))}: "
            f"liquidity_restricted={row.get('liquidity_restricted', '')} "
            f"holding_lock_months={row.get('holding_lock_months', '')} "
            f"rule={row.get('rule_code', '')}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_fetch_diagnostics_report(path: Path, dataset_metadata: dict[str, object]) -> None:
    """把抓数过程中的接口耗时、失败和错误样本写成诊断报告。"""
    diagnostics = dataset_metadata.get("fetch_diagnostics", {}) if isinstance(dataset_metadata.get("fetch_diagnostics"), dict) else {}
    api_call_stats = diagnostics.get("api_call_stats", {}) if isinstance(diagnostics.get("api_call_stats"), dict) else {}
    api_cache_stats = diagnostics.get("api_cache_stats", {}) if isinstance(diagnostics.get("api_cache_stats"), dict) else {}
    api_error_samples = diagnostics.get("api_error_samples", []) if isinstance(diagnostics.get("api_error_samples"), list) else []
    lines = [
        "# Fetch Diagnostics Report",
        "",
        "## Summary",
        "",
        f"- runtime_seconds: {diagnostics.get('runtime_seconds', 'n/a')}",
        f"- api_count: {len(api_call_stats)}",
        f"- error_sample_count: {len(api_error_samples)}",
        "",
        "## API Call Stats",
        "",
    ]
    for api_name, payload in api_call_stats.items():
        if isinstance(payload, dict):
            lines.append(
                f"- {api_name}: calls={payload.get('calls', 'n/a')} "
                f"failures={payload.get('failures', 'n/a')} "
                f"elapsed_seconds={payload.get('elapsed_seconds', 'n/a')}"
            )
    lines.extend(["", "## API Cache Stats", ""])
    for api_name, payload in api_cache_stats.items():
        if isinstance(payload, dict):
            lines.append(
                f"- {api_name}: hits={payload.get('hits', 'n/a')} "
                f"misses={payload.get('misses', 'n/a')}"
            )
    lines.extend(["", "## Error Samples", ""])
    for row in api_error_samples[:50]:
        lines.append(
            f"- api={row.get('api_name', '')} ts_code={row.get('ts_code', '') or 'n/a'} "
            f"attempt={row.get('attempt', '')} error={row.get('error', '')}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_fetch_retry_report(path: Path, refresh_result: dict[str, object]) -> None:
    """把失败项增量补抓的结果写成报告。"""
    diagnostics = refresh_result.get("fetch_diagnostics", {}) if isinstance(refresh_result.get("fetch_diagnostics"), dict) else {}
    api_call_stats = diagnostics.get("api_call_stats", {}) if isinstance(diagnostics.get("api_call_stats"), dict) else {}
    api_cache_stats = diagnostics.get("api_cache_stats", {}) if isinstance(diagnostics.get("api_cache_stats"), dict) else {}
    error_samples = diagnostics.get("api_error_samples", []) if isinstance(diagnostics.get("api_error_samples"), list) else []
    lines = [
        "# Fetch Retry Report",
        "",
        "## Summary",
        "",
        f"- generated_at: {refresh_result.get('generated_at', 'n/a')}",
        f"- runtime_seconds: {refresh_result.get('runtime_seconds', 'n/a')}",
        f"- failed_ts_code_count: {refresh_result.get('failed_ts_code_count', 'n/a')}",
        f"- success_ts_code_count: {refresh_result.get('success_ts_code_count', 'n/a')}",
        f"- failed_ts_code_count_after_retry: {refresh_result.get('failed_ts_code_count_after_retry', 'n/a')}",
        "",
        "## API Call Stats",
        "",
    ]
    for api_name, payload in api_call_stats.items():
        if isinstance(payload, dict):
            lines.append(f"- {api_name}: calls={payload.get('calls', 'n/a')} failures={payload.get('failures', 'n/a')} elapsed_seconds={payload.get('elapsed_seconds', 'n/a')}")
    lines.extend(["", "## API Cache Stats", ""])
    for api_name, payload in api_cache_stats.items():
        if isinstance(payload, dict):
            lines.append(f"- {api_name}: hits={payload.get('hits', 'n/a')} misses={payload.get('misses', 'n/a')}")
    lines.extend(["", "## Failed TS Codes After Retry", ""])
    for ts_code in refresh_result.get("failed_ts_codes_after_retry", []) if isinstance(refresh_result.get("failed_ts_codes_after_retry"), list) else []:
        lines.append(f"- {ts_code}")
    lines.extend(["", "## Error Samples", ""])
    for row in error_samples[:50]:
        lines.append(f"- api={row.get('api_name', '')} ts_code={row.get('ts_code', '') or 'n/a'} attempt={row.get('attempt', '')} error={row.get('error', '')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_experiment_report(
    path: Path,
    config: AppConfig,
    dataset_metadata: dict[str, object],
    score_rows: list[dict[str, object]],
    portfolio_rows: list[dict[str, object]],
    backtest_rows: list[dict[str, object]],
    backtest_summary: dict[str, object],
) -> None:
    """把最新月评分、组合和回测摘要写成实验报告。"""
    latest_month = _latest_research_month(config, score_rows)
    top_risk_rows = sorted(
        [row for row in backtest_rows if float(row.get("missing_weight", 0.0)) > 0],
        key=lambda item: (-float(item.get("missing_weight", 0.0)), str(item.get("execution_month", ""))),
    )[:5]
    # 实验报告强调“这套配置+这份数据快照产出了什么结果”，因此先交代实验上下文，再摘要展示最新月与历史表现。
    latest_rows = _latest_month_rows(score_rows, latest_month, config.reporting.top_ranked_limit)
    month_range = dataset_metadata.get("month_range", {}) if isinstance(dataset_metadata.get("month_range"), dict) else {}
    lines = [
        "# Experiment Report",
        "",
        "## Experiment Context",
        "",
        f"- as_of_date: {config.as_of_date}",
        f"- data_source: {config.data_source}",
        f"- latest_month: {latest_month}",
        f"- dataset_source: {dataset_metadata.get('source_name', 'unknown')}",
        f"- benchmark_name: {dataset_metadata.get('benchmark_name', config.benchmark.series_for_key(config.benchmark.default_key).name)}",
        f"- benchmark_source: {dataset_metadata.get('benchmark_source', config.benchmark.source)}",
        f"- benchmark_ts_code: {dataset_metadata.get('benchmark_ts_code', config.benchmark.series_for_key(config.benchmark.default_key).ts_code or 'n/a')}",
        f"- entity_count: {dataset_metadata.get('entity_count', 'n/a')}",
        f"- share_class_count: {dataset_metadata.get('share_class_count', 'n/a')}",
        f"- month_range_start: {month_range.get('start', 'n/a')}",
        f"- month_range_end: {month_range.get('end', 'n/a')}",
        f"- candidate_count: {config.ranking.candidate_count}",
        f"- portfolio_size: {config.portfolio.portfolio_size}",
        f"- transaction_cost_bps: {config.backtest.transaction_cost_bps}",
        "",
        "## Benchmark Mapping",
        "",
    ]
    lines.extend(_benchmark_summary_lines(config, dataset_metadata))
    lines.extend([
        "",
        "## Latest Ranking Snapshot",
        "",
    ])
    for row in latest_rows:
        lines.append(
            f"- rank {row['rank']}: {row['entity_name']} "
            f"score={row['total_score']} perf={row['performance_quality']} "
            f"risk={row['risk_control']} stability={row['stability_quality']}"
        )
    lines.extend(["", "## Time Boundary Notes", ""])
    lines.extend(_time_boundary_notes())
    lines.extend(["", "## Latest Portfolio Snapshot", ""])
    for row in portfolio_rows:
        lines.append(
            f"- {row['entity_name']}: weight={row['target_weight']} rank={row['rank']} "
            f"company={row['fund_company']} score={row['total_score']}"
        )
    lines.extend(["", "## Backtest Summary", ""])
    for key, value in backtest_summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Backtest Reliability", ""])
    lines.append(f"- missing_month_count: {backtest_summary.get('missing_month_count', 0)}")
    lines.append(f"- low_confidence_month_count: {backtest_summary.get('low_confidence_month_count', 0)}")
    lines.append(f"- avg_missing_weight: {backtest_summary.get('avg_missing_weight', 0.0)}")
    lines.append(f"- max_missing_weight: {backtest_summary.get('max_missing_weight', 0.0)}")
    if int(backtest_summary.get("low_confidence_month_count", 0)) > 0:
        lines.append("- interpretation: 存在低置信度月份，建议结合 backtest_report.md 与 backtest_position_audit.csv 一起阅读。")
    else:
        lines.append("- interpretation: 当前回测未识别出低置信度月份。")
    lines.extend(["", "## Top Risk Months", ""])
    if top_risk_rows:
        for row in top_risk_rows:
            lines.append(
                f"- {row['execution_month']}: signal_month={row.get('signal_month', '')} "
                f"missing_weight={row.get('missing_weight', 0.0)} "
                f"missing_positions={row.get('missing_position_count', 0)} "
                f"validity={row.get('return_validity', '')} "
                f"low_confidence={row.get('low_confidence_flag', 0)}"
            )
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_portfolio_report(
    path: Path,
    config: AppConfig,
    dataset_metadata: dict[str, object],
    latest_month: str,
    latest_scores: list[dict[str, object]],
    portfolio_rows: list[dict[str, object]],
) -> None:
    """把最新一期组合建议写成独立报告。"""
    top_ranked_rows = latest_scores[: config.reporting.top_ranked_limit]
    selected_ids = {str(row["entity_id"]) for row in portfolio_rows}
    near_misses = [row for row in latest_scores if str(row["entity_id"]) not in selected_ids][: config.reporting.top_ranked_limit]
    selected_companies = sorted({str(row["fund_company"]) for row in portfolio_rows})
    lines = [
        "# Portfolio Report",
        "",
        "## Decision Context",
        "",
        f"- as_of_date: {config.as_of_date}",
        f"- latest_month: {latest_month}",
        f"- data_source: {config.data_source}",
        f"- dataset_source: {dataset_metadata.get('source_name', 'unknown')}",
        f"- benchmark_name: {dataset_metadata.get('benchmark_name', config.benchmark.series_for_key(config.benchmark.default_key).name)}",
        f"- eligible_funds: {len(latest_scores)}",
        f"- portfolio_size: {len(portfolio_rows)}",
        f"- weighting_method: {config.portfolio.weighting_method}",
        f"- single_fund_cap: {config.portfolio.single_fund_cap}",
        f"- single_company_max: {config.portfolio.single_company_max}",
        f"- selected_companies: {', '.join(selected_companies) if selected_companies else 'n/a'}",
        "",
        "## Benchmark Mapping",
        "",
    ]
    lines.extend(_benchmark_summary_lines(config, dataset_metadata))
    lines.extend([
        "",
        "## Top Ranked Candidates",
        "",
    ])
    for row in top_ranked_rows:
        lines.append(
            f"- rank {row['rank']}: {row['entity_name']} "
            f"score={row['total_score']} perf={row['performance_quality']} risk={row['risk_control']} stability={row['stability_quality']}"
        )
    lines.extend(["", "## Time Boundary Notes", ""])
    lines.extend(_time_boundary_notes())
    lines.extend(["", "## Selected Portfolio", ""])
    for row in portfolio_rows:
        lines.append(
            f"- {row['entity_name']}: weight={row['target_weight']} rank={row['rank']} "
            f"company={row['fund_company']} score={row['total_score']}"
        )
    lines.extend(["", "## High Ranked But Not Selected", ""])
    for row in near_misses:
        lines.append(f"- rank {row['rank']}: {row['entity_name']} company={row['fund_company']} score={row['total_score']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_universe_audit_report(
    path: Path,
    config: AppConfig,
    dataset_metadata: dict[str, object],
    entity_rows: list[dict[str, object]],
    universe_rows: list[dict[str, object]],
) -> None:
    """把最新月基金池漏斗和剔除原因写成审计报告。"""
    latest_month = _latest_research_month(config, universe_rows)
    latest_universe_rows = [row for row in universe_rows if str(row["month"]) == latest_month]
    entity_lookup = {str(row["entity_id"]): row for row in entity_rows}
    latest_entity_ids = {str(row["entity_id"]) for row in latest_universe_rows}
    latest_reason_map = _latest_reason_map(latest_universe_rows)
    current_ids = [str(row["entity_id"]) for row in entity_rows]
    eligible_rows = [row for row in latest_universe_rows if int(row["is_eligible"]) == 1]
    reason_counter: Counter[str] = Counter()
    for row in latest_universe_rows:
        for reason in [item for item in str(row["reason_codes"]).split("|") if item]:
            reason_counter[reason] += 1
    type_counter: Counter[str] = Counter(str(entity.get("primary_type", "")) for entity in entity_rows)
    allowed_type_counter: Counter[str] = Counter(
        str(entity_lookup[entity_id].get("primary_type", ""))
        for entity_id in current_ids
        if str(entity_lookup[entity_id].get("primary_type", "")) in config.universe.allowed_primary_types
    )
    excluded_type_counter: Counter[str] = Counter(
        str(entity_lookup[entity_id].get("primary_type", ""))
        for entity_id in current_ids
        if str(entity_lookup[entity_id].get("primary_type", "")) not in config.universe.allowed_primary_types
    )
    eligible_type_counter: Counter[str] = Counter(str(entity_lookup[str(row["entity_id"])].get("primary_type", "")) for row in eligible_rows)

    funnel_rows = [
        ("初始基金主体", current_ids),
        (
            "保留允许一级分类后",
            [entity_id for entity_id in current_ids if str(entity_lookup[entity_id]["primary_type"]) in config.universe.allowed_primary_types],
        ),
    ]
    filtered_by_name = [
        entity_id
        for entity_id in funnel_rows[-1][1]
        if not any(keyword in str(entity_lookup[entity_id]["entity_name"]) for keyword in config.universe.exclude_name_keywords)
    ]
    funnel_rows.append(("剔除名称关键词后", filtered_by_name))
    filtered_by_liquidity = [
        entity_id for entity_id in funnel_rows[-1][1]
        if int(str(entity_lookup[entity_id].get("liquidity_restricted") or "0")) != 1
    ]
    funnel_rows.append(("剔除最低持有期后", filtered_by_liquidity))
    filtered_by_history = [
        entity_id
        for entity_id in funnel_rows[-1][1]
        if entity_id in latest_entity_ids and "insufficient_history" not in str(latest_reason_map.get(entity_id, "")).split("|")
    ]
    funnel_rows.append(("满足最少历史月数后", filtered_by_history))
    filtered_by_assets = [
        entity_id
        for entity_id in funnel_rows[-1][1]
        if entity_id in latest_entity_ids and "assets_below_threshold" not in str(latest_reason_map.get(entity_id, "")).split("|")
    ]
    funnel_rows.append(("满足规模门槛后", filtered_by_assets))

    asset_blocked_rows = []
    for row in latest_universe_rows:
        reasons = [item for item in str(row["reason_codes"]).split("|") if item]
        if "assets_below_threshold" in reasons:
            entity = entity_lookup.get(str(row["entity_id"]), {})
            asset_blocked_rows.append(
                {
                    "entity_id": str(row["entity_id"]),
                    "entity_name": str(entity.get("entity_name", row["entity_id"])),
                    "primary_type": str(entity.get("primary_type", row.get("primary_type", ""))),
                    "visible_assets_cny_mn": row.get("visible_assets_cny_mn", "n/a"),
                    "visible_history_months": row.get("visible_history_months", "n/a"),
                    "fund_age_months": row.get("fund_age_months", "n/a"),
                    "nav_available_date": row.get("nav_available_date", ""),
                    "reason_codes": str(row["reason_codes"]),
                }
            )
    asset_blocked_rows.sort(
        key=lambda item: float(item["visible_assets_cny_mn"]) if str(item["visible_assets_cny_mn"]).replace(".", "", 1).isdigit() else -1.0
    )

    lines = [
        "# Universe Audit Report",
        "",
        "## Audit Context",
        "",
        f"- as_of_date: {config.as_of_date}",
        f"- latest_month: {latest_month}",
        f"- data_source: {config.data_source}",
        f"- dataset_source: {dataset_metadata.get('source_name', 'unknown')}",
        f"- entity_count: {len(entity_rows)}",
        f"- eligible_count: {len(eligible_rows)}",
        f"- allowed_primary_types: {', '.join(config.universe.allowed_primary_types)}",
        f"- exclude_name_keywords: {', '.join(config.universe.exclude_name_keywords)}",
        f"- min_history_months: {config.universe.min_history_months}",
        f"- min_assets_cny_mn: {config.universe.min_assets_cny_mn}",
        "",
        "## Latest Month Funnel",
        "",
    ]
    previous_count = None
    for step_name, entity_ids in funnel_rows:
        count = len(entity_ids)
        drop_text = "n/a" if previous_count is None else str(previous_count - count)
        lines.append(f"- {step_name}: count={count} dropped={drop_text}")
        previous_count = count

    lines.extend(["", "## Type Funnel", ""])
    for primary_type, count in sorted(type_counter.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- 初始主体: type={primary_type} count={count}")
    for primary_type, count in sorted(allowed_type_counter.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- 保留类型后: type={primary_type} count={count}")
    for primary_type, count in sorted(excluded_type_counter.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- 被整体排除类型: type={primary_type} count={count}")
    for primary_type, count in sorted(eligible_type_counter.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- 最新月可投: type={primary_type} count={count}")

    lines.extend(["", "## Reason Counts", ""])
    for reason, count in sorted(reason_counter.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {reason}: {count}")

    lines.extend(["", "## Eligible Funds", ""])
    for row in sorted(eligible_rows, key=lambda item: str(item["entity_id"])):
        entity = entity_lookup.get(str(row["entity_id"]), {})
        lines.append(
            f"- {entity.get('entity_name', row['entity_id'])}: "
            f"company={entity.get('fund_company', row.get('fund_company', ''))} "
            f"type={entity.get('primary_type', row.get('primary_type', ''))} "
            f"visible_assets_cny_mn={row.get('visible_assets_cny_mn', 'n/a')} "
            f"visible_history_months={row.get('visible_history_months', 'n/a')} "
            f"fund_age_months={row.get('fund_age_months', 'n/a')}"
        )

    lines.extend(["", "## Funds Blocked By Asset Threshold", ""])
    for row in asset_blocked_rows[:20]:
        lines.append(
            f"- {row['entity_name']}: type={row['primary_type']} "
            f"visible_assets_cny_mn={row['visible_assets_cny_mn']} "
            f"visible_history_months={row['visible_history_months']} "
            f"fund_age_months={row['fund_age_months']} "
            f"nav_available_date={row['nav_available_date'] or 'n/a'} "
            f"reasons={row['reason_codes']}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _latest_reason_map(latest_universe_rows: list[dict[str, object]]) -> dict[str, str]:
    """把最新月基金池原因码整理成按基金主体索引的映射。"""
    return {str(row["entity_id"]): str(row["reason_codes"]) for row in latest_universe_rows}
