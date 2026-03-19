# 时点边界审计

本文档用于回答一个具体问题：

- 当前研究主流程里，哪些字段可以用于解释历史月份
- 哪些字段只能用于解释“最新快照”

如果不显式区分这两类字段，就容易在阅读基金池、特征和报告时产生“事后看起来合理，但当时并不知道”的错觉。

## 1. 当前已收紧的链路

### 1.1 净值链路

- 数据表：
  - `fund_nav_monthly`
- 当前规则：
  - 只有 `available_date <= signal_month` 月末的净值记录，才能进入基金池和特征
- 当前状态：
  - 已接入主流程

### 1.2 benchmark 链路

- 数据表：
  - `benchmark_monthly`
- 当前规则：
  - `excess_ret_12m` 只使用信号月月末前已可见的 benchmark 月收益
- 当前状态：
  - 已接入特征层

### 1.3 经理任期链路

- 数据表：
  - `manager_assignment_monthly`
- 当前规则：
  - `manager_tenure_months` 优先按该月实际经理的 `manager_start_month` 计算
- 当前状态：
  - 已接入特征层

### 1.4 基金池规模链路

- 数据表：
  - `fund_universe_monthly`
- 当前规则：
  - 基金池规模门槛使用 `visible_assets_cny_mn`
  - 审计报告解释历史月份时也使用 `visible_assets_cny_mn`
- 当前状态：
  - 已接入基金池与报告层

## 2. 可以解释历史月份的字段

以下字段当前可以直接用于解释某个历史 `month`：

- `fund_universe_monthly.visible_assets_cny_mn`
- `fund_universe_monthly.visible_history_months`
- `fund_universe_monthly.fund_age_months`
- `fund_universe_monthly.nav_available_date`
- `fund_feature_monthly.manager_name`
- `fund_feature_monthly.manager_tenure_months`
- `fund_feature_monthly.ret_3m`
- `fund_feature_monthly.ret_6m`
- `fund_feature_monthly.ret_12m`
- `fund_feature_monthly.excess_ret_12m`
- `fund_feature_monthly.vol_12m`
- `fund_feature_monthly.downside_vol_12m`
- `fund_feature_monthly.max_drawdown_12m`
- `fund_feature_monthly.asset_stability_12m`
- `fund_score_monthly` 中全部评分字段

这些字段的共同特点是：

- 都有明确的 `month`
- 都是在该月研究时点下重新计算或重新判定

## 3. 只能解释最新快照的字段

以下字段更适合解释“基金当前长什么样”，不适合直接回头解释历史月份：

- `fund_entity_master.manager_name`
- `fund_entity_master.manager_start_month`
- `fund_entity_master.latest_assets_cny_mn`
- `fund_entity_master.status`
- `fund_entity_master.representative_share_class_id`

原因：

- 它们属于实体主表字段
- 主表默认承载的是当前快照，而不是每个月都重建一份实体画像

## 4. 当前仍存在的审计边界

### 4.1 `inception_month` 仍视为稳定静态字段

- 当前用途：
  - 计算基金年龄
  - 作为经理任期异常时的回退锚点
- 当前判断：
  - 这是相对稳定、可接受的静态字段

### 4.2 回测阶段仍按 next month 收益直接取数

- 当前规则：
  - `signal_month` 形成组合
  - `execution_month` 月收益评价结果
- 当前判断：
  - 这是设计上的 ex-post 评估，不属于前视问题
  - 但仍未覆盖暂停申赎、清盘退出等真实执行细节

### 4.3 实体主表仍未完全“月度画像化”

- 当前现状：
  - 我们已经把最关键的净值、经理、规模链路做成了逐月口径
  - 但 `fund_entity_master` 本身没有变成按月快照表
- 含义：
  - 这不是 bug
  - 但阅读报告时必须知道主表字段默认是“当前画像”

## 5. 当前建议

当前继续推进主线时，应优先遵循以下顺序：

1. 任何新筛选条件，先定义它的 `available_date` 或月度可见口径
2. 任何新报告字段，先判断它是在解释“历史月份”还是“当前快照”
3. 任何新因子，先写清它依赖的是逐月表还是静态主表

否则系统会再次回到“策略复杂了，但时间边界又变脏了”的状态。
