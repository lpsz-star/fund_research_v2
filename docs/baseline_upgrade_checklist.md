# Baseline 升级决策清单

本文档只回答一个更窄的问题：

- 某个候选评分体系，是否适合从“候选配置”升级为新的默认 baseline

它不是因子研究方法文档，也不是回测报告模板。
它是团队在评审会上统一口径时使用的终审闸门。

## 1. 文档边界

本清单不负责定义：

- 因子如何研究
- 单因子如何评价
- 增量贡献如何测试
- 组合层如何验证

上述流程统一由 [`factor_research_framework.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_research_framework.md) 定义。

本清单只负责回答：

- 前置研究材料是否齐备
- 候选配置是否满足进入 baseline 升级评审的最低条件
- 评审结论应当如何落地记录

建议与以下文档配合阅读：

- [`factor_research_framework.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_research_framework.md)
- [`robustness_analysis.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)
- [`candidate_validation_spec.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)
- [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)

## 2. 使用场景

只有在下面这个场景下才使用本清单：

- 默认 baseline 已固定
- 某个候选评分配置已经完成完整实验
- 当前讨论的问题是“是否升级默认 baseline”

如果当前只是：

- 还在新增字段或修因子实现
- 还在调权重
- 还在做单因子初筛
- 还没做完候选配置对照实验

则不应直接进入 baseline 升级讨论。

## 3. 进入评审前的硬前提

若以下任一项不能明确，暂停升级讨论。

### 3.1 实验口径一致性

- 候选配置文件路径明确
- 当前 baseline 配置文件路径明确
- 两次实验使用同一数据快照口径
- benchmark 口径一致
- 基金池口径一致
- 信号与执行时点一致
- 成本口径一致
- 结果来源于标准实验命令，而不是手工改 CSV

### 3.2 研究材料完整性

候选配置要进入 baseline 升级评审，至少应具备以下材料：

- 字段可得性与时间边界审计已完成
- 单因子评价已完成
- 增量贡献测试已完成
- 主回测与实验对比已完成
- 稳健性分析已完成
- candidate validation 已完成

任何一个前置材料缺失，都不应进入正式 baseline 升级评审。

推荐先核对：

- `dataset_snapshot.json`
- `outputs/<data_source>/factor_research/field_availability_report.md`
- `outputs/<data_source>/factor_evaluation/factor_evaluation_report.md`
- `outputs/<data_source>/comparison/comparison_report.md`
- `outputs/<data_source>/robustness/robustness_summary.json`
- `outputs/<data_source>/candidate_validation/candidate_validation_summary.json`

## 4. 决策输出只能有三类

每次评审只允许输出以下三种结论之一：

### 4.1 升级为 baseline

含义：

- 候选配置已经具备足够完整、可复核、可解释的证据，可替代当前默认评分体系

### 4.2 保留为主候选基线

含义：

- 候选配置明显值得继续跟踪
- 但当前证据仍不足以替代默认 baseline

### 4.3 暂不保留

含义：

- 候选配置没有显示出足够清晰、可信、可复验的优势
- 不再作为主候选升级方向

## 5. 四道终审硬门槛

下面四项是升级 baseline 前最少要过的门槛。
四项里只要有一项明显不过，就不建议直接升级。

### 5.1 收益改进必须真实且可复现

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

### 5.2 风险与稳健性恶化必须可解释且可接受

不能只看累计收益，还必须同时看：

- 年化波动
- 最大回撤
- 月胜率
- 平均换手
- 平均新进数
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

### 5.3 研究证据链必须完整

这里看的是“为什么这个候选配置值得信”，而不只是“它涨得更多”。

至少要回答：

- 新增字段是否已经通过可得性审计，而不是停留在 `needs_audit`
- 引入的新因子是否完成单因子评价，并已明确角色
- 新因子是否完成 `add-one` / `replace-one`，证明相对 baseline 有边际贡献
- 候选配置是否已经完成组合层验证，而不是只停留在单因子表现

如果候选配置只是：

- 增加更多字段
- 堆更多权重
- 让结构更复杂
- 但没有补齐研究证据链

则不应轻易升级为默认 baseline。

### 5.4 评分逻辑必须更干净、更可审计

至少要回答：

- 它是否删除了已知偏弱、方向可疑或高度重复的旧因子
- 它是否避免让高相关因子重复加权
- 它的主排序因子、辅助修正因子、风险约束因子职责是否更清晰
- 它的评分结构是否比旧 baseline 更容易解释和复核

如果候选配置只是：

- 靠更多线性叠加获得表面收益改善
- 让主排序与风险约束混在一起
- 让结构更复杂但更难解释

则默认不应升级为 baseline。

## 6. 推荐打分表

评审时建议按下面四项给出结论：

- 收益真实性：`通过 / 存疑 / 不通过`
- 风险与稳健性：`通过 / 存疑 / 不通过`
- 研究证据链完整性：`通过 / 存疑 / 不通过`
- 逻辑与实现可审计性：`通过 / 存疑 / 不通过`

推荐决策规则：

- `4 个通过`：可讨论升级为 baseline
- `3 个通过 + 1 个存疑`：保留为主候选基线
- `存在 1 个不通过`：默认不升级
- `存在 2 个及以上存疑`：默认不升级

## 7. 评审会必须记录的内容

每次升级讨论都建议留下下面这份简短记录：

- 候选配置：
- 当前 baseline：
- 数据快照是否一致：
- 基金池 / benchmark / 信号执行时点 / 成本是否一致：
- 字段审计是否完成：
- 单因子评价是否完成：
- 增量贡献测试是否完成：
- 主回测与对照实验是否完成：
- 稳健性与 candidate validation 是否完成：
- 收益变化摘要：
- 风险变化摘要：
- 稳健性摘要：
- 评分逻辑变化摘要：
- 决策结论：
- 是否需要重跑更多验证：

## 8. 当前默认保守原则

在本项目里，若证据不足，默认选择：

- 保留旧 baseline
- 让候选配置继续作为主候选基线存在

而不是：

- 因为收益看起来更高，就立即替换默认 baseline

原因很简单：

- baseline 的职责是“稳定对照”
- 候选配置的职责才是“探索更优可能”

只要两者职责不混淆，研究迭代就更容易审计，也更不容易在多轮试验中失去可比性。
