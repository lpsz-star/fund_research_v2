# `tushare_scoring_v2_lite` Baseline 升级评审记录

本文档用于记录 2026-03-27 基于 `10000` 样本快照，对 [`tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json) 的 baseline 升级评审结论。

评审口径依据：

- [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md)
- [`robustness_analysis.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)
- [`candidate_validation_spec.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)

本次记录是对 [`v2_lite_baseline_review_2026-03-26.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_lite_baseline_review_2026-03-26.md) 的扩样本重评，不替代历史记录。

## 1. 评审对象

- 候选配置：
  - [`tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json)
- 当前 baseline：
  - [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
- 数据源：
  - `tushare`
- 评审日期：
  - `2026-03-27`
- 本轮样本口径：
  - `requested_max_funds = 10000`

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

- baseline 实验记录生成时间：`2026-03-27T07:08:08Z`
- `v2-lite` 实验记录生成时间：`2026-03-27T07:08:52Z`
- `dataset_snapshot.generated_at = 2026-03-27T06:44:47Z`
- `requested_max_funds = 10000`
- `entity_count = 6493`
- `share_class_count = 9988`
- `eligible_count = 807`
- 当前回测主口径固定使用 `benchmark.default_key = broad_equity`
- 当前固定市场 benchmark 名称：`中证800`

结论：

- 本次评审满足“同口径升级讨论”的前提条件

## 3. 收益变化摘要

baseline 回测摘要：

- `cumulative_return = 0.441169`
- `annualized_return = 0.125836`
- `annualized_volatility = 0.087328`
- `max_drawdown = -0.043211`
- `benchmark_cumulative_return = 0.196065`
- `excess_cumulative_return = 0.245103`
- `win_rate = 0.405405`

`v2-lite` 回测摘要：

- `cumulative_return = 0.561076`
- `annualized_return = 0.155399`
- `annualized_volatility = 0.098866`
- `max_drawdown = -0.039342`
- `benchmark_cumulative_return = 0.196065`
- `excess_cumulative_return = 0.36501`
- `win_rate = 0.378378`

直接观察：

- `v2-lite` 相对 baseline 的累计收益和超额收益仍明显更强
- 绝对收益增量与超额收益增量都是 `+0.119907`
- 波动继续高于 baseline，增量为 `+0.011538`
- 最大回撤继续优于 baseline，改善幅度为 `+0.003869`
- `win_rate` 低于 baseline，说明收益路径仍偏“少数强月份拉开差距”，而不是更高月度胜率

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

- 当前收益改善来自同一 `10000` 样本快照、同一基金池、同一固定市场 benchmark 口径
- 不存在样本扩大后两套方案口径不一致的问题
- 收益改善不是 benchmark 变化、样本变化或缺失处理差异造成的假提升

结论：

- 收益真实性：`通过`

### 4.2 风险解释充分性

观察结果：

- `annualized_volatility` 从 `0.087328` 上升到 `0.098866`
- `max_drawdown` 从 `-0.043211` 改善到 `-0.039342`
- `win_rate` 从 `0.405405` 下降到 `0.378378`
- `turnover_risk_flag = 1`
- `candidate_avg_new_entry_count = 3.428571`
- `excess_attribution_assessment = selection_dominant`
- `selection_driven_share = 1.0`
- `benchmark_driven_share = 0.0`

解释：

- 当前收益提升仍然不是 benchmark 驱动，而是 `selection-driven excess`
- 但这套候选依然伴随更高波动，且收益路径不如 baseline 平滑
- 稳健性产物仍给出 `turnover_risk_flag = 1`，说明“更高收益是否部分依赖更积极换手”仍未完全关掉
- 虽然回撤没有恶化，反而更好，但“更高波动 + 更高换仓风险”作为默认 baseline 是否可接受，仍需要业务判断

结论：

- 风险解释充分性：`存疑`

### 4.3 稳健性结构

稳健性摘要：

- `time_slice_consistency_flag = 1`
- `return_concentration_flag = 0`
- `turnover_risk_flag = 1`
- `factor_stability_flag = 1`
- `overall_assessment = keep_candidate`
- `top3_positive_excess_share = 0.394911`

候选补证摘要：

- `style_phase_assessment = broadly_distributed`
- `window_assessment = window_broad`
- `recommended_decision = ready_for_baseline_review`
- `excess_attribution_assessment = selection_dominant`
- `selection_driven_share = 1.0`
- `positive_window_ratio = 0.846154`
- `material_phase_win_count = 5 / 7`

解释：

- checklist 中更关键的硬门槛已经满足：
  - `selection_dominant = 是`
  - `window_concentrated = 否`
  - 不利 regime 明显失效 = 否
  - `return_concentration_flag = 0`
- `factor_stability_flag = 1` 仍提示部分因子跨阶段稳定性一般，但它在当前规则里属于参考项，不是一票否决
- `overall_assessment = keep_candidate` 也说明机器诊断仍偏保守，更适合支持“继续推进升级讨论”，而不是自动替代 baseline

结论：

- 稳健性结构：`通过`

### 4.4 逻辑可解释性

`v2-lite` 相对 baseline 的核心变化：

- 去掉了 `ret_6m`
- 去掉了 `manager_tenure_months`
- 去掉了 `vol_12m` / `max_drawdown_12m`
- 强化了 `excess_ret_12m`
- 引入了 `worst_3m_avg_return_12m`
- 用 `asset_stability_12m` 保留最小必要的稳定性约束

解释：

- 这套结构比 baseline 更聚焦，也比旧 `v2` 更少依赖短样本事件型因子
- 在当前固定市场 benchmark 口径下，因子逻辑与收益来源是一致的
- 但 `ret_12m` 与 `excess_ret_12m` 仍高度同向，结构虽干净，仍不是显著更丰富的新框架，而是更激进的聚焦版 baseline

结论：

- 逻辑可解释性：`通过`

## 5. 评分汇总

- 收益真实性：`通过`
- 风险解释充分性：`存疑`
- 稳健性结构：`通过`
- 逻辑可解释性：`通过`

按 [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md) 的决策规则：

- `3 个通过 + 1 个存疑`

对应 checklist 的机器化建议：

- `保留为主候选基线`

但本轮在补充执行风险说明后，团队已经明确接受该风险画像，因此进入人工升级决策。

## 6. 最终决策

决策结论：

- `tushare_scoring_v2_lite` 已升级为新的默认 baseline
- 默认 baseline 配置文件仍为 [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)，但其评分结构已与 `v2-lite` 对齐
- [`tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json) 保留为历史候选参考配置

更直白地说：

- checklist 的保守默认结论原本停在“保留主候选”
- 但在补充 [`v2_lite_execution_risk_note_2026-03-27.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_lite_execution_risk_note_2026-03-27.md) 后，最后剩余的风险接受度问题已被人工确认关闭

因此，本轮正式决策不再是“距离升级还差多远”，而是“升级条件已被接受并执行”。

## 7. 建议下一步

本轮已经完成的补充确认：

- 已形成 [`v2_lite_execution_risk_note_2026-03-27.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_lite_execution_risk_note_2026-03-27.md)
- 已确认“略高换手、略高波动，但更高收益、更好回撤”的画像可以接受

后续建议：

- 新的候选配置应开始与升级后的 [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json) 做比较
- 不再把旧 baseline 当作默认对照，只保留其历史评审与实验记录

## 8. 评审引用产物

- [`comparison_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/comparison_report.md)
- [`robustness_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/robustness_report.md)
- [`candidate_validation_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/candidate_validation/candidate_validation_report.md)
- [`dataset_snapshot.json`](/Users/liupeng/.codex/projects/fund_research_v2/data/raw/tushare/dataset_snapshot.json)
- [`experiment_registry.jsonl`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/experiments/experiment_registry.jsonl)
