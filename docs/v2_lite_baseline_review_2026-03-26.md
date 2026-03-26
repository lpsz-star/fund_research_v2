# `tushare_scoring_v2_lite` Baseline 升级评审记录

本文档用于记录 2026-03-26 对 [`tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json) 的 baseline 升级评审结论。

评审口径依据：

- [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md)
- [`robustness_analysis.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)
- [`candidate_validation_spec.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)

本次记录建立在 2026-03-25 中证800 benchmark 统一重跑之后，并吸收了“去掉 `manager_post_change_excess_delta_12m` 后再做一次最小对照实验”的新证据。

## 1. 评审对象

- 候选配置：
  - [`tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json)
- 当前 baseline：
  - [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
- 历史参考候选：
  - [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)
- 数据源：
  - `tushare`
- 评审日期：
  - `2026-03-26`

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

- baseline 实验记录生成时间：`2026-03-25T10:47:44Z`
- `v2` 实验记录生成时间：`2026-03-25T10:48:24Z`
- `v2-lite` 实验记录生成时间：`2026-03-25T10:48:49Z`
- 三者使用的 `dataset_snapshot.generated_at` 都是 `2026-03-21T14:59:34Z`
- 三者 `benchmark_primary_type_map` 一致：
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

`v2-lite` 回测摘要：

- `cumulative_return = 0.417063`
- `annualized_return = 0.119694`
- `annualized_volatility = 0.107443`
- `max_drawdown = -0.072839`
- `benchmark_cumulative_return = 0.170682`
- `excess_cumulative_return = 0.246381`

相对历史 `v2` 的补充观察：

- `cumulative_return` 进一步提升 `0.047213`
- `excess_cumulative_return` 进一步提升 `0.047213`
- `annualized_volatility` 仅增加 `0.006437`
- `max_drawdown` 反而略有改善 `0.000624`

直接观察：

- `v2-lite` 相对 baseline 的累计收益和超额收益提升都更强
- 波动仍明显高于 baseline
- 但删除事件型因子后，收益没有变差，说明 `manager_post_change_excess_delta_12m` 不是当前样本中不可替代的收益来源

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
- 当前没有证据表明 `v2-lite` 的提升来自样本变化、benchmark 切换或缺失处理差异

结论：

- 收益真实性：`通过`

### 4.2 风险解释充分性

观察结果：

- `annualized_volatility` 从 `0.065674` 上升到 `0.107443`
- `max_drawdown` 从 `-0.072212` 变为 `-0.072839`
- `turnover_risk_flag = 0`
- `excess_attribution_assessment = selection_dominant`
- `benchmark_driven_delta_sum = 0.0`
- `selection_driven_delta_sum = 0.148642`

解释：

- `v2-lite` 的收益改善同样不是“同风险下纯增厚收益”，而是承担了更高波动
- 但当前归因显示，收益改善主要来自 `selection-driven excess`，不是 benchmark 驱动
- 与旧 `v2` 相比，删除事件因子后收益更强、回撤更稳，因此“风险换收益”的交易没有变坏

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

- `v2-lite` 仍没有表现出单窗口极端集中，`return_concentration_flag` 也没有触发
- 收益改善主要来自 selection，这一点继续成立
- 但阶段分布仍显示 `partially_concentrated`
- 稳健性总评仍是 `needs_more_validation`
- 候选补证仍未给出“可直接升级”的建议

判断：

- 删除事件型因子后，稳健性口径没有恶化，但也没有从“存疑”提升为“明确通过”
- 因此，当前证据仍不足以支持直接升级默认 baseline

结论：

- 稳健性结构：`存疑`

### 4.4 逻辑可解释性

`v2-lite` 相对 baseline 的核心变化：

- 去掉了较弱的 `ret_6m`
- 去掉了方向可疑的 `manager_tenure_months`
- 去掉了更容易与总收益重复暴露的 `vol_12m` / `max_drawdown_12m`
- 强化了 `excess_ret_12m`
- 引入了 `worst_3m_avg_return_12m`
- 保留了 `asset_stability_12m`
- 不再依赖样本偏短的 `manager_post_change_excess_delta_12m`

解释：

- 从因子结构看，`v2-lite` 比 baseline 更干净
- 相比旧 `v2`，它进一步去掉了当前最不稳的一项事件型因子
- 这使得“为什么这套评分更值得信”比旧 `v2` 更容易解释

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

- `tushare_scoring_v2_lite` 暂不直接升级为新的默认 baseline
- 当前更合适的定位是：`保留为主候选基线`
- 旧 [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json) 降为历史参考候选

原因概括：

- `v2-lite` 的收益改善是真实的，且不是 benchmark 切换或样本变化造成的
- 它的收益改善主要来自 selection，而不是 benchmark 暴露
- 它比 baseline 更干净，也比旧 `v2` 更少依赖短样本事件因子
- 但稳健性层面仍存在 `partially_concentrated` 和 `needs_more_validation`
- 候选补证自己的推荐结论也仍是 `keep_candidate_pending_more_validation`

因此，本轮评审支持把 `v2-lite` 设为当前主候选，但仍不支持直接升级默认 baseline。

## 7. 是否需要更多验证

- 需要

下一步建议聚焦：

- 继续细化 `partially_concentrated` 对应的风格阶段解释
- 专门补“不利 regime 是否明显失效”的明确结论
- 若后续再次发起升级评审，优先围绕 `v2-lite` 而不是旧 `v2`

## 8. 评审引用产物

- [`comparison_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/comparison_report.md)
- [`robustness_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/robustness_report.md)
- [`candidate_validation_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/candidate_validation/candidate_validation_report.md)
- [`experiment_registry.jsonl`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/experiments/experiment_registry.jsonl)
