# `tushare_scoring_v2` Baseline 升级评审记录

本文档用于记录 2026-03-25 对 [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json) 的 baseline 升级评审结论。

评审口径依据：

- [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md)
- [`robustness_analysis.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)
- [`candidate_validation_spec.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)

本次记录替代 2026-03-24 的旧版评审结论，原因是偏股混合 benchmark 已统一改挂 `中证800`，相关实验已按新口径重跑。

## 1. 评审对象

- 候选配置：
  - [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)
- 当前 baseline：
  - [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
- 数据源：
  - `tushare`
- 评审日期：
  - `2026-03-25`

## 2. 前提核对

- 候选配置路径明确：是
- baseline 配置路径明确：是
- 数据快照是否一致：是
- benchmark 口径是否一致：是
- 基金池口径是否一致：是
- 信号与执行时点是否一致：是
- 成本口径是否一致：是
- 是否来源于标准实验流程：是

补充说明：

- baseline 实验记录生成时间：`2026-03-25T10:06:13Z`
- `v2` 实验记录生成时间：`2026-03-25T10:07:52Z`
- 两者使用的 `dataset_snapshot.generated_at` 都是 `2026-03-21T14:59:34Z`
- 两者 `benchmark_primary_type_map` 一致：
  - `主动股票 -> broad_equity`
  - `偏股混合 -> broad_equity`
  - `灵活配置混合 -> broad_equity`
- 默认 benchmark 名称一致：`中证800`

结论：

- 本次评审满足“同口径升级讨论”的前提条件

## 3. 收益变化摘要

baseline 回测摘要：

- `cumulative_return = 0.235298`
- `annualized_return = 0.070937`
- `annualized_volatility = 0.065674`
- `max_drawdown = -0.072212`
- `benchmark_cumulative_return = 0.170682`
- `excess_cumulative_return = 0.064616`

`v2` 回测摘要：

- `cumulative_return = 0.36985`
- `annualized_return = 0.107456`
- `annualized_volatility = 0.101006`
- `max_drawdown = -0.073463`
- `benchmark_cumulative_return = 0.170682`
- `excess_cumulative_return = 0.199168`

直接观察：

- 累计收益显著提升
- 年化收益显著提升
- 超额累计收益显著提升
- 最大回撤只小幅变差
- 波动明显抬升

## 4. 四道门槛逐项评审

### 4.1 收益真实性

核对结果：

- `entity_count_delta = 0`
- `eligible_count_delta = 0`
- `missing_month_count_delta = 0`
- `low_confidence_month_count_delta = 0`
- `max_missing_weight_delta = 0`
- `benchmark_cumulative_return_delta = 0`

判断：

- 收益改善来自同一数据快照、同一基金池、同一 benchmark 口径和同一回测边界
- 当前没有证据表明 `v2` 的提升来自样本变化、benchmark 切换或缺失处理差异

结论：

- 收益真实性：`通过`

### 4.2 风险解释充分性

观察结果：

- `annualized_volatility` 从 `0.065674` 上升到 `0.101006`
- `max_drawdown` 从 `-0.072212` 变为 `-0.073463`
- `win_rate` 保持 `0.324324`
- `turnover_risk_flag = 0`
- `excess_attribution_assessment = selection_dominant`
- `benchmark_driven_delta_sum = 0.0`
- `selection_driven_delta_sum = 0.112517`

解释：

- `v2` 的收益提升不是“同风险下纯增厚收益”，而是以更高波动换取了更强收益
- 但当前补证显示，收益改善主要来自 `selection-driven excess`，不是 benchmark 驱动
- 最大回撤没有明显恶化，换手风险也没有触发红旗

结论：

- 风险解释充分性：`通过`

### 4.3 稳健性结构

稳健性摘要：

- `time_slice_consistency_flag = 0`
- `return_concentration_flag = 0`
- `turnover_risk_flag = 0`
- `factor_stability_flag = 1`
- `overall_assessment = needs_more_validation`

候选补证摘要：

- `style_phase_assessment = partially_concentrated`
- `window_assessment = window_broad`
- `recommended_decision = keep_candidate_pending_more_validation`
- `selection_dominant = 是`
- `benchmark_driven_share = 0.0`
- `positive_window_ratio = 0.692308`

解释：

- `v2` 没有表现出单窗口极端集中，`return_concentration_flag` 也没有触发
- 收益改善主要来自 selection，这一点是正面证据
- 但阶段分布仍显示 `partially_concentrated`
- 稳健性总评仍是 `needs_more_validation`
- 候选补证的直接建议仍然是 `keep_candidate_pending_more_validation`

判断：

- 按清单中的硬门槛，`selection_dominant`、`window_broad`、`return_concentration_flag = 0` 都满足
- 但从实际评审标准看，当前稳健性证据还不足以支持“直接升级”为明确结论

结论：

- 稳健性结构：`存疑`

### 4.4 逻辑可解释性

`v2` 相对 baseline 的核心变化：

- 去掉了较弱的 `ret_6m`
- 去掉了方向可疑的 `manager_tenure_months`
- 去掉了更容易与总收益重复暴露的 `vol_12m` / `max_drawdown_12m`
- 强化了 `excess_ret_12m`
- 引入了 `worst_3m_avg_return_12m`
- 保留了 `asset_stability_12m`
- 保留了样本较短的 `manager_post_change_excess_delta_12m`

解释：

- 从因子结构看，`v2` 比旧 baseline 更干净，信号也更聚焦
- 但事件型因子 `manager_post_change_excess_delta_12m` 的评估月份仍偏少，因此还不算完全定型

结论：

- 逻辑可解释性：`通过`

## 5. 评分汇总

- 收益真实性：`通过`
- 风险解释充分性：`通过`
- 稳健性结构：`存疑`
- 逻辑可解释性：`通过`

按 [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md) 的决策规则：

- `3 个通过 + 1 个存疑`

对应结论：

- `保留为主候选基线`

## 6. 最终决策

决策结论：

- `tushare_scoring_v2` 暂不直接升级为新的默认 baseline
- 当前更合适的定位是：`保留为主候选基线`

原因概括：

- 收益改善是真实的，且不是 benchmark 切换或样本变化造成的假提升
- 风险抬升可以解释，且主要来自 selection 而不是 benchmark 暴露
- 评分结构比旧 baseline 更干净
- 但稳健性层面仍存在 `partially_concentrated` 和 `needs_more_validation`
- 候选补证自己的推荐结论也仍是 `keep_candidate_pending_more_validation`

因此，本轮评审不支持把 `v2` 直接升级为默认 baseline。

## 7. 是否需要更多验证

- 需要

下一步建议聚焦：

- 继续细化 `partially_concentrated` 对应的风格阶段解释
- 继续观察 `manager_post_change_excess_delta_12m` 的样本稳定性
- 若后续要再次发起升级评审，优先补“不利 regime 是否明显失效”的更明确结论

## 8. 评审引用产物

- [`comparison_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/comparison/comparison_report.md)
- [`robustness_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/robustness/robustness_report.md)
- [`candidate_validation_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/candidate_validation/candidate_validation_report.md)
- [`experiment_registry.jsonl`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/experiments/experiment_registry.jsonl)
