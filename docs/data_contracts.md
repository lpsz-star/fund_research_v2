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

## 2. 数据分层

### 2.1 `data/raw`

原始层或接近原始层的数据缓存。

当前包含：

- `fund_entity_master.csv`
- `fund_share_class_map.csv`
- `fund_nav_monthly.csv`
- `benchmark_monthly.csv`
- `dataset_snapshot.json`

### 2.2 `outputs/clean`

清洗后、可供研究链路直接使用的数据。

当前包含：

- 基金实体主表
- 份额映射表
- 月频净值表
- benchmark 月收益表
- 月频基金池表

### 2.3 `outputs/feature`

特征层：

- `fund_feature_monthly.csv`

### 2.4 `outputs/result`

结果层：

- `fund_score_monthly.csv`
- `portfolio_target_monthly.csv`
- `backtest_monthly.csv`
- `backtest_summary.json`

### 2.5 `outputs/experiments`

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
  当前基金主类型，例如 `主动股票`、`偏股混合`。
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
- `available_date` 当前与 `nav_date` 相同
- 后续如引入披露滞后，应优先调整 `available_date`

### 3.4 `benchmark_monthly`

月频 benchmark 收益表。

关键字段：

- `month`
- `benchmark_return_1m`

主键：

- `month`

### 3.5 `fund_universe_monthly`

每月基金池快照。

关键字段：

- `entity_id`
- `month`
- `is_eligible`
- `reason_codes`
- `fund_company`
- `primary_type`

主键：

- `entity_id + month`

说明：

- `reason_codes` 用于审计为何被剔除或保留
- 多个原因以 `|` 拼接

### 3.6 `fund_feature_monthly`

因子输入和中间特征。

关键字段：

- `entity_id`
- `month`
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

### 3.7 `fund_score_monthly`

月频打分结果。

关键字段：

- `entity_id`
- `month`
- `performance_quality`
- `risk_control`
- `stability_quality`
- `total_score`
- `rank`

主键：

- `entity_id + month`

### 3.8 `portfolio_target_monthly`

某次调仓生成的组合目标权重。

关键字段：

- `month`
- `entity_id`
- `entity_name`
- `fund_company`
- `rank`
- `total_score`
- `target_weight`

### 3.9 `backtest_monthly`

历史回测结果。

关键字段：

- `signal_month`
- `execution_month`
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

当前默认简化为：

- 月末生成信号
- 下一月获得收益

## 5. 当前代理字段说明

`AGENTS.md` 明确要求不能编造字段含义，因此当前需要明确标记代理字段：

在 `sample` 模式下：

- 多数值仅用于流程演示，不代表真实研究数据

在 `tushare` 模式下：

- `latest_assets_cny_mn` 当前仍是代理值
- `manager_name` 当前仍是占位值

后续如果这些字段进入真实评分前，必须先补全真实数据来源与可得性定义。

