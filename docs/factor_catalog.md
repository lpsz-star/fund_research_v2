# 因子目录

本文档只回答两个问题：

- 每个因子在金融上是什么意思
- 每个评分体系对应的因子和权重

本文档以当前代码真实实现为准，主要对应以下位置：

- 特征构建：[feature_builder.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/features/feature_builder.py)
- 评分方向与横截面打分：[scoring_engine.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/ranking/scoring_engine.py)
- 默认评分体系回退配置：[config.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/config.py)
- 实验配置：
  - [`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
  - [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)
  - [`tushare_scoring_v3.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v3.json)

## 1. 当前口径

- 资产范围：中国市场场外公募主动权益基金。
- 当前基金类型：`主动股票`、`偏股混合`、`灵活配置混合`。
- 频率：月频。
- 时间边界：所有特征都只使用“截至当月末已可见”的历史数据，不使用未来月份信息。
- 评分方法：同月横截面分位打分，再按权重合成三大类分数和总分。
- 评分方向：
  - `high` 表示数值越大越好。
  - `low` 表示数值越小越好。
- 缺失值处理：
  - 评分时，单字段若缺失，会给该基金该字段中性分 `0.5`。
  - 这主要是为了避免事件类因子因为“没有事件”而被机械奖惩。

## 2. 因子字典

下面只列当前代码中真实产出的、并且已经被评分系统使用或进入观察层的字段。

### 2.1 收益与超额类

#### `ret_3m`

- 含义：截至当前月的近 `3` 个月复利累计收益。
- 计算方式：对近 `3` 个月 `return_1m` 做复利连乘。
- 金融语义：短期动量，反映最近一个季度表现是否强。
- 评分方向：`high`
- 当前状态：已实现；当前三个评分体系都未使用。

#### `ret_6m`

- 含义：截至当前月的近 `6` 个月复利累计收益。
- 计算方式：对近 `6` 个月 `return_1m` 做复利连乘。
- 金融语义：中短期趋势，比 `ret_3m` 更平滑。
- 评分方向：`high`
- 当前状态：基线评分体系使用。

#### `ret_12m`

- 含义：截至当前月的近 `12` 个月复利累计收益。
- 计算方式：对近 `12` 个月 `return_1m` 做复利连乘。
- 金融语义：过去一年总收益，是最基础的历史表现刻画。
- 评分方向：`high`
- 当前状态：基线、`v2`、`v3` 都使用。

#### `excess_ret_3m`

- 含义：截至当前月的近 `3` 个月累计超额收益。
- 计算方式：`ret_3m - benchmark_3m_return`。
- 金融语义：回答“最近一个季度是否跑赢对应 benchmark”。
- 评分方向：`high`
- 当前状态：已实现；当前三个评分体系都未使用。

#### `excess_ret_6m`

- 含义：截至当前月的近 `6` 个月累计超额收益。
- 计算方式：`ret_6m - benchmark_6m_return`。
- 金融语义：回答“最近半年是否跑赢对应 benchmark”。
- 评分方向：`high`
- 当前状态：已实现；当前三个评分体系都未使用。

#### `excess_ret_12m`

- 含义：截至当前月的近 `12` 个月累计超额收益。
- 计算方式：
  - `ret_12m - benchmark_12m_return`
  - 这里的 benchmark 指特征层 benchmark，按 `primary_type` 映射：
    - `主动股票 -> 中证800`
    - `偏股混合 -> 中证800`
    - `灵活配置混合 -> 中证800`
- 说明：
  - 上述映射用于构造超额收益类因子
  - 不应直接等同于主回测 benchmark；主回测当前固定使用 `benchmark.default_key`
- 金融语义：把“市场整体上涨”与“基金主动跑赢市场”区分开。
- 评分方向：`high`
- 当前状态：基线、`v2`、`v3` 都使用。

#### `excess_consistency_12m`

- 含义：不同收益窗口下超额是否同时成立的一致性指标。
- 计算方式：基于 `excess_ret_3m`、`excess_ret_6m`、`excess_ret_12m` 聚合而成。
- 金融语义：不只看超额幅度，还看超额是否跨窗口持续存在。
- 评分方向：`high`
- 当前状态：已实现；当前三个评分体系都未使用。

#### `excess_hit_rate_12m`

- 含义：近 `12` 个月中，基金月收益跑赢特征层对应 benchmark 的月份占比。
- 计算方式：逐月比较 `fund_return_1m > benchmark_return_1m` 后求占比。
- 金融语义：衡量超额是否经常发生，而不是只在少数月份集中兑现。
- 评分方向：`high`
- 当前状态：观察层；`v3` 使用。

#### `excess_streak_6m`

- 含义：近 `6` 个月内最长连续跑赢特征层对应 benchmark 的月数。
- 计算方式：对逐月超额收益序列统计最长连续 `excess_return > 0` 段。
- 金融语义：衡量超额的连续性和趋势延续性。
- 评分方向：`high`
- 当前状态：观察层；当前三个正式评分体系都未使用。

### 2.2 风险与收益路径类

#### `vol_12m`

- 含义：截至当前月的近 `12` 个月月收益波动率。
- 计算方式：对近 `12` 个月月收益计算总体标准差。
- 金融语义：衡量收益路径整体波动程度。
- 评分方向：`low`
- 当前状态：基线评分体系使用。

#### `downside_vol_12m`

- 含义：截至当前月的近 `12` 个月下行波动率。
- 计算方式：只保留负收益月份，对其平方均值开根号；若无负收益则记 `0.0`。
- 金融语义：关注亏损月份的波动强度，比总波动更接近持有人的痛感。
- 评分方向：`low`
- 当前状态：基线、`v2`、`v3` 都使用。

#### `max_drawdown_12m`

- 含义：截至当前月的近 `12` 个月最大回撤。
- 计算方式：基于近 `12` 个月净值路径计算历史峰值到后续低点的最大跌幅。
- 金融语义：衡量最差历史回撤体验。
- 评分方向：`high`
- 说明：这里数值通常为负，越接近 `0` 越好；代码按 `high` 方向处理。
- 当前状态：基线评分体系使用。

#### `drawdown_recovery_ratio_12m`

- 含义：近 `12` 个月回撤后的恢复程度。
- 计算方式：基于净值路径的回撤与后续修复关系计算。
- 金融语义：不是只看跌得多深，还看跌后恢复得快不快。
- 评分方向：`high`
- 当前状态：已实现；当前三个评分体系都未使用。

#### `drawdown_duration_ratio_12m`

- 含义：近 `12` 个月中净值处于历史峰值下方的月份占比。
- 计算方式：逐月维护历史峰值，统计 `nav < running_peak` 的月份比例。
- 金融语义：衡量回撤状态是否长期拖延。
- 评分方向：`low`
- 当前状态：观察层；当前三个正式评分体系都未使用。

#### `months_since_drawdown_low_12m`

- 含义：距离近 `12` 个月回撤低点已经过去了多少个月。
- 计算方式：在窗口内定位回撤低点并计算至当前月的月数。
- 金融语义：衡量基金是否已经离开最差阶段一段时间。
- 评分方向：`high`
- 当前状态：已实现；当前三个评分体系都未使用。

#### `hit_rate_12m`

- 含义：近 `12` 个月中正收益月份占比。
- 计算方式：统计 `return_1m > 0` 的月份比例。
- 金融语义：反映盈利月份出现得是否足够频繁。
- 评分方向：`high`
- 当前状态：已实现；当前三个评分体系都未使用。

#### `profit_loss_ratio_12m`

- 含义：近 `12` 个月平均盈利月份收益与平均亏损月份亏损绝对值之比。
- 计算方式：`average_gain / average_loss`；若无亏损则返回较大保护值。
- 金融语义：衡量“赚的时候赚多少、亏的时候亏多少”。
- 评分方向：`high`
- 当前状态：已实现；当前三个评分体系都未使用。

#### `worst_3m_avg_return_12m`

- 含义：近 `12` 个月中最差 `3` 个月收益的平均值。
- 计算方式：取近 `12` 个月月收益，从低到高排序，取最差 `3` 个月做平均。
- 金融语义：直接刻画左尾阶段的杀伤力。
- 评分方向：`high`
- 说明：值越高越好，表示最差几个月没那么差。
- 当前状态：`v2`、`v3` 使用。

#### `tail_loss_ratio_12m`

- 含义：近 `12` 个月中最差 `2` 个月亏损，占全部亏损月亏损总和的比例。
- 计算方式：提取负收益月的亏损绝对值，取最差 `2` 个月亏损之和除以全部亏损之和。
- 金融语义：衡量亏损是否过度集中在少数极端月份。
- 评分方向：`low`
- 当前状态：观察层；当前三个正式评分体系都未使用。

### 2.3 经理与运作稳定性类

#### `manager_tenure_months`

- 含义：当前月下基金经理任期月数。
- 计算方式：
  - 优先取月度经理映射里的 `manager_start_month`
  - 若缺失则回退到实体层 `manager_start_month`
  - 若仍缺失则回退到 `inception_month`
- 金融语义：经理任期越长，当前业绩与现任管理团队的对应关系通常更清楚。
- 评分方向：`high`
- 当前状态：基线评分体系使用。

#### `manager_change_count_24m`

- 含义：近 `24` 个月内经理名称发生变化的次数。
- 计算方式：基于 `manager_assignment_monthly` 比较相邻月份经理名称是否变化。
- 金融语义：把频繁换帅视作稳定性风险代理。
- 评分方向：`low`
- 当前状态：观察层；当前三个正式评分体系都未使用。

#### `manager_post_change_excess_delta_12m`

- 含义：现任经理上任后相对上任前的超额收益均值变化。
- 计算方式：
  - 以当前经理 `manager_start_month` 为分界
  - 分别取上任前后、截至当前月最多 `12` 个月的月度超额收益
  - 计算 `post_mean_excess - pre_mean_excess`
  - 若任一侧可见月份少于 `3`，则记缺失
- 金融语义：观察换经理之后，基金相对 benchmark 的表现是否改善。
- 评分方向：`high`
- 当前状态：`v2`、`v3` 使用。

#### `manager_post_change_downside_vol_delta_12m`

- 含义：现任经理上任后相对上任前的下行波动变化。
- 计算方式：
  - 以当前经理 `manager_start_month` 为分界
  - 分别取上任前后最多 `12` 个月基金月收益
  - 计算 `post_downside_vol - pre_downside_vol`
  - 若任一侧可见月份少于 `3`，则记缺失
- 金融语义：观察换帅后亏损月份的波动是否收敛。
- 评分方向：`low`
- 当前状态：观察层；当前三个正式评分体系都未使用。

#### `asset_stability_12m`

- 含义：近 `12` 个月规模波动幅度。
- 计算方式：`max(assets) / min(assets) - 1`
- 金融语义：衡量基金规模是否大起大落，间接反映申赎扰动和运作稳定性。
- 评分方向：`low`
- 说明：数值越大越不稳定。
- 当前状态：基线、`v2` 使用。

#### `asset_growth_6m`

- 含义：当前实体规模相对 `6` 个月前的增长率。
- 计算方式：`assets_t / assets_t-6 - 1`
- 金融语义：观察容量扩张与潜在拥挤程度。
- 评分方向：`high`
- 当前状态：观察层；当前三个正式评分体系都未使用。

#### `asset_flow_volatility_12m`

- 含义：近 `12` 个月月度规模变化率的波动率。
- 计算方式：
  - 先计算相邻月份规模变化率 `assets_t / assets_t-1 - 1`
  - 再对窗口内变化率计算标准差
- 金融语义：衡量资金流入流出是否剧烈摇摆。
- 评分方向：`low`
- 当前状态：观察层；`v3` 使用。

## 3. 评分体系

### 3.1 统一评分规则

所有评分体系都共用同一套横截面打分机制：

- 先只在当月 `is_eligible = 1` 的基金里比较。
- 单字段先转成同月横截面分位分数 `0 ~ 1`。
- 再按类内权重合成：
  - `performance_quality`
  - `risk_control`
  - `stability_quality`
- 最后按类间权重合成 `total_score`。

### 3.2 基线评分体系

- 真实来源：
  - 配置文件：[`configs/tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
  - 当前结构来源：`v2-lite` 升级后的默认 baseline
- 说明：
  - `tushare.json` 当前已经显式写出类间权重与类内因子。
  - 它不再依赖 `config.py` 里的默认因子回退。

类间权重：

| 类别 | 权重 |
| --- | ---: |
| `performance_quality` | `0.50` |
| `risk_control` | `0.35` |
| `stability_quality` | `0.15` |

类内因子：

| 类别 | 因子 | 权重 |
| --- | --- | ---: |
| `performance_quality` | `excess_ret_12m` | `0.70` |
| `performance_quality` | `ret_12m` | `0.30` |
| `risk_control` | `downside_vol_12m` | `0.55` |
| `risk_control` | `worst_3m_avg_return_12m` | `0.45` |
| `stability_quality` | `asset_stability_12m` | `1.00` |

设计特点：

- 收益侧从“绝对收益主导”切到“超额收益主导”。
- 风险侧更关注下行风险和左尾压力，不再保留总波动与最大回撤三件套。
- 稳定性侧只保留最小必要的规模稳定约束。

### 3.3 `tushare_scoring_v2`

- 配置文件：[`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)

类间权重：

| 类别 | 权重 |
| --- | ---: |
| `performance_quality` | `0.50` |
| `risk_control` | `0.35` |
| `stability_quality` | `0.15` |

类内因子：

| 类别 | 因子 | 权重 |
| --- | --- | ---: |
| `performance_quality` | `excess_ret_12m` | `0.70` |
| `performance_quality` | `ret_12m` | `0.30` |
| `risk_control` | `downside_vol_12m` | `0.55` |
| `risk_control` | `worst_3m_avg_return_12m` | `0.45` |
| `stability_quality` | `asset_stability_12m` | `0.70` |
| `stability_quality` | `manager_post_change_excess_delta_12m` | `0.30` |

设计特点：

- 收益侧从“绝对收益主导”切到“超额收益主导”。
- 风险侧弱化总波动与最大回撤，改看下行风险和左尾阶段损伤。
- 稳定性侧弱化经理任期，加入经理变更事件后的表现改善因子。

### 3.4 `tushare_scoring_v3`

- 配置文件：[`tushare_scoring_v3.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v3.json)

类间权重：

| 类别 | 权重 |
| --- | ---: |
| `performance_quality` | `0.50` |
| `risk_control` | `0.35` |
| `stability_quality` | `0.15` |

类内因子：

| 类别 | 因子 | 权重 |
| --- | --- | ---: |
| `performance_quality` | `excess_ret_12m` | `0.55` |
| `performance_quality` | `ret_12m` | `0.15` |
| `performance_quality` | `excess_hit_rate_12m` | `0.30` |
| `risk_control` | `downside_vol_12m` | `0.55` |
| `risk_control` | `worst_3m_avg_return_12m` | `0.45` |
| `stability_quality` | `asset_flow_volatility_12m` | `0.80` |
| `stability_quality` | `manager_post_change_excess_delta_12m` | `0.20` |

设计特点：

- 收益侧在 `v2` 基础上加入 `excess_hit_rate_12m`，补充“超额是否持续发生”。
- 风险侧延续 `v2` 的下行风险和左尾韧性组合。
- 稳定性侧用 `asset_flow_volatility_12m` 替代 `asset_stability_12m`，测试更直接的资金流波动约束。

## 4. 因子使用总览

下面这张表用于快速回答“某个因子到底在哪套体系里被用到了”。

| 因子 | 基线 | `v2` | `v3` | 观察层 |
| --- | --- | --- | --- | --- |
| `ret_3m` |  |  |  |  |
| `ret_6m` | `Y` |  |  |  |
| `ret_12m` | `Y` | `Y` | `Y` |  |
| `excess_ret_3m` |  |  |  |  |
| `excess_ret_6m` |  |  |  |  |
| `excess_ret_12m` | `Y` | `Y` | `Y` |  |
| `excess_consistency_12m` |  |  |  |  |
| `excess_hit_rate_12m` |  |  | `Y` | `Y` |
| `excess_streak_6m` |  |  |  | `Y` |
| `vol_12m` | `Y` |  |  |  |
| `downside_vol_12m` | `Y` | `Y` | `Y` |  |
| `max_drawdown_12m` | `Y` |  |  |  |
| `drawdown_recovery_ratio_12m` |  |  |  |  |
| `drawdown_duration_ratio_12m` |  |  |  | `Y` |
| `months_since_drawdown_low_12m` |  |  |  |  |
| `hit_rate_12m` |  |  |  |  |
| `profit_loss_ratio_12m` |  |  |  |  |
| `worst_3m_avg_return_12m` |  | `Y` | `Y` |  |
| `tail_loss_ratio_12m` |  |  |  | `Y` |
| `manager_tenure_months` | `Y` |  |  |  |
| `manager_change_count_24m` |  |  |  | `Y` |
| `manager_post_change_excess_delta_12m` |  | `Y` | `Y` |  |
| `manager_post_change_downside_vol_delta_12m` |  |  |  | `Y` |
| `asset_stability_12m` | `Y` | `Y` |  |  |
| `asset_growth_6m` |  |  |  | `Y` |
| `asset_flow_volatility_12m` |  |  | `Y` | `Y` |

## 5. 非评分辅助字段

以下字段会出现在特征层或调试分析中，但不应当被理解为评分因子：

### `manager_post_change_observation_months`

- 含义：当前经理上任后，事件类因子可见的后验观察月数。
- 作用：辅助判断 `manager_post_change_excess_delta_12m` 是否因为样本太短而缺失。
- 当前状态：诊断字段，不参与评分。
