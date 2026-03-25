# `tushare_scoring_v2` Baseline 升级评审记录

本文档用于记录 2026-03-24 对 [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json) 的 baseline 升级评审结论。

评审口径依据：

- [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md)
- [`robustness_analysis.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)

## 1. 评审对象

- 候选配置：
  - [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)
- 当前 baseline：
  - [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
- 数据源：
  - `tushare`
- 评审日期：
  - `2026-03-24`

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

- 默认 baseline 实验记录生成时间：`2026-03-23T10:59:25Z`
- `v2` 实验记录生成时间：`2026-03-23T12:12:38Z`
- 两者使用的 `dataset_snapshot.generated_at` 都是 `2026-03-21T14:59:34Z`

结论：

- 本次评审满足“同口径升级讨论”的前提条件

## 3. 收益变化摘要

默认 baseline 回测摘要：

- `cumulative_return = 0.235298`
- `annualized_return = 0.070937`
- `annualized_volatility = 0.065674`
- `max_drawdown = -0.072212`
- `excess_cumulative_return = 0.113753`

`v2` 回测摘要：

- `cumulative_return = 0.36985`
- `annualized_return = 0.107456`
- `annualized_volatility = 0.101006`
- `max_drawdown = -0.073463`
- `excess_cumulative_return = 0.250285`

直接观察：

- 累计收益显著提升
- 年化收益显著提升
- 超额累计收益大幅提升
- 最大回撤仅小幅变差
- 波动明显抬升

## 4. 四道门槛逐项评审

### 4.1 收益真实性

核对结果：

- `entity_count_delta = 0`
- `eligible_count_delta = 0`
- `missing_month_count_delta = 0`
- `low_confidence_month_count_delta = 0`
- `max_missing_weight_delta = 0`

判断：

- 收益改善来自同一数据快照、同一基金池和同一回测边界
- 当前没有证据表明 `v2` 的提升来自样本变化或数据缺失处理差异

结论：

- 收益真实性：`通过`

### 4.2 风险可接受性

观察结果：

- `annualized_volatility` 从 `0.065674` 上升到 `0.101006`
- `max_drawdown` 从 `-0.072212` 变为 `-0.073463`
- `win_rate` 保持 `0.324324`
- 稳健性摘要里 `turnover_risk_flag = 0`

解释：

- `v2` 并不是“同风险下纯增厚收益”
- 它更像是“收益显著更强，但同时承受更高波动”
- 回撤没有明显恶化，但波动增幅已经足够大，不能视作轻微代价

结论：

- 风险可接受性：`存疑`

### 4.3 稳健性诊断

稳健性摘要：

- `time_slice_consistency_flag = 0`
- `return_concentration_flag = 0`
- `turnover_risk_flag = 0`
- `factor_stability_flag = 1`
- `overall_assessment = needs_more_validation`

解释：

- `v2` 没有表现出“收益主要依赖最好的 3 个月”
- `v2` 也没有显示更高的组合换仓红旗
- 但它没有通过当前按年度切片的一致性门槛
- 当前系统给出的总判断仍是 `needs_more_validation`

按项目现行规则：

- 只要 `overall_assessment` 仍是 `needs_more_validation`，默认就不应直接升级 baseline

结论：

- 稳健性诊断：`存疑`

### 4.4 逻辑可解释性

`v2` 相对默认 baseline 的核心变化是：

- 去掉了弱证据的 `ret_6m`
- 去掉了方向可疑的 `manager_tenure_months`
- 去掉了更容易与总收益重复暴露的 `vol_12m` / `max_drawdown_12m`
- 强化了 `excess_ret_12m`
- 引入了 `worst_3m_avg_return_12m`
- 保留了 `asset_stability_12m`
- 保留了事件型但样本偏少的 `manager_post_change_excess_delta_12m`

当前单因子证据里：

- `excess_ret_12m`、`ret_12m`、`downside_vol_12m`、`worst_3m_avg_return_12m` 都处于较强组
- `manager_tenure_months` 为负向，且 `direction_ok = 0`
- `ret_6m` 明显偏弱
- `manager_post_change_excess_delta_12m` 方向正常，但只有 `10` 个评估月份

解释：

- 从因子质量和可解释性看，`v2` 比旧 baseline 更干净
- 但它仍保留了一个样本偏短的事件因子，因此“完全定型”还差一步

结论：

- 逻辑可解释性：`通过`

## 5. 评分汇总

- 收益真实性：`通过`
- 风险可接受性：`存疑`
- 稳健性诊断：`存疑`
- 逻辑可解释性：`通过`

按 [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md) 的决策规则：

- `2 个通过 + 2 个存疑`

对应结论：

- 不直接升级 baseline

## 6. 最终决策

决策结论：

- `tushare_scoring_v2` 暂不升级为新的默认 baseline
- `tushare_scoring_v2` 保留为当前主候选基线

原因概括：

- 它的收益提升是真实的
- 它的评分逻辑比旧 baseline 更干净
- 但当前风险抬升明显
- 且稳健性摘要仍给出 `needs_more_validation`

因此更合适的定位是：

- 继续作为主候选方案跟踪
- 暂不替换当前默认 baseline

## 7. 后续建议

下一轮验证建议优先回答两个问题：

1. `v2` 的收益提升是否主要集中在少数风格阶段，而不是仅按自然年切片偶然成立。
2. `v2` 的风险抬升是否主要来自更高 beta 暴露，还是来自更有效的主动选基。

在这两点没有被进一步解释清楚之前，不建议把 [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json) 直接替换为 [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)。

## 8. Next Validation Path

下一步最小验证路径已冻结在 [`v2_validation_spec.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_validation_spec.md)：

- 先完成“风格/阶段集中性”验证，确认 `v2` 胜出是广泛分布还是阶段集中。
- 再完成“beta vs selection”归因验证，区分 benchmark 驱动与选基驱动的超额来源。
- 两项输出均需通过标准 CLI 流程复现后，再进入下一轮 baseline 升级评审。
