# 候选评分稳健性分析说明

本文档解释 `analyze-robustness` 的设计目标、实现逻辑、输出含义与协作使用方式。
它对应当前代码中的以下位置：

- [`robustness.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/evaluation/robustness.py)
- [`robustness_reports.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/reporting/robustness_reports.py)
- [`workflows.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/workflows.py)

本文档的目标不是证明某个候选配置一定更好，而是统一回答下面几个问题：

- 候选评分体系的收益提升是否跨阶段存在，而不是只集中在少数年份
- 候选评分体系是否主要依赖少数极端月份贡献
- 候选评分体系是否通过更激进的换仓或更集中的组合换来收益
- 候选评分体系内部真正参与打分的因子，在不同阶段是否仍然大体保持同方向

## 1. 为什么需要这一步

单次回测结果只能回答“在当前样本里，这个配置跑成了什么样”。
它不能直接回答：

- 收益是不是只在少数月份兑现
- 提升是不是只出现在某一个市场阶段
- 更高收益是不是主要来自更高换仓或更高集中暴露
- 评分体系里新增的因子，在不同阶段是否仍有相同方向

因此，`analyze-robustness` 的定位不是重新定义策略，也不是替代正式回测，而是在“候选配置 vs 默认 baseline”之间增加一层只读诊断。

## 2. 分析对象与输入

命令入口：

```bash
PYTHONPATH=src python3 -m fund_research_v2 analyze-robustness --config configs/archive/factor_research/tushare_scoring_v4.json
```

当前工作流会先加载：

1. 候选配置
2. 默认 baseline 配置
3. 两套配置在同一项目根目录下准备出的数据快照与评分结果

baseline 的选择规则由 [`default_baseline_config_path()`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/evaluation/robustness.py) 决定：

- 若候选配置所在目录下存在同数据源的 `<data_source>.json`，则把它作为 baseline
- 若不存在，再回退到 `default.json`
- 若两者都不存在，才退回候选配置自身

这意味着：

- `configs/archive/factor_research/tushare_scoring_v2.json` 默认会与 `configs/tushare.json` 比
- `configs/sample_scoring_v2.json` 默认会与 `configs/sample.json` 比

## 3. 整体逻辑

`build_robustness_analysis()` 会做五件事：

1. 分别对候选配置和 baseline 跑回测
2. 为两套评分结果各自重建逐月目标组合
3. 对回测结果按时间切片做摘要比较
4. 对候选回测的月度超额收益做贡献和删月敏感性分析
5. 对候选评分体系中真正参与打分的原子因子做分阶段方向稳定性分析

最终输出四张诊断表和一份摘要：

- `robustness_time_slices.csv`
- `robustness_month_contribution.csv`
- `robustness_portfolio_behavior.csv`
- `robustness_factor_regime.csv`
- `robustness_summary.json`

这些产物当前统一写入独立目录：

- `outputs/<data_source>/robustness/`

## 4. 四类诊断分别在看什么

### 4.1 时间切片比较

对应函数：`_build_time_slice_rows()`

目的：

- 看候选收益改善是否跨阶段存在
- 避免只看完整样本区间的一个总收益数字

当前会生成三类切片：

- `calendar_year`
- `half_year`
- `rolling_12m`

每个切片里都会对 baseline 和 candidate 分别计算：

- 月数
- 累计收益
- 年化收益
- 年化波动
- 最大回撤
- benchmark 累计收益
- 超额累计收益
- 胜率
- 平均换手
- 平均交易成本
- 平均缺失权重
- 低置信月份数

这里的核心原则是：

- 候选方案如果只在某一年明显领先，而在其余年份普遍落后，则不能轻易认为它适合升级为 baseline
- 候选方案如果完整区间更高，但 rolling 12m 表现高度不稳定，也应保持谨慎

### 4.2 月度收益贡献与删月敏感性

对应函数：`_build_month_contribution_rows()` 和 `_contribution_sensitivity_summary()`

目的：

- 看超额收益是否集中在少数极端正收益月份
- 回答“去掉最好几个月以后，结果还剩多少”

这里会对候选回测的每个月计算：

- 当月组合净收益
- 当月 benchmark 收益
- 当月超额收益
- 截至当月的累计超额收益
- 按超额收益从高到低的月度贡献排名
- 是否属于前 5 大正贡献月
- 是否属于前 5 大负贡献月

摘要部分还会进一步计算：

- `top3_positive_excess_share`
- `cumulative_return_without_best3`
- `cumulative_return_without_worst3`
- `excess_return_without_best3`

其中最重要的是 `top3_positive_excess_share`：

- 它表示候选配置全部正超额收益中，有多少比例来自最好的 3 个月
- 该值越高，说明候选配置越可能依赖少数行情月份

当前 summary 里把阈值定为：

- `top3_positive_excess_share >= 0.5` 时，`return_concentration_flag = 1`

这不是统计显著性检验，而是一个审计告警阈值。

### 4.3 组合行为分析

对应函数：`_build_portfolio_behavior_rows()`

目的：

- 看候选收益提升是不是通过更激进的组合行为换来的
- 把“收益更高”拆解成“是否更集中、是否换仓更多、是否持仓更不稳定”

这里会按月输出 baseline 和 candidate 各自的：

- `holdings`
- `top1_weight`
- `top3_weight_sum`
- `company_count`
- `top_company_weight_proxy`
- `new_entry_count`
- `dropped_count`
- `weight_overlap_ratio`

这些字段大致回答：

- 持仓是不是更少、更集中
- 单一基金公司暴露是否更高
- 每个月新进组合的基金数量是否更多
- 当前月和上个月组合的重叠是否更低

当前摘要里的换仓风险判断规则很简单：

- 候选组合的平均 `new_entry_count` 若高于 baseline，则 `turnover_risk_flag = 1`

因此它是一个偏保守的结构提示，不是完整的交易摩擦模型。

### 4.4 因子阶段稳定性

对应函数：`_build_factor_regime_rows()`

目的：

- 不只看组合结果，还要回头检查候选配置内部因子在不同阶段是否仍保持大致一致的方向
- 防止“总收益提升”其实来自个别因子在个别阶段偶然奏效

这里不会分析所有 feature 字段，而只分析候选评分体系中真正参与打分的原子因子。
字段集合由 `_candidate_factor_fields()` 从 `ranking.category_factors` 中提取。

对每个切片、每个因子，当前会：

1. 取该月可投基金横截面样本
2. 读取该因子的当月取值
3. 读取这些基金下一月 `return_1m`
4. 根据因子方向计算月度 RankIC
5. 计算 top-bottom 下一月收益差

当前只生成两类因子切片：

- `calendar_year`
- `half_year`

每行输出：

- `evaluation_months`
- `avg_rankic`
- `positive_rankic_ratio`
- `avg_top_bottom_next_return`

其中方向约定来自 `_factor_direction()`：

- 波动、规模波动、拖延回撤、换帅后下行波动变化等字段按 `low`
- 其他字段按 `high`

这一步的重点不是证明因子显著，而是观察：

- 它在大多数阶段里是不是同方向
- 它是否频繁在不同年份反向

## 5. 摘要里的四个 flag 是怎么来的

`robustness_summary.json` 不是人工结论，而是代码按固定规则生成的摘要。

### 5.1 `time_slice_consistency_flag`

规则：

- 先看 `calendar_year` 切片
- 统计候选配置超额累计收益高于 baseline 的年份数
- 若胜出年份数至少达到 `总年份数 - 1`，则记为 `1`

含义：

- 候选配置在绝大多数年份都没有输给 baseline

注意：

- 它只看按年聚合后的超额累计收益
- 不代表每个半年或每个 rolling 12m 都更好

### 5.2 `return_concentration_flag`

规则：

- 若 `top3_positive_excess_share >= 0.5`，则记为 `1`

含义：

- 候选超额收益有至少一半依赖最好的 3 个月

### 5.3 `turnover_risk_flag`

规则：

- 若候选组合的平均 `new_entry_count` 大于 baseline，记为 `1`

含义：

- 候选组合更依赖频繁更换持仓

### 5.4 `factor_stability_flag`

规则：

- 只看 `calendar_year` 且 `evaluation_months > 0` 的候选因子阶段结果
- 若其中 `avg_rankic > 0` 的行占比至少达到 `60%`，记为 `1`

含义：

- 候选评分体系内部的大多数因子，在按年切片后仍保持正向关系

注意：

- 这是很弱的稳定性门槛
- 它不等于“因子显著”
- 它更像是“没有大面积方向反转”的最小诊断

## 6. `overall_assessment` 是怎么判的

当前代码里的判定非常克制：

- 若 `time_slice_consistency_flag = 1`
- 且 `factor_stability_flag = 1`
- 且 `return_concentration_flag = 0`

则：

- `overall_assessment = keep_candidate`

否则：

- `overall_assessment = needs_more_validation`

注意这里没有把 `turnover_risk_flag` 直接写进最终 gate。
这意味着：

- 换仓风险目前被视为需要人工复核的结构信号
- 还没有被当作一票否决条件

因此，看到 `keep_candidate` 时，也不应自动理解为“可以直接升为 baseline”。
它只表示：按照当前这套最小诊断规则，候选配置没有触发明显的稳健性红旗。

## 7. 这套方法回答不了什么

当前稳健性分析刻意保持轻量，因此它不能回答很多更强的问题：

- 不能回答统计显著性
- 不能回答样本外泛化能力
- 不能回答不同市场风格标签下的真实因果
- 不能回答生命周期事件、暂停申赎、清盘退出对稳健性的影响
- 不能回答更高收益是否在现实交易摩擦下仍成立

因此，`analyze-robustness` 应被理解为：

- 候选评分升级前的一道审计门
- 不是正式研究结论的终点

## 8. 推荐阅读顺序

如果要评估一个候选评分体系是否接近 baseline 升级条件，建议按下面顺序阅读：

1. `outputs/<data_source>/robustness/robustness_summary.json`
2. `outputs/<data_source>/robustness/robustness_report.md`
3. `outputs/<data_source>/robustness/robustness_time_slices.csv`
4. `outputs/<data_source>/robustness/robustness_month_contribution.csv`
5. `outputs/<data_source>/robustness/robustness_portfolio_behavior.csv`
6. `outputs/<data_source>/robustness/robustness_factor_regime.csv`
7. `outputs/<data_source>/comparison/comparison_report.md`
8. `outputs/<data_source>/factor_evaluation/factor_evaluation.json`

推荐这样读的原因是：

- 先看摘要，确认有没有触发明显红旗
- 再看时间切片和月度贡献，判断收益是否集中
- 再看组合行为，判断是不是更激进
- 最后回到因子层，确认候选配置内部逻辑是否仍然站得住

## 9. 协作时的建议话术

为了避免讨论失焦，团队在复盘稳健性结果时，建议把结论分成三层：

- 观察结果：
  - 例如“候选配置在 2024、2025 年按年切片超额收益高于 baseline”
- 结构解释：
  - 例如“候选配置的提升没有集中在最好的 3 个月”
- 决策建议：
  - 例如“继续保留为主候选基线，但暂不升默认 baseline”

不建议直接写成：

- “这个配置已经被证明更优”
- “这个评分体系未来一定更稳健”

## 10. 当前最重要的使用边界

在本项目里，稳健性分析只用于回答：

- 候选评分体系是否值得继续保留
- 候选评分体系是否值得进一步做 baseline 升级讨论

它默认不用于：

- 直接替代正式实验报告
- 直接宣布策略升级
- 为收益提升提供因果证明

如果后续需要更强的升级证据，应继续补：

- 更细的阶段划分
- 更明确的风险调整指标
- 更完整的交易与生命周期事件建模
- 更系统的候选配置对照矩阵
