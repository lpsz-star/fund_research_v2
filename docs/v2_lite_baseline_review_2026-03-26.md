# `tushare_scoring_v2_lite` Baseline 升级评审记录

本文档用于记录 2026-03-26 对 [`tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json) 的 baseline 升级评审结论。

评审口径依据：

- [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md)
- [`robustness_analysis.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)
- [`candidate_validation_spec.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)

本次记录建立在以下两项口径更新之后：

- 样本规模从 `max_funds=1000` 扩大到 `max_funds=3000`
- 回测主 benchmark 改为固定市场 benchmark，不再按组合持仓动态混合 benchmark

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

- baseline 实验记录生成时间：`2026-03-26T05:17:03Z`
- `v2-lite` 实验记录生成时间：`2026-03-26T05:17:03Z`
- 两者使用的 `dataset_snapshot.generated_at` 都是 `2026-03-26T05:11:01Z`
- 两者 `requested_max_funds = 3000`
- 两者 `entity_count = 1893`
- 两者 `share_class_count = 2998`
- 当前回测主口径固定使用 `benchmark.default_key = broad_equity`
- 当前固定市场 benchmark 名称：`中证800`

结论：

- 本次评审满足“同口径升级讨论”的前提条件

## 3. 收益变化摘要

baseline 回测摘要：

- `cumulative_return = 0.335306`
- `annualized_return = 0.09832`
- `annualized_volatility = 0.068865`
- `max_drawdown = -0.065136`
- `benchmark_cumulative_return = 0.196065`
- `excess_cumulative_return = 0.13924`

`v2-lite` 回测摘要：

- `cumulative_return = 0.406786`
- `annualized_return = 0.117053`
- `annualized_volatility = 0.082093`
- `max_drawdown = -0.056967`
- `benchmark_cumulative_return = 0.196065`
- `excess_cumulative_return = 0.21072`

直接观察：

- `v2-lite` 相对 baseline 的累计收益和超额收益仍明显更强，但领先幅度较 `2000` 样本时有所收敛
- 波动仍高于 baseline
- 最大回撤反而优于 baseline
- 在固定市场 benchmark 口径下，benchmark 收益对两套方案完全一致，收益差异更容易解释

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

- 收益改善来自同一数据快照、同一基金池、同一固定市场 benchmark 口径和同一回测边界
- 当前没有证据表明 `v2-lite` 的提升来自样本变化、benchmark 切换或缺失处理差异

结论：

- 收益真实性：`通过`

### 4.2 风险解释充分性

观察结果：

- `annualized_volatility` 从 `0.068865` 上升到 `0.082093`
- `max_drawdown` 从 `-0.065136` 改善到 `-0.056967`
- `turnover_risk_flag = 1`
- `excess_attribution_assessment = selection_dominant`
- `benchmark_driven_delta_sum = 0.0`
- `selection_driven_delta_sum = 0.055471`

解释：

- `v2-lite` 的收益改善不是“同风险下纯增厚收益”，仍然伴随更高波动
- 但当前固定市场 benchmark 口径下，收益改善仍主要来自 `selection-driven excess`，不是 benchmark 驱动
- 回撤优于 baseline，说明更高收益并没有换来更差的极端下行表现
- 当前真正需要继续解释的风险点，不再是 beta，而是更高换仓是否适合作为默认 baseline

结论：

- 风险解释充分性：`存疑`

### 4.3 稳健性结构

稳健性摘要：

- `time_slice_consistency_flag = 1`
- `return_concentration_flag = 0`
- `turnover_risk_flag = 1`
- `factor_stability_flag = 1`
- `overall_assessment = keep_candidate`

候选补证摘要：

- `style_phase_assessment = partially_concentrated`
- `window_assessment = window_broad`
- `recommended_decision = keep_candidate_pending_more_validation`
- `selection_dominant = 是`
- `benchmark_driven_share = 0.0`
- `positive_window_ratio = 0.807692`

解释：

- `v2-lite` 现在已经通过时间切片一致性检查
- `return_concentration_flag = 0`，且 `top3_positive_excess_share = 0.308434`，说明收益不依赖极少数月份
- 收益改善主要来自 selection，这一点继续成立
- 但阶段分布仍显示 `partially_concentrated`
- 候选补证仍未给出“可直接升级”的建议

判断：

- 与旧版评审相比，稳健性证据明显变强
- 但当前仍不足以把稳健性直接判成“明确通过”

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
- 它不再依赖短样本事件型因子，逻辑比旧 `v2` 更容易解释
- 在固定市场 benchmark 口径下，这套评分结构的收益来源也更便于解读

结论：

- 逻辑可解释性：`通过`

## 5. 评分汇总

- 收益真实性：`通过`
- 风险解释充分性：`存疑`
- 稳健性结构：`存疑`
- 逻辑可解释性：`通过`

按 [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md) 的决策规则：

- `2 个通过 + 2 个存疑`

对应结论：

- `保留为主候选基线`

## 6. 最终决策

决策结论：

- `tushare_scoring_v2_lite` 暂不直接升级为新的默认 baseline
- 当前更合适的定位是：`保留为主候选基线`
- 旧 [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json) 继续作为历史参考候选

原因概括：

- `v2-lite` 的收益改善是真实的，且在固定市场 benchmark 口径下仍成立
- 它的收益改善主要来自 selection，而不是 benchmark 暴露
- 它比 baseline 更干净，也比旧 `v2` 更少依赖短样本事件因子
- 扩样本到 `3000` 后，`v2-lite` 仍能保持相对优势，`overall_assessment` 维持 `keep_candidate`
- 但相较 `2000` 样本时，`v2-lite` 相对 baseline 的累计超额优势收窄约 `3.94pct`
- 但当前仍存在 `partially_concentrated` 与 `turnover_risk_flag = 1`
- 候选补证自己的推荐结论仍是 `keep_candidate_pending_more_validation`

因此，本轮评审继续支持把 `v2-lite` 设为当前主候选，但仍不支持直接升级默认 baseline。

## 7. 是否需要更多验证

- 需要

下一步建议聚焦：

- 单独解释 `turnover_risk_flag = 1` 的来源，确认更高换仓是否可接受
- 继续细化 `partially_concentrated` 对应的风格阶段解释
- 若后续再次发起升级评审，应继续沿用固定市场 benchmark 口径，不再回退到动态混合 benchmark

## 8. 评审引用产物

- [`comparison_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/comparison_report.md)
- [`robustness_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/robustness_report.md)
- [`candidate_validation_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/candidate_validation/candidate_validation_report.md)
- [`experiment_registry.jsonl`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/experiments/experiment_registry.jsonl)
