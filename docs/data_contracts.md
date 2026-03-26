# 数据契约说明

## 1. 设计原则

本项目的数据契约遵循以下原则：

- 原始层与清洗层分离
- 每个数据集尽量有明确主键和时间字段
- 不能混淆“发生时间”和“可获得时间”
- 份额类与基金实体分离
- 输出结果不反向驱动源码逻辑

### 1.1 tushare 基金场景常用接口在线文档链接：
基金列表：https://tushare.pro/document/2?doc_id=19
基金管理人：https://tushare.pro/document/2?doc_id=118
基金经理：https://tushare.pro/document/2?doc_id=208
基金规模数据：https://tushare.pro/document/2?doc_id=207
基金净值：https://tushare.pro/document/2?doc_id=119
基金分红：https://tushare.pro/document/2?doc_id=120
基金持仓：https://tushare.pro/document/2?doc_id=121
指数基本信息：https://tushare.pro/document/2?doc_id=94
指数日线行情：https://tushare.pro/document/2?doc_id=95

## 2. 数据分层

### 2.1 `data/raw/<data_source>`

原始层或接近原始层的数据缓存。

当前包含：

- `fund_entity_master.csv`
- `fund_share_class_map.csv`
- `fund_nav_monthly.csv`
- `benchmark_monthly.csv`
- `manager_assignment_monthly.csv`
- `fund_type_audit.csv`
- `fund_liquidity_audit.csv`
- `dropped_entities.csv`
- `dataset_snapshot.json`

### 2.2 `outputs/<data_source>/clean`

清洗后、可供研究链路直接使用的数据。

当前包含：

- 基金实体主表
- 份额映射表
- 月频净值表
- benchmark 月收益表
- 月频经理映射表
- 基金流动性审计表
- 月频基金池表

### 2.3 `outputs/<data_source>/feature`

特征层：

- `fund_feature_monthly.csv`

### 2.4 `outputs/<data_source>/result`

结果层：

- `fund_score_monthly.csv`
- `portfolio_target_monthly.csv`
- `backtest_monthly.csv`
- `backtest_summary.json`

### 2.5 `outputs/<data_source>/experiments`

实验追踪层：

- `experiment_registry.jsonl`

## 3. 主要表定义

### 3.1 `fund_entity_master`

基金实体主表。

关键字段：

- `entity_id`
  基金实体 ID。用于聚合同一基金的不同份额。
- `entity_name`
  基金实体名称，默认去除 A/C 后缀。
- `primary_type`
  当前基金主类型，例如 `主动股票`、`偏股混合`、`灵活配置混合`。
- `fund_company`
  基金公司。
- `manager_name`
  当前经理名称。
- `inception_month`
  成立月份，格式 `YYYY-MM`。
- `latest_assets_cny_mn`
  最近可得规模，单位百万元人民币。
- `status`
  当前状态。

主键：

- `entity_id`

### 3.2 `fund_share_class_map`

份额类与基金实体映射表。

关键字段：

- `entity_id`
- `share_class_id`
- `share_class_name`
- `is_primary_share_class`

主键：

- `entity_id + share_class_id`

当前含义：

- 同一基金实体的 A/C 份额不作为独立 alpha 来源
- `is_primary_share_class=1` 的份额用于表示默认代表份额

### 3.3 `fund_nav_monthly`

月频净值与收益表。

关键字段：

- `entity_id`
- `month`
- `nav_date`
  净值所属月份的观测日期
- `available_date`
  数据可获得日期
- `nav`
- `return_1m`
- `assets_cny_mn`

主键：

- `entity_id + month`

当前默认口径：

- `signal_date` 由 `month` 所代表的月末近似表达
- 正式研究只把 `as_of_date` 之前最后一个完整结束的自然月视为“最新有效 `month`”
- `available_date` 当前与 `nav_date` 相同
- 后续如引入披露滞后，应优先调整 `available_date`

### 3.4 `benchmark_monthly`

月频 benchmark 收益表。

关键字段：

- `month`
- `benchmark_key`
- `benchmark_name`
- `benchmark_ts_code`
- `benchmark_return_1m`

主键：

- `benchmark_key + month`

说明：

- 当前允许同一研究快照同时保存多条 benchmark 序列。
- `benchmark_key` 是项目内部使用的稳定标识，例如 `broad_equity`、`large_cap_equity`。
- 基金类型到 benchmark 的映射当前主要用于特征层构造超额收益类因子。
- 回测主口径固定使用 `benchmark.default_key` 对应的市场 benchmark，不再按组合持仓动态混合 benchmark。
- 若存在 `available_date`，则特征层构造 `excess_ret_12m` 时只能使用信号月月末前已可见的 benchmark 月收益。

### 3.5 `manager_assignment_monthly`

月频经理映射表。

关键字段：

- `entity_id`
- `month`
- `manager_name`
- `manager_start_month`
- `manager_end_month`

主键：

- `entity_id + month`

当前默认口径：

- 尝试把 `fund_manager` 的任职区间映射到基金实体的月频净值时间轴。
- 若同月存在多名在任经理，当前默认取 `begin_date` 最近的一位，目的是让任期口径更接近“当月主要管理责任人”。
- 若某月没有严格匹配到在任区间，则允许回退到“该月之前最近开始任职”的经理，避免历史接口缺口把任期字段全部打成缺失。

### 3.6 `fund_universe_monthly`

每月基金池快照。

关键字段：

- `entity_id`
- `month`
- `is_eligible`
- `reason_codes`
- `fund_company`
- `primary_type`
- `visible_history_months`
- `fund_age_months`
- `visible_assets_cny_mn`
- `nav_available_date`

主键：

- `entity_id + month`

说明：

- `reason_codes` 用于审计为何被剔除或保留
- 多个原因以 `|` 拼接
- `visible_assets_cny_mn` 是基金池规模门槛实际使用的当月可见规模
- 审计报告解释历史月份时，应优先使用该字段，而不是 `fund_entity_master.latest_assets_cny_mn`
- `fund_age_months` 当前保留为审计字段，不再作为默认基金池独立筛选条件
- 若基金实体在 clean 层被识别为最低持有期产品，则会在基金池原因码中体现 `holding_period_restricted`

### 3.7 `fund_liquidity_audit`

基金流动性审计表。

关键字段：

- `entity_id`
- `entity_name`
- `share_class_id`
- `fund_name`
- `liquidity_restricted`
- `holding_lock_months`
- `rule_code`
- `confidence`
- `reason`

主键：

- `entity_id`

说明：

- 当前第一版流动性识别基于基金名称中的最低持有期关键词。
- 本项目当前策略重视月频调仓流动性，因此识别为 `liquidity_restricted=1` 的基金会被基金池直接排除。

### 3.7 `fund_type_audit`

基金类型标准化审计表。

关键字段：

- `entity_id`
- `entity_name`
- `share_class_id`
- `fund_name`
- `raw_fund_type`
- `raw_invest_type`
- `benchmark_text`
- `primary_type`
- `rule_code`
- `confidence`
- `reason`

主键：

- `entity_id`

说明：

- 这张表不负责决定基金池去留，而是回答“这只基金为什么被分到这个类型”。
- `primary_type` 是当前研究流程消费的标准类型。
- `rule_code` 和 `reason` 用于解释具体命中的规则。
- `confidence` 用于标记低置信度或 fallback 分类，方便后续人工抽查与规则迭代。

### 3.8 `fund_feature_monthly`

因子输入和中间特征。

关键字段：

- `entity_id`
- `month`
- `official_research_month`
- `research_month_status`
- `is_eligible`
- `ret_3m`
- `ret_6m`
- `ret_12m`
- `excess_ret_12m`
- `vol_12m`
- `downside_vol_12m`
- `max_drawdown_12m`
- `manager_tenure_months`
- `asset_stability_12m`

主键：

- `entity_id + month`

说明：

- `manager_tenure_months` 优先使用 `manager_assignment_monthly` 中该月真实匹配到的 `manager_start_month` 计算。
- 只有当月度经理映射缺失时，才回退到 `fund_entity_master.manager_start_month`。
- `official_research_month = 1` 表示该行属于当前 `as_of_date` 下的正式最新研究月。
- `research_month_status = official / observation_only` 用于区分正式月与月内观察月。

### 3.8 `fund_score_monthly`

月频打分结果。

关键字段：

- `entity_id`
- `month`
- `official_research_month`
- `research_month_status`
- `performance_quality`
- `risk_control`
- `stability_quality`
- `total_score`
- `rank`

主键：

- `entity_id + month`

### 3.9 `portfolio_target_monthly`

某次调仓生成的组合目标权重。

关键字段：

- `month`
- `entity_id`
- `entity_name`
- `fund_company`
- `rank`
- `total_score`
- `target_weight`

### 3.10 `backtest_monthly`

历史回测结果。

关键字段：

- `signal_month`
- `execution_month`
- `execution_request_date_proxy`
- `execution_effective_date_proxy`
- `portfolio_return_gross`
- `portfolio_return_net`
- `benchmark_return`
- `turnover`
- `transaction_cost`
- `holdings`

## 4. 时间字段约定

本项目当前统一采用以下时间语义：

- `month`
  月频研究索引，格式 `YYYY-MM`
- `nav_date`
  净值所属日期
- `available_date`
  数据真实可获得日期
- `signal_month`
  生成信号的月份
- `execution_month`
  组合执行对应的下一月份
- `execution_request_date_proxy`
  在月频研究框架下，代理“提交申购请求”的日期；当前统一取 `execution_month` 月初
- `execution_effective_date_proxy`
  在月频研究框架下，代理“组合开始承担收益”的日期；当前与 `execution_request_date_proxy` 相同

当前默认简化为：

- 月末生成信号
- 正式最新信号月取 `as_of_date` 之前最后一个完整月
- 次月月初按代理申购口径开始承担收益
- 下一月获得收益

## 5. 当前代理字段说明

`AGENTS.md` 明确要求不能编造字段含义，因此当前需要明确标记代理字段：

在 `sample` 模式下：

- 多数值仅用于流程演示，不代表真实研究数据

在 `tushare` 模式下：

- `latest_assets_cny_mn` 当前仍是代理值
- `manager_name` 当前仍是占位值

后续如果这些字段进入真实评分前，必须先补全真实数据来源与可得性定义。
