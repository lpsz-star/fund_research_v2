# V2 最小验证规范（2026-03-24）

本文档用于冻结 [`tushare_scoring_v2`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json) 在 baseline 升级前的两项最小补充验证问题，仅定义验证目标与验收标准，不定义新的策略实现。

## 1. 背景与目标

根据 [`v2_baseline_review_2026-03-24.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_baseline_review_2026-03-24.md) 的结论，`v2` 目前处于“收益提升明确，但风险与稳健性仍需补证”的状态。  
本规范的目标是补齐两项解释性证据，支持下一轮是否升级 baseline 的判断。

## 2. 冻结问题

### 问题 A：风格/阶段集中性

`v2` 的超额表现是否主要集中在特定风格或市场阶段，而非广泛分布。

### 问题 B：风险来源归因

`v2` 的风险抬升是否主要由更高 beta 暴露解释，还是主要来自更强的基金选择（selection）能力。

## 3. 验收标准

### A. 风格/阶段视图验收

- 必须输出可复核的风格/阶段视图，能够明确判断 `v2` 的相对胜出是“广泛分布”还是“集中发生”。
- 输出必须支持对“集中性”作出明确结论，而不是仅给出单一总体统计。

### B. 归因视图验收

- 必须输出归因视图，将 `v2` 相对 baseline 的超额变化拆分为：
  - 与 benchmark 同向/暴露相关的部分（benchmark-driven excess）
  - 无法由 benchmark 暴露直接解释、归入选择效应的部分（selection-driven excess）
- 拆分结果必须可复核，且两部分定义不重叠。

### C. 可复现性验收

- 上述两个输出都必须能由标准 CLI 流程直接产出，不允许依赖手工脚本或 notebook 临时步骤。
- 在同一代码版本、同一数据快照、同一配置下，重复运行应得到一致结果。

## 4. 范围边界（防止 scope creep）

本规范不包含以下变更：

- 不新增因子定义
- 不新增或修改组合构建逻辑
- 不修改默认 benchmark 口径
- 不引入新的数据源

若后续实现需要触及以上任一项，应单独立项并先完成评审确认。
