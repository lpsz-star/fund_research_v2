# Baseline 升级决策清单

本文档用于回答一个更窄的问题：

- 某个候选评分体系，是否适合从“候选配置”升级为新的默认 baseline

它不是方法说明书，也不是回测报告模板。
它是团队在评审会上统一口径时使用的一页决策清单。

建议与以下文档配合阅读：

- [`robustness_analysis.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)
- [`candidate_validation_spec.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)
- [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)
- [`strategy_spec_v1.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/strategy_spec_v1.md)

## 1. 使用场景

只有在下面这个场景下才使用本清单：

- 默认 baseline 已固定
- 新候选评分配置已经完成完整实验
- 已完成实验对比
- 已完成稳健性分析
- 当前要讨论的是“是否升级默认 baseline”

如果当前只是：

- 还在加新因子
- 还在调权重
- 还没做完对照实验
- 还没做稳健性分析

则不应直接进入 baseline 升级讨论。

## 2. 决策输出只能有三类

每次评审只允许输出以下三种结论之一：

### 2.1 升级为 baseline

含义：

- 候选配置已经具备足够证据，可替代当前默认评分体系

### 2.2 保留为主候选基线

含义：

- 候选配置明显值得继续跟踪
- 但当前证据还不足以替代默认 baseline

### 2.3 暂不保留

含义：

- 候选配置没有显示出足够清晰、可信、可解释的优势
- 不再作为主候选升级方向

## 3. 决策前必须确认的前提

若以下任一项不能明确，暂停升级讨论：

- 候选配置文件路径明确
- 当前默认 baseline 配置文件路径明确
- 两次实验使用同一数据快照口径
- benchmark 口径一致
- 基金池口径一致
- 信号与执行时点一致
- 成本口径一致
- 结果来源于标准实验命令，而不是手工改 CSV

推荐先核对：

- `dataset_snapshot.json`
- `comparison_report.md`
- `robustness_summary.json`
- `candidate_validation_summary.json`
- `factor_evaluation.json`

## 4. 四道硬门槛

下面四项是升级 baseline 前最少要过的门槛。
四项里只要有一项明显不过，就不建议直接升级。

### 4.1 收益改进必须真实且可复现

至少要确认：

- 候选配置相对 baseline 的收益提升来自同一数据快照
- 提升不是由基金池变化、benchmark 变化或样本变化驱动
- 缺失收益、低置信月份、缺失权重没有恶化

最低要求：

- `entity_count_delta = 0`
- `eligible_count_delta = 0`
- `missing_month_count_delta = 0`
- `low_confidence_month_count_delta = 0`

若这些条件不成立，优先视为“新口径实验”，而不是 baseline 升级证据。

### 4.2 风险恶化必须可解释且可接受

不能只看累计收益，还必须同时看：

- 年化波动
- 最大回撤
- 平均换手
- 组合集中度
- 候选补证中的收益归因结果
- 候选补证中的不利 regime 表现

建议问题：

- 候选收益提升是否只是伴随显著更高波动
- 候选回撤是否明显恶化
- 候选是否通过更高换仓频率“买”到了收益
- 候选的风险抬升是否主要由更高 beta / benchmark 暴露解释
- 候选在不利 regime 下是否出现明显失效

经验判断：

- 如果收益提升明显，但波动和换仓同步明显抬升，且收益改善主要由 beta 驱动，则通常只能判为“保留为主候选基线”
- 如果波动有所抬升，但收益改善主要来自 selection，且候选在不利 regime 下没有明显失效，则仍可进入“升级为 baseline”讨论

### 4.3 稳健性结构必须站得住

至少检查：

- `selection_dominant`
- `window_concentrated`
- 不利 regime 是否明显失效
- `return_concentration_flag`
- `factor_stability_flag`

当前建议门槛分成“硬门槛”和“参考项”。

硬门槛：

- `selection_dominant = 是`
- `window_concentrated = 否`
- 不利 regime 明显失效 = 否
- `return_concentration_flag = 0`

参考项：

- `time_slice_consistency_flag`
- `turnover_risk_flag`
- `factor_stability_flag`
- `overall_assessment`

说明：

- 旧的 `time_slice_consistency_flag` 与 `overall_assessment` 仍然有参考价值，但不再作为一票否决 gate。
- 若候选已经完成 A/B 补证，并能证明“selection 主导 + 非单窗口集中 + 不利 regime 不明显失效”，则即便旧的自然年切片 gate 未通过，也可进入人工升级讨论。

### 4.4 评分逻辑必须比旧 baseline 更干净

这里看的是“为什么这个候选配置更值得信”，而不只是“它涨得更多”。

至少要回答：

- 它是否删除了已知偏弱或方向可疑的旧因子
- 它引入的新因子是否已有基本单因子证据
- 它的评分结构是否比旧 baseline 更容易解释

如果候选配置只是：

- 增加更多字段
- 堆更多权重
- 让结构更复杂
- 但没有显著提升可解释性

则不应轻易升级为默认 baseline。

## 5. 推荐打分表

评审时建议按下面四项给出结论：

- 收益真实性：`通过 / 存疑 / 不通过`
- 风险解释充分性：`通过 / 存疑 / 不通过`
- 稳健性结构：`通过 / 存疑 / 不通过`
- 逻辑可解释性：`通过 / 存疑 / 不通过`

推荐决策规则：

- `4 个通过`：可讨论升级为 baseline
- `3 个通过 + 1 个存疑`：保留为主候选基线
- `存在 1 个不通过`：默认不升级
- `存在 2 个及以上存疑`：默认不升级

## 6. 评审会必须记录的内容

每次升级讨论都建议留下下面这份简短记录：

- 候选配置：
- 当前 baseline：
- 数据快照是否一致：
- 基金池/benchmark/成本是否一致：
- 收益变化摘要：
- 风险变化摘要：
- 稳健性摘要：
- 因子逻辑变化摘要：
- 决策结论：
- 是否需要重跑更多验证：

## 7. 当前默认保守原则

在本项目里，若证据不足，默认选择：

- 保留旧 baseline
- 让候选配置继续作为主候选基线存在

而不是：

- 因为收益看起来更高，就立即替换默认 baseline

原因很简单：

- baseline 的职责是“稳定对照”
- 候选配置的职责才是“探索更优可能”

只要两者职责不混淆，研究迭代就更容易审计，也更不容易在多轮试验中失去可比性。
