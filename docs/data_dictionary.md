# 数据字典

本文档从字段层面对当前研究平台的核心数据表进行说明。
它和 [`data_contracts.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_contracts.md) 的区别是：

- `data_contracts.md` 更强调数据层级、主键、表职责
- 本文档更强调字段含义、单位、时间边界与缺失语义

## 1. 通用约定

### 1.1 时间字段

- `month`
  - 格式：`YYYY-MM`
  - 含义：月频研究索引
- `nav_date`
  - 格式：`YYYY-MM-DD`
  - 含义：净值所属日期
- `available_date`
  - 格式：`YYYY-MM-DD`
  - 含义：系统认为该条数据可被研究流程看到的日期
  - 当前用途：
    - 用于限制某个 `signal_month` 能看到哪些净值记录
    - 只有 `available_date <= signal_month` 月末的数据才能进入该月基金池与特征
- `ann_date`
  - 格式：`YYYYMMDD` 或空
  - 含义：上游接口中的公告日期

### 1.2 单位约定

- 收益率字段：小数表示
  - 例如 `0.05` 表示 `5%`
- 波动率字段：小数表示
- 回撤字段：小数表示，通常为负数
- 规模字段 `assets_cny_mn` / `latest_assets_cny_mn`
  - 单位：人民币百万元
  - 例如 `200.0` 表示 `2 亿元`

### 1.3 缺失值约定

- 代码中默认不把缺失值写成文本 `NA`
- 数值型字段在无法可靠计算时，通常会：
  - 在上游清洗时回退到可解释近似值
  - 或在窗口函数中返回 `0.0`
- 这类 `0.0` 不一定代表真实经济含义为零，可能代表当前版本的保守降级处理

## 2. `fund_entity_master.csv`

作用：

- 基金实体主表
- 作为基金池、特征、评分与报告的实体维表

字段说明：

- `entity_id`
  - 类型：字符串
  - 含义：基金实体唯一标识
  - 当前生成规则：`基金公司::去份额后基金名`
- `entity_name`
  - 类型：字符串
  - 含义：实体名称
  - 当前会去除常见 `A/C` 份额后缀
- `primary_type`
  - 类型：字符串
  - 含义：项目内部使用的粗分类
  - 当前值通常为：
    - `主动股票`
    - `偏股混合`
    - `其他`
- `fund_company`
  - 类型：字符串
  - 含义：基金管理人名称
- `fund_company_province`
  - 类型：字符串
  - 含义：基金公司所在省份
- `fund_company_city`
  - 类型：字符串
  - 含义：基金公司所在城市
- `fund_company_website`
  - 类型：字符串
  - 含义：基金公司官网
- `manager_name`
  - 类型：字符串
  - 含义：当前在任经理名称
  - 风险：
    - 当前只取一名经理，不保留联席经理完整结构
- `manager_start_month`
  - 类型：字符串
  - 格式：`YYYY-MM`
  - 含义：当前在任经理任职起始月
- `inception_month`
  - 类型：字符串
  - 格式：`YYYY-MM`
  - 含义：基金成立月
- `latest_assets_cny_mn`
  - 类型：浮点数
  - 单位：百万元人民币
  - 含义：最近一期实体级规模
  - 当前口径：
    - 同一实体下各份额规模求和
    - 若缺失净资产字段，则可能由 `fund_share × nav` 近似得到
- `status`
  - 类型：字符串
  - 含义：基金状态，如 `L`
- `custodian`
  - 类型：字符串
  - 含义：托管人
- `benchmark_text`
  - 类型：字符串
  - 含义：基金合同或产品定义中的业绩比较基准文本
  - 当前用途：
    - 仅保留原始描述，尚未驱动 benchmark 映射
- `invest_type`
  - 类型：字符串
  - 含义：上游接口中的投资类型描述
- `representative_share_class_id`
  - 类型：字符串
  - 含义：代表份额 ID
  - 当前用途：
    - 收益序列默认由代表份额承载

## 3. `fund_share_class_map.csv`

作用：

- 记录份额类到基金实体的映射

字段说明：

- `entity_id`
  - 含义：基金实体 ID
- `share_class_id`
  - 含义：上游份额代码，例如 `006864.OF`
- `share_class_name`
  - 含义：份额名称
- `is_primary_share_class`
  - 类型：`0/1`
  - 含义：是否为代表份额

## 4. `fund_nav_monthly.csv`

作用：

- 研究主流程消费的月频净值、收益与规模表

字段说明：

- `entity_id`
  - 含义：基金实体 ID
- `month`
  - 含义：该条月频记录所属月份
- `nav_date`
  - 含义：月内被选中的净值日期
  - 当前口径：
    - 取该月最后一条排序后的可用净值记录
- `available_date`
  - 含义：系统认为这条净值可被看到的日期
  - 当前口径：
    - 优先使用 `ann_date`
    - 若 `ann_date` 缺失，则回退到 `nav_date`
- `nav`
  - 类型：浮点数
  - 含义：用于收益路径的净值值
  - 当前优先级：
    - `adj_nav`
    - `unit_nav`
    - `accum_nav`
- `return_1m`
  - 类型：浮点数
  - 含义：月收益
  - 当前口径：
    - 同一实体月末净值 / 上月月末净值 - 1
- `assets_cny_mn`
  - 类型：浮点数
  - 单位：百万元人民币
  - 含义：该月实体级规模
  - 当前口径：
    - 同一实体下各份额该月规模求和
  - 风险：
    - 若上游缺少净资产字段，则会使用最近可得份额乘净值近似估算

## 5. `benchmark_monthly.csv`

作用：

- 保存月频 benchmark 收益序列

字段说明：

- `month`
  - 含义：月份索引
- `benchmark_return_1m`
  - 类型：浮点数
  - 含义：benchmark 当月收益
  - 在特征计算中的使用口径：
    - 只有 `available_date <= signal_month` 月末的 benchmark 月收益，才能进入该月 `excess_ret_12m`
- `benchmark_close`
  - 类型：浮点数或空
  - 含义：月末收盘点位
- `benchmark_trade_date`
  - 含义：用于代表该月的最后交易日
- `available_date`
  - 含义：benchmark 月收益在研究流程中可被看到的日期
  - 当前口径：
    - 优先使用显式字段
    - 若不存在，则回退到 `benchmark_trade_date`
    - 旧缓存缺失该字段时，再回退到该月月内默认日期
- `benchmark_name`
  - 含义：benchmark 名称
- `benchmark_ts_code`
  - 含义：benchmark 代码

## 6. `fund_universe_monthly.csv`

作用：

- 保存每只基金在每个月是否进入基金池，以及原因

字段说明：

- `entity_id`
  - 含义：基金实体 ID
- `month`
  - 含义：月份索引
- `is_eligible`
  - 类型：`0/1`
  - 含义：该月是否可投
- `reason_codes`
  - 类型：字符串
  - 含义：原因码，多个值使用 `|` 拼接
  - 当前可能值：
    - `eligible`
    - `primary_type_excluded`
    - `name_keyword_excluded`
    - `no_available_nav_for_month`
    - `insufficient_history`
    - `assets_below_threshold`
- `fund_company`
  - 含义：基金公司
- `visible_history_months`
  - 类型：整数
  - 含义：截至该信号月月末、真实可见的净值历史月数
- `fund_age_months`
  - 类型：整数
  - 含义：从基金成立月到当前月份的月数差
  - 当前用途：
    - 保留为审计字段
    - 当前默认基金池不再把它作为独立筛选门槛
- `visible_assets_cny_mn`
  - 类型：浮点数
  - 单位：百万元人民币
  - 含义：该信号月月末前可见的实体规模
  - 说明：
    - 这是基金池规模门槛真正使用的字段
    - 不等于实体主表里的 `latest_assets_cny_mn`
- `nav_available_date`
  - 类型：字符串或空
  - 含义：该月净值在研究流程中变得可见的日期
- `primary_type`
  - 含义：项目内部粗分类

## 7. `manager_assignment_monthly.csv`

作用：

- 把基金经理任职历史展开到月频时间轴
- 为 `manager_tenure_months` 提供“按月看当时是谁在管”的输入

字段说明：

- `entity_id`
  - 含义：基金实体 ID
- `month`
  - 含义：该条经理映射对应的研究月份
- `manager_name`
  - 类型：字符串
  - 含义：系统认定该月应使用的经理名称
  - 当前口径：
    - 优先取该月处于任职区间内的经理
    - 若同月多人在任，取 `begin_date` 最近者
- `manager_start_month`
  - 类型：字符串
  - 格式：`YYYY-MM`
  - 含义：该月所使用经理的任职起始月
- `manager_end_month`
  - 类型：字符串或空
  - 格式：`YYYY-MM`
  - 含义：该经理任期结束月
  - 缺失语义：
    - 空值通常表示当前仍在任，或上游未提供明确离任日期

## 8. `fund_feature_monthly.csv`

作用：

- 保存基金池通过后的月频特征结果

字段说明：

- `entity_id`
  - 含义：基金实体 ID
- `month`
  - 含义：信号月份
- `is_eligible`
  - 类型：`0/1`
  - 含义：该月是否在基金池内
- `manager_name`
  - 类型：字符串
  - 含义：该月特征所绑定的经理名称
  - 当前口径：
    - 优先取 `manager_assignment_monthly`
    - 若月度经理映射缺失，则回退到实体主表中的当前经理
- `ret_3m` / `ret_6m` / `ret_12m`
  - 类型：浮点数
  - 含义：滚动复利收益
  - 时间边界：
    - 只使用 `available_date <= signal_month` 月末的净值月收益
- `excess_ret_12m`
  - 类型：浮点数
  - 含义：相对 benchmark 的近 12 个月超额收益
  - 时间边界：
    - benchmark 也必须在信号月月末前可见
- `vol_12m` / `downside_vol_12m` / `max_drawdown_12m`
  - 类型：浮点数
  - 含义：滚动风险特征
- `manager_tenure_months`
  - 类型：整数
  - 含义：该月经理任期月数
  - 当前口径：
    - 优先使用该月经理映射的 `manager_start_month`
    - 若缺失或异常，回退到实体主表中的 `manager_start_month`
    - 若仍不可用，再回退到 `inception_month`
    - 若起始月晚于当前月，不返回负数，而是继续回退或截断为 `0`
- `asset_stability_12m`
  - 类型：浮点数
  - 含义：近 12 个月规模波动幅度

## 7. `fund_feature_monthly.csv`

作用：

- 保存基金实体的月频特征

字段说明：

- `entity_id`
- `month`
- `is_eligible`
- `entity_name`
- `fund_company`
- `primary_type`
- `ret_3m`
  - 近 3 个月复利累计收益
  - 只基于当月月末前已可见的历史净值记录
- `ret_6m`
  - 近 6 个月复利累计收益
  - 只基于当月月末前已可见的历史净值记录
- `ret_12m`
  - 近 12 个月复利累计收益
  - 只基于当月月末前已可见的历史净值记录
- `excess_ret_12m`
  - 近 12 个月相对 benchmark 的累计超额收益
- `vol_12m`
  - 近 12 个月月收益波动率
- `downside_vol_12m`
  - 近 12 个月负收益波动率
- `max_drawdown_12m`
  - 近 12 个月最大回撤
- `manager_tenure_months`
  - 当前月经理任期月数
- `asset_stability_12m`
  - 近 12 个月规模波动幅度
  - 只基于当月月末前已可见的历史规模记录

## 8. `fund_score_monthly.csv`

作用：

- 保存月度横截面评分结果

字段说明：

- `entity_id`
- `month`
- `performance_quality`
  - 收益质量因子分
- `risk_control`
  - 风险控制因子分
- `stability_quality`
  - 稳定性质量因子分
- `total_score`
  - 总分
- `rank`
  - 同月可投基金中的排序

## 9. `portfolio_target_monthly.csv`

作用：

- 保存最新一期组合建议

字段说明：

- `month`
- `entity_id`
- `entity_name`
- `fund_company`
- `rank`
- `total_score`
- `target_weight`
  - 目标权重

## 10. `backtest_monthly.csv`

作用：

- 保存历史回测逐月结果

字段说明：

- `signal_month`
  - 生成组合信号的月份
- `execution_month`
  - 实际持有收益归属的月份
- `portfolio_return_gross`
  - 扣成本前组合收益
- `portfolio_return_net`
  - 扣成本后组合收益
- `benchmark_return`
  - benchmark 同月收益
- `turnover`
  - 当月换手率
- `transaction_cost`
  - 当月交易成本
- `holdings`
  - 持仓数量

## 11. `dataset_snapshot.json`

作用：

- 保存当前数据快照元信息

字段说明：

- `source_name`
  - 数据源名称
- `generated_at`
  - 快照生成时间
- `entity_count`
  - 基金实体数量
- `share_class_count`
  - 份额类数量
- `month_range.start`
  - 数据起始月份
- `month_range.end`
  - 数据结束月份
- `field_status`
  - 字段来源与质量说明
- `benchmark_name`
- `benchmark_source`
- `benchmark_ts_code`
- `entity_asset_aggregation`
  - 当前实体规模汇总口径标识

## 12. `experiment_registry.jsonl`

作用：

- 记录每次完整实验的配置、数据快照和结果摘要

字段说明：

- `experiment_id`
  - 实验标识
- `generated_at`
  - 实验生成时间
- `config`
  - 本次实验的完整配置快照
- `dataset_snapshot`
  - 本次实验使用的数据快照元信息
- `git_commit`
  - 当前代码版本标识
  - 当前目录不是 git 仓库时为 `unknown`
- `portfolio_size`
  - 最新一期组合持仓数
- `backtest_summary`
  - 回测摘要指标
- `result_dir`
  - 本次实验结果目录
