# `tushare_scoring_v2_lite` Baseline 升级评审记录

本文档用于记录 2026-03-27 对 [`tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json) 的 baseline 升级评审结论。

评审口径依据：

- [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md)
- [`robustness_analysis.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)
- [`candidate_validation_spec.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)

本次记录建立在以下两项口径更新之后：

- 样本规模从 `max_funds=1000` 扩大到 `max_funds=5000`
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
  - `2026-03-27`

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

- baseline 实验记录生成时间：`2026-03-27T03:36:34Z`
- `v2-lite` 实验记录生成时间：`2026-03-27T03:36:34Z`
- 两者使用的 `dataset_snapshot.generated_at` 都是 `2026-03-27T03:18:41Z`
- 两者 `requested_max_funds = 5000`
- 两者 `entity_count = 3186`
- 两者 `share_class_count = 4995`
- 当前回测主口径固定使用 `benchmark.default_key = broad_equity`
- 当前固定市场 benchmark 名称：`中证800`

结论：

- 本次评审满足“同口径升级讨论”的前提条件

## 3. 收益变化摘要

baseline 回测摘要：

- `cumulative_return = 0.437317`
- `annualized_return = 0.124859`
- `annualized_volatility = 0.0846`
- `max_drawdown = -0.043211`
- `benchmark_cumulative_return = 0.196065`
- `excess_cumulative_return = 0.241252`

`v2-lite` 回测摘要：

- `cumulative_return = 0.545619`
- `annualized_return = 0.151677`
- `annualized_volatility = 0.097508`
- `max_drawdown = -0.039342`
- `benchmark_cumulative_return = 0.196065`
- `excess_cumulative_return = 0.349554`

直接观察：

- `v2-lite` 相对 baseline 的累计收益和超额收益仍明显更强，且在 `5000` 样本下领先幅度较 `3000` 样本进一步扩大
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

- `annualized_volatility` 从 `0.0846` 上升到 `0.097508`
- `max_drawdown` 从 `-0.043211` 改善到 `-0.039342`
- `turnover_risk_flag = 1`
- `excess_attribution_assessment = selection_dominant`
- `benchmark_driven_delta_sum = 0.0`
- `selection_driven_delta_sum = 0.076852`

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

- `style_phase_assessment = broadly_distributed`
- `window_assessment = window_broad`
- `recommended_decision = ready_for_baseline_review`
- `selection_dominant = 是`
- `benchmark_driven_share = 0.0`
- `positive_window_ratio = 0.846154`

解释：

- `v2-lite` 现在已经通过时间切片一致性检查
- `return_concentration_flag = 0`，且 `top3_positive_excess_share = 0.393178`，说明收益不依赖极少数月份
- 收益改善主要来自 selection，这一点继续成立
- 阶段分布已经从 `partially_concentrated` 改善到 `broadly_distributed`
- 候选补证已经给出 `ready_for_baseline_review`

判断：

- 与 `3000` 样本评审相比，稳健性证据继续变强
- 当前已经满足“selection 主导 + 非单窗口集中 + 关键阶段多数分布胜出”的要求

结论：

- 稳健性结构：`通过`

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
- 稳健性结构：`通过`
- 逻辑可解释性：`通过`

按 [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md) 的决策规则：

- `3 个通过 + 1 个存疑`

对应结论：

- `可进入升级为 baseline 讨论`

## 6. 最终决策

决策结论：

- `tushare_scoring_v2_lite` 已具备进入“升级为默认 baseline”正式讨论的条件
- 当前建议定位上调为：`准备进入 baseline 升级讨论`
- 在完成最终人工确认前，仍可继续保留旧 [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json) 作为对照基线

原因概括：

- `v2-lite` 的收益改善是真实的，且在固定市场 benchmark 口径下仍成立
- 它的收益改善主要来自 selection，而不是 benchmark 暴露
- 它比 baseline 更干净，也比旧 `v2` 更少依赖短样本事件因子
- 扩样本到 `5000` 后，`v2-lite` 相对 baseline 的累计超额优势扩大到 `10.83pct`
- 候选补证结论已从 `keep_candidate_pending_more_validation` 上调为 `ready_for_baseline_review`
- `style_phase_assessment` 也从 `partially_concentrated` 改善到 `broadly_distributed`
- 当前剩余主要疑点不再是收益真实性或稳健性结构，而是更高波动与更高换仓是否可接受

因此，本轮评审结论从“继续保留为主候选基线”上调为“可以进入升级为 baseline 的正式讨论阶段”。

## 7. 是否需要更多验证

- 需要，但验证重点已明显收敛

下一步建议聚焦：

- 单独解释 `turnover_risk_flag = 1` 的来源，确认更高换仓是否可接受
- 对更高波动是否可接受给出业务层判断，而不是继续停留在研究层判断
- 若正式升级 baseline，应继续沿用固定市场 benchmark 口径，不再回退到动态混合 benchmark

## 8. 评审引用产物

- [`comparison_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/comparison/comparison_report.md)
- [`robustness_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/robustness/robustness_report.md)
- [`candidate_validation_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/candidate_validation/candidate_validation_report.md)
- [`experiment_registry.jsonl`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/experiments/experiment_registry.jsonl)
