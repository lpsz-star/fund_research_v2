# 因子目录

本文档记录当前版本已经落地到生产代码中的特征、评分因子与合成口径。
目标是让协作者能够直接回答三个问题：

- 当前到底算了哪些因子
- 每个因子在金融上是什么意思
- 这些因子如何进入最终评分

本文档只描述当前代码真实存在的字段，不描述尚未实现的设想。

当前完整实验还会额外输出一份因子评估报告：

- `factor_evaluation.json`
- `factor_evaluation.csv`
- `factor_evaluation_report.md`

它们用于回答“这些因子在下一月收益上是否真的有区分度”，不直接改变当前评分或回测口径。

## 1. 适用范围

当前因子体系服务于：

- 资产范围：中国市场场外公募主动权益基金
- 当前纳入基金类型：
  - `主动股票`
  - `偏股混合`
  - `灵活配置混合`
- 调仓频率：月频
- 信号时点：最后一个完整自然月的月末
- 执行时点：下一月

注意：

- 因子虽按 `month` 月频落盘，但正式研究只使用 `as_of_date` 之前最后一个完整月作为“最新信号月”
- 尚未走完的当月若已经有部分净值或规模记录，只能用于观察，不直接进入正式组合建议

相关实现：

- 特征计算：[feature_builder.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/features/feature_builder.py)
- 横截面评分：[scoring_engine.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/ranking/scoring_engine.py)

## 2. 总体结构

当前评分分成三大类：

1. 收益质量 `performance_quality`
2. 风险控制 `risk_control`
3. 稳定性质量 `stability_quality`

最终总分 `total_score` 是三类因子分的加权和，默认权重来自 [`configs/tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)：

- `performance_quality`: `0.45`
- `risk_control`: `0.35`
- `stability_quality`: `0.20`

评分方法不是绝对值打分，而是“同月横截面分位映射”：

- 每个月只在当月可投基金之间比较
- 每个字段先按排序位置映射到 `0 ~ 1`
- 再在类别内加权合成

这样做的目的，是先固定一个可解释、可追踪、对异常值不太敏感的基础评分口径。

当前评分引擎已经支持把三大类内部因子集合配置化，而不再完全写死在代码里：

- 默认基线配置：[`tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
- 候选优化配置：[`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)

这意味着：

- 新因子可以先进入观察层
- 评分体系优化可以通过新配置做对照实验
- 不必直接覆盖旧 baseline

## 3. 原子特征

### 3.1 `ret_3m`

- 含义：截至当前月的近 `3` 个月复利累计收益
- 计算方式：
  - 使用月收益 `return_1m`
  - 对窗口内收益做复利连乘
- 金融语义：
  - 反映基金近期短期动量
- 风险提示：
  - 对短期风格切换比较敏感

### 3.2 `ret_6m`

- 含义：截至当前月的近 `6` 个月复利累计收益
- 计算方式：
  - 使用月收益 `return_1m`
  - 对窗口内收益做复利连乘
- 金融语义：
  - 比 `ret_3m` 更平滑，兼顾趋势与阶段性表现

### 3.3 `ret_12m`

- 含义：截至当前月的近 `12` 个月复利累计收益
- 计算方式：
  - 使用月收益 `return_1m`
  - 对窗口内收益做复利连乘
- 金融语义：
  - 反映基金过去一年的整体收益表现
- 当前用途：
  - 是收益质量因子的核心字段

### 3.4 `excess_ret_12m`

- 含义：截至当前月的近 `12` 个月累计超额收益
- 计算方式：
  - `ret_12m - benchmark_12m_return`
- benchmark 来源：
  - 当前改为按 `primary_type` 映射 benchmark
  - 默认映射为：
    - `主动股票 -> 中证800 (000906.SH)`
    - `偏股混合 -> 沪深300 (000300.SH)`
    - `灵活配置混合 -> 中证800 (000906.SH)`
- 金融语义：
  - 区分“市场整体上涨带来的收益”和“基金相对市场的主动超额”
- 时间边界：
  - 只使用当前月及历史月度 benchmark 收益，不引入未来信息
- 工程说明：
  - 若某类基金缺少专属 benchmark 序列，当前会安全回退到默认 benchmark，而不是让整条特征缺失

### 3.5 `vol_12m`

- 含义：截至当前月的近 `12` 个月收益波动率
- 计算方式：
  - 对窗口内月收益计算总体标准差
- 金融语义：
  - 衡量收益路径波动程度
- 当前说明：
  - 当前是月频总体波动率，尚未做年化

### 3.6 `downside_vol_12m`

- 含义：截至当前月的近 `12` 个月下行波动率
- 计算方式：
  - 仅保留负收益月份
  - 对负收益平方均值开根号
- 金融语义：
  - 更关注亏损波动，而不是全部波动
- 当前说明：
  - 如果窗口内没有负收益，记为 `0.0`

### 3.7 `max_drawdown_12m`

- 含义：截至当前月的近 `12` 个月最大回撤
- 计算方式：
  - 基于窗口内净值路径
  - 用历史峰值到后续低点的最大跌幅表示
- 金融语义：
  - 衡量持有体验中最差的历史回撤风险
- 当前方向：
  - 数值越低越差，评分时按“回撤更小更好”处理

### 3.8 `manager_tenure_months`

- 含义：当前月下基金经理任期月数
- 计算方式：
  - 优先使用 `manager_assignment_monthly` 中该月匹配到的 `manager_start_month`
  - 若月度经理映射缺失，再回退到 `fund_entity_master.manager_start_month`
  - 若仍缺失或异常，回退到 `inception_month`
  - 若起始月晚于当前观察月，则做安全截断，不允许出现负任期
- 金融语义：
  - 经理任期越长，通常代表“当前负责人的历史业绩”更具可解释性
- 风险提示：
  - 该字段不衡量经理能力，只衡量任职持续时间
  - 若上游只返回单经理口径，联席经理和团队共管关系仍未完整刻画

### 3.9 `asset_stability_12m`

- 含义：截至当前月的近 `12` 个月规模波动幅度
- 计算方式：
  - `max(assets) / min(assets) - 1`
- 金融语义：
  - 用来刻画基金规模是否大起大落
- 当前方向：
  - 数值越大表示越不稳定
  - 在评分时按“更稳定更好”反向处理
- 当前规模口径说明：
  - 基金实体规模按同一实体下各份额规模求和
  - 当 `fund_nav` 缺少净资产字段时，会回退到 `fund_share × nav` 近似估算

## 3A. 观察层候选因子

以下因子已经进入特征层与因子评估，但当前默认不进入评分体系，只用于观察其信息增量、方向稳定性与相关性。

### 3A.1 `excess_hit_rate_12m`

- 含义：近 `12` 个月中，基金月收益跑赢对应 benchmark 的月份占比
- 计算方式：
  - 对窗口内逐月比较 `fund_return_1m > benchmark_return_1m`
  - 统计命中比例
- 金融语义：
  - 回答“超额是否持续发生”，而不是只看累计超额幅度

### 3A.2 `tail_loss_ratio_12m`

- 含义：近 `12` 个月中最差 `2` 个月亏损，占全部亏损月亏损总和的比例
- 计算方式：
  - 取负收益月份的绝对亏损值
  - 用尾部最差 `2` 个月的亏损和除以全部负收益月亏损和
- 金融语义：
  - 衡量亏损是否集中在少数极端月份，识别左尾风险尖锐度

### 3A.3 `manager_change_count_24m`

- 含义：近 `24` 个月内经理名称发生变化的次数
- 计算方式：
  - 基于 `manager_assignment_monthly`
  - 比较相邻月份经理名称是否变化
- 金融语义：
  - 作为管理稳定性的观察代理，回答“基金是否频繁换帅”

### 3A.4 `asset_growth_6m`

- 含义：当前实体规模相对 `6` 个月前的增长率
- 计算方式：
  - `assets_t / assets_t-6 - 1`
- 金融语义：
  - 作为容量扩张与潜在拥挤的观察代理
- 风险提示：
  - 当前规模仍可能依赖 `fund_share × nav` 近似值，因此先停留在观察层更稳妥

### 3A.5 `excess_streak_6m`

- 含义：近 `6` 个月内最长连续跑赢 benchmark 的月数
- 计算方式：
  - 基于逐月超额收益序列
  - 统计窗口内 `excess_return > 0` 的最长连续段长度
- 金融语义：
  - 回答“超额是否具有连续性”，而不只是累计幅度高低

### 3A.6 `drawdown_duration_ratio_12m`

- 含义：近 `12` 个月中净值处于历史峰值下方的月份占比
- 计算方式：
  - 对窗口内净值路径逐月维护历史峰值
  - 统计 `nav < running_peak` 的月份比例
- 金融语义：
  - 衡量回撤是否长期拖延，补充最大回撤深度之外的持有体验信息

### 3A.7 `manager_post_change_downside_vol_delta_12m`

- 含义：现任经理上任后相对上任前的下行波动变化
- 计算方式：
  - 以当前经理 `manager_start_month` 为分界
  - 分别取上任前后最多 `12` 个月基金月收益
  - 计算 `post_downside_vol - pre_downside_vol`
- 金融语义：
  - 观察换帅后亏损月份的波动是否收敛，而不是只看平均收益是否改善
- 风险提示：
  - 若上任前后任一侧可见月份少于 `3`，当前记为缺失，不强行造值

### 3A.8 `asset_flow_volatility_12m`

- 含义：近 `12` 个月月度规模变化率的波动率
- 计算方式：
  - 先计算相邻月份规模变化率 `assets_t / assets_t-1 - 1`
  - 再对窗口内变化率计算标准差
- 金融语义：
  - 用于识别资金申赎是否剧烈摇摆，补充“规模水平变化”之外的资金流稳定性
- 风险提示：
  - 当前规模口径仍可能受估算值影响，因此先停留在观察层

## 3B. 观察层候选因子当前状态

以下状态基于当前真实 `tushare` 样本上的因子评估结果整理，只用于研究优先级管理，不改变默认评分体系。

### 3B.1 建议继续保留观察

#### `excess_hit_rate_12m`

- 当前状态：保留观察
- 是否进入默认评分：否
- 当前判断：
  - 在真实样本上有一定正向迹象，但分层收益不稳定。
  - 与 `ret_12m`、`excess_ret_12m` 相关性偏高，更像已有收益/超额因子的补充视角，而不是全新信息源。

#### `asset_flow_volatility_12m`

- 当前状态：保留观察
- 是否进入默认评分：否
- 当前判断：
  - 第二批候选中相对最有观察价值，真实样本上的区分度优于其余 3 个新因子。
  - 但与 `asset_stability_12m` 高相关，说明它更可能是“规模稳定性”的细化版本，而不是独立 alpha 来源。

### 3B.2 建议降为低优先级观察

#### `tail_loss_ratio_12m`

- 当前状态：低优先级观察
- 是否进入默认评分：否
- 当前判断：
  - 真实样本上的方向不稳，暂未证明对下一月收益有稳定解释力。

#### `manager_change_count_24m`

- 当前状态：低优先级观察
- 是否进入默认评分：否
- 当前判断：
  - 区分度接近噪声。
  - 与 `manager_tenure_months` 有明显信息重叠。

#### `asset_growth_6m`

- 当前状态：低优先级观察
- 是否进入默认评分：否
- 当前判断：
  - 真实样本上的方向和分层表现都不稳。
  - 容易混入渠道、营销和市场风格热度噪声。

#### `excess_streak_6m`

- 当前状态：低优先级观察
- 是否进入默认评分：否
- 当前判断：
  - 连续超额的想法直观，但当前样本上的区分度接近噪声。
  - 与 `excess_hit_rate_12m` 及既有收益类因子有一定重叠。

### 3B.3 建议暂缓推进

#### `drawdown_duration_ratio_12m`

- 当前状态：暂缓
- 是否进入默认评分：否
- 当前判断：
  - 真实样本上的方向与预期不一致，暂不支持继续推进到评分候选池。

#### `manager_post_change_downside_vol_delta_12m`

- 当前状态：暂缓
- 是否进入默认评分：否
- 当前判断：
  - 事件样本覆盖不足，缺失比例高，当前证据不够稳定。
  - 该思路可以保留，但前提是后续先解决事件样本稀疏问题。

## 4. 三类合成因子

### 4.1 收益质量 `performance_quality`

字段构成：

- `ret_12m`
- `ret_6m`
- `excess_ret_12m`

类内权重：

- `ret_12m`: `0.5`
- `ret_6m`: `0.3`
- `excess_ret_12m`: `0.2`

设计含义：

- 以中期收益为主
- 兼顾半年表现
- 保留一部分相对 benchmark 的主动超额信息

### 4.2 风险控制 `risk_control`

字段构成：

- `max_drawdown_12m`
- `vol_12m`
- `downside_vol_12m`

类内权重：

- `max_drawdown_12m`: `0.4`
- `vol_12m`: `0.3`
- `downside_vol_12m`: `0.3`

设计含义：

- 最大回撤权重最高，因为它更接近持有人的实际痛感
- 波动率与下行波动共同描述收益路径风险

### 4.3 稳定性质量 `stability_quality`

字段构成：

- `manager_tenure_months`
- `asset_stability_12m`

类内权重：

- `manager_tenure_months`: `0.7`
- `asset_stability_12m`: `0.3`

设计含义：

- 当前版本更强调经理持续性
- 规模稳定性作为辅助约束，而不是主导因子

## 4.4 `tushare_scoring_v2` 候选评分体系

当前已落地一版候选评分体系配置，用于根据因子评价结果重构正式评分：

- 配置文件：
  - [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)

类间权重：

- `performance_quality`: `0.50`
- `risk_control`: `0.35`
- `stability_quality`: `0.15`

类内因子：

- `performance_quality`
  - `excess_ret_12m`: `0.70`
  - `ret_12m`: `0.30`
- `risk_control`
  - `downside_vol_12m`: `0.55`
  - `worst_3m_avg_return_12m`: `0.45`
- `stability_quality`
  - `asset_stability_12m`: `0.70`
  - `manager_post_change_excess_delta_12m`: `0.30`

设计意图：

- 收益侧减少对 `ret_6m` 的依赖，转而更强调 `excess_ret_12m`
- 风险侧减少对 `vol_12m` 与 `max_drawdown_12m` 的直接依赖，转而更强调下行风险和极端阶段韧性
- 稳定性侧弱化 `manager_tenure_months`，改为把经理变更事件后的表现作为弱权重试验项

当前状态：

- `v2` 已在真实 `tushare` 数据上完整跑通
- 当前结果显示回测收益明显改善，但波动也明显抬升

## 4.5 `tushare_scoring_v3` 候选评分体系

当前新增一版更激进的候选评分配置，用于把“保留观察”的新因子正式纳入对照实验：

- 配置文件：
  - [`tushare_scoring_v3.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v3.json)

类间权重：

- `performance_quality`: `0.50`
- `risk_control`: `0.35`
- `stability_quality`: `0.15`

类内因子：

- `performance_quality`
  - `excess_ret_12m`: `0.55`
  - `ret_12m`: `0.15`
  - `excess_hit_rate_12m`: `0.30`
- `risk_control`
  - `downside_vol_12m`: `0.55`
  - `worst_3m_avg_return_12m`: `0.45`
- `stability_quality`
  - `asset_flow_volatility_12m`: `0.80`
  - `manager_post_change_excess_delta_12m`: `0.20`

设计意图：

- 收益侧在保留 `excess_ret_12m` 主导地位的前提下，引入 `excess_hit_rate_12m` 观察“跑赢是否持续发生”
- 风险侧延续 `v2` 的下行风险和极端阶段韧性组合
- 稳定性侧用 `asset_flow_volatility_12m` 替换 `asset_stability_12m`，测试资金流波动能否提供更直接的稳定性信息

当前状态：

- `v3` 已在真实 `tushare` 数据上完成首轮验证
- 相比 baseline 仍有明显提升，但目前尚未优于上一版 `v2`
- 因此它应被视为“候选 baseline”，而不是已经确认的最终正式评分体系

## 5. 横截面评分口径

每个月评分时，只对当月 `is_eligible = 1` 的基金进行排序。

基本规则：

- 同月比较，不跨月混排
- 默认数值越大越好
- 风险类字段按反向排序
- `asset_stability_12m` 也按反向排序，因为波动越大越差
- 若某个事件类因子在该基金上没有观测值，例如 `manager_post_change_excess_delta_12m`，当前按中性分 `0.5` 处理

分位映射方式：

- 若当月有 `N` 只基金
- 排名第一得分接近 `1`
- 排名最后得分接近 `0`
- 若当月只有 `1` 只基金，则该字段得分记为 `1.0`
