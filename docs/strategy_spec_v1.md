# 策略规格说明 v1

本文档只回答一个问题：

- 当前仓库默认在跑的，到底是哪一版策略

它的职责是“策略总纲”，不是字段手册、时间边界细则或实验操作手册。
因此本文件只保留版本声明和核心策略定义，所有实现细节都跳转到专门文档。

## 1. 当前策略版本定位

当前默认版本可概括为：

- 资产范围：中国市场场外公募主动权益基金
- 频率：月频
- 研究目标：在主动权益基金池中做可审计、可复现的横截面选基
- 当前定位：研究策略，不是实盘执行系统

这意味着：

- 它适合做策略筛选、因子试验和实验对比
- 不应直接被理解成“已具备真实申购执行能力的赚钱系统”

## 2. 基金池定义

当前默认纳入：

- `主动股票`
- `偏股混合`
- `灵活配置混合`

当前默认排除：

- ETF / 联接 / 指数 / LOF / FOF / QDII
- 名称中明显带债、货币特征的基金
- 名称中明显带最低持有期特征的基金

当前主线基金池更强调：

- 可见历史长度
- 可见规模门槛
- 流动性可接受

详细规则请看：

- [`data_contracts.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_contracts.md)
- [`data_dictionary.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_dictionary.md)

## 3. 信号与执行定义

当前默认研究口径：

- 信号基于最后一个完整自然月月末形成
- 组合在下一月按月频代理执行口径生效
- 回测当前仍属于研究近似，不代表真实场外基金申购确认回测

详细时间边界与执行解释请看：

- [`backtest_conventions.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/backtest_conventions.md)

## 4. 评分体系定义

当前评分结构固定为三大类：

1. `performance_quality`
2. `risk_control`
3. `stability_quality`

当前仓库同时保留两类配置角色：

- 默认基线配置：
  - [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
- 候选优化配置：
  - [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/archive/factor_research/tushare_scoring_v2.json)
  - [`tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/archive/factor_research/tushare_scoring_v2_lite.json)
  - [`tushare_scoring_v3.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/archive/factor_research/tushare_scoring_v3.json)

当前原则是：

- 新因子先进入观察层
- 因子评价通过后，再通过新配置进入候选评分体系
- 默认 baseline 可以在正式评审后升级

当前默认 baseline 已采用与 `v2-lite` 一致的评分结构：

- `performance_quality`：`excess_ret_12m(0.7)` + `ret_12m(0.3)`
- `risk_control`：`downside_vol_12m(0.55)` + `worst_3m_avg_return_12m(0.45)`
- `stability_quality`：`asset_stability_12m(1.0)`

具体因子、类内权重和事件因子缺失处理请看：

- [`factor_catalog.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_catalog.md)

## 5. 组合构建定义

当前默认组合方法：

- 基于正式最新研究月评分结果
- 按总分排序选前 `N`
- 等权
- 控制单基金权重上限
- 控制单公司入选数量上限

当前不是优化器策略，不做：

- 均值方差优化
- 风险平价
- Black-Litterman

组合与回测细则请看：

- [`backtest_conventions.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/backtest_conventions.md)
- [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)

## 6. Benchmark 定义

当前 benchmark 已不是单一序列，而是：

- 按基金类型映射到不同指数
- 特征层按基金类型映射使用对应 benchmark
- 主回测固定使用 `benchmark.default_key` 对应的市场 benchmark

这意味着：

- `excess_ret_12m` 等超额收益类因子，仍可按 `primary_type` 读取对应 benchmark
- 但回测评估阶段不再按组合持仓动态混合 benchmark
- 当前默认主回测 benchmark 为 `benchmark.default_key = broad_equity = 中证800`

详细口径请看：

- [`factor_catalog.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_catalog.md)
- [`backtest_conventions.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/backtest_conventions.md)

## 7. 当前版本不覆盖什么

当前版本尚未覆盖：

- 真实场外基金申购确认建模
- 暂停申购 / 赎回约束
- 大额申购限制
- 更完整的实盘风控与交易编排
- 复杂组合优化

这些不属于“文档漏写”，而是当前版本明确还没做。

## 8. 什么时候说明策略版本变了

以下任一项变化，都应视为策略版本变化：

- 基金池纳入/剔除规则变化
- 信号与执行口径变化
- 正式评分体系变化
- benchmark 体系变化
- 组合构建规则变化
- 成本模型变化

一旦发生这些变化，应：

- 新建实验配置
- 保留旧 baseline
- 用实验对比产物解释变化来源

对应说明请看：

- [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)
- [`changes.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/changes.md)
