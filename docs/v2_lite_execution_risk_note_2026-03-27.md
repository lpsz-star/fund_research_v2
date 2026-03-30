# `v2-lite` 执行约束与换手风险说明

本文档用于回答 `v2-lite` 相对旧 baseline，是否因为更高换手而不适合作为默认 baseline。

分析口径：

- 数据快照：`requested_max_funds = 10000`
- baseline：[`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
- candidate：[`tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json)
- 主要引用产物：
  - [`robustness_portfolio_behavior.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/robustness/robustness_portfolio_behavior.csv)
  - [`robustness_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/robustness/robustness_report.md)
  - [`v2_lite_baseline_review_2026-03-27.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_lite_baseline_review_2026-03-27.md)

## 1. 核心结论

- `v2-lite` 的换手风险确实高于旧 baseline，但幅度不大
- 它不是“靠明显更高换手硬换收益”的形态
- 当前 `turnover_risk_flag = 1` 更应理解为“存在增量换手，需要业务确认是否接受”，而不是“执行风险明显失控”

更直白地说：

- 团队已接受“略高换手、略低持仓延续性、但更高收益和更好回撤”的方案作为新的默认 baseline
- 因此，这项风险最终没有阻止 `v2-lite` 升级

## 2. 月度组合行为汇总

baseline 月度均值：

- `holdings_avg = 4.47619`
- `company_count_avg = 3.857143`
- `new_entry_count_avg = 3.333333`
- `dropped_count_avg = 3.047619`
- `weight_overlap_ratio_avg = 0.206349`
- `top1_weight_avg = 0.18254`
- `top3_weight_sum_avg = 0.490477`
- `top_company_weight_proxy_avg = 0.276191`

`v2-lite` 月度均值：

- `holdings_avg = 4.47619`
- `company_count_avg = 3.857143`
- `new_entry_count_avg = 3.428571`
- `dropped_count_avg = 3.142857`
- `weight_overlap_ratio_avg = 0.190476`
- `top1_weight_avg = 0.18254`
- `top3_weight_sum_avg = 0.490477`
- `top_company_weight_proxy_avg = 0.284127`

候选相对 baseline 的均值差异：

- `holdings_delta = 0.0`
- `company_count_delta = 0.0`
- `new_entry_count_delta = +0.095238`
- `dropped_count_delta = +0.095238`
- `weight_overlap_ratio_delta = -0.015873`
- `top1_weight_delta = 0.0`
- `top3_weight_sum_delta = 0.0`
- `top_company_weight_proxy_delta = +0.007937`

解释：

- 组合持仓数、公司分散度、前三大权重集中度几乎完全一致
- 风险差异主要不在“更集中”，而在“月度更替略快”
- `v2-lite` 的平均新增基金数只比 baseline 多约 `0.095`，并不是显著更高的调仓等级

## 3. 哪些月份差异更明显

月度差异主要集中在少数月份：

- `2025-01`：`new_entry_count +1`，`weight_overlap_ratio -0.166667`
- `2026-01`：`new_entry_count +2`，`weight_overlap_ratio -0.333334`
- `2026-02`：`new_entry_count +1`，`weight_overlap_ratio -0.166667`

其余大部分月份：

- baseline 与 `v2-lite` 的调仓行为一致，或差异极小

解释：

- `turnover_risk_flag = 1` 的主要来源，不是全时段持续显著高换手
- 更像是少数月份 `v2-lite` 更愿意做组合切换，尤其是在近期阶段更积极

## 4. 与收益表现合并看

在同一 `10000` 样本快照下：

- `v2-lite` 的 `excess_cumulative_return` 比 baseline 高 `+0.119907`
- `annualized_volatility` 高 `+0.011538`
- `max_drawdown` 反而改善 `+0.003869`
- `selection_driven_share = 1.0`
- `benchmark_driven_share = 0.0`

这意味着：

- 收益增厚不是 benchmark 暴露造成的
- 也没有表现为“更高换手换来更差回撤”
- 当前最准确的表述应是：
  - `v2-lite` 用略高的组合更替速度，换来了更强的 selection 收益`

## 5. 对 baseline 升级判断的含义

如果 baseline 的定义是：

- 稳定对照
- 可解释
- 不追求最低换手，只要求换手在可接受区间内

则当前执行风险证据已经足够支持 `v2-lite` 升级为默认 baseline。

如果 baseline 的定义是：

- 首要任务是低换手
- 首要任务是更高月度延续性
- 宁可少赚，也不愿让调仓更积极

这也是本项目原本保守默认值下最可能出现的反方理由：

- `并非收益真实性不足`
- `而是默认 baseline 的角色定义偏保守`

## 6. 最终判断

执行侧的客观结论：

- `v2-lite` 存在轻度更高换手风险
- 但未观察到显著更高集中度或显著失控的组合翻转
- 这项风险更接近“风格选择差异”，而不是“设计缺陷”

因此，这一项最终没有阻止升级。
它真正要求的是先明确默认 baseline 的业务角色，而这一步在本轮已经完成。
