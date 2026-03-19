# 错误记录

本文档记录项目迭代过程中已经确认的错误、根因、修复方案与影响范围。
目标不是追责，而是避免同类问题在后续研究迭代中重复出现。

## 1. `sample` 与 `tushare` 共用缓存导致串仓

- 发现时间：2026-03-19
- 影响模块：
  - [`providers.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
  - [`workflows.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/workflows.py)
- 现象：
  - 运行 `make backtest-tushare` 时，`outputs/clean/dataset_snapshot.json` 与 `outputs/result/backtest_summary.json` 仍显示 `sample` 结果。
- 根因：
  - `data/raw` 被 `sample` 与 `tushare` 共用。
  - 旧实现只判断缓存文件是否存在，不校验缓存是否与当前配置的数据源、benchmark 口径一致。
- 修复方案：
  - 在 `load_cached_dataset()` 中增加缓存口径校验。
  - 校验项包括 `source_name`、`benchmark_source`、`benchmark_ts_code`。
- 影响范围：
  - 在修复前，任何 `sample -> tushare` 或 `tushare -> sample` 切换都可能读到错误快照。
  - 会直接污染基金池、特征、回测和报告结果。
- 当前状态：已修复，并补充测试。

## 2. `run-experiment` 未刷新组合报告与组合快照

- 发现时间：2026-03-19
- 影响模块：
  - [`workflows.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/workflows.py)
- 现象：
  - 运行 `make run-tushare` 后，`experiment_report.md` 已切换为 `tushare`，但 `portfolio_report.md` 和 `portfolio_snapshot.json` 仍保留旧的 `sample` 内容。
- 根因：
  - `run-experiment` 只写 `portfolio_target_monthly.csv`，没有同步刷新组合报告和组合快照。
- 修复方案：
  - 抽出统一的 `write_portfolio_outputs()`。
  - 让 `run-portfolio` 与 `run-experiment` 共用同一套组合输出逻辑。
- 影响范围：
  - 研究报告之间会出现口径不一致，影响审计与协作判断。
- 当前状态：已修复，并补充测试。

## 3. 基金实体规模误用代表份额规模

- 发现时间：2026-03-19
- 影响模块：
  - [`providers.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
  - [`filters.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/universe/filters.py)
  - [`feature_builder.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/features/feature_builder.py)
- 现象：
  - 审计报告中的部分 `assets_cny_mn` 与公开网站相差较大。
  - A/C 多份额基金的实体规模被明显低估。
- 根因：
  - 基金已经按实体合并，但规模仍只取代表份额的 `fund_nav` / `fund_share` 结果。
  - 这等价于用“A 份额规模”近似“实体总规模”，在多份额基金上口径错误。
- 修复方案：
  - 收益序列仍由代表份额承载。
  - 规模口径改为同一实体下各份额月度规模求和。
  - 增加缓存版本字段 `entity_asset_aggregation = sum_of_share_classes`，主动淘汰旧缓存。
- 影响范围：
  - 会影响基金池规模筛选。
  - 会影响规模稳定性特征。
  - 会影响审计报告对规模门槛的解释。
- 当前状态：已修复，并补充测试。

## 4. `fund_nav` 中净资产字段大面积缺失

- 发现时间：2026-03-19
- 影响模块：
  - [`providers.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
- 现象：
  - 多只基金在 `fund_nav` 近 10 日返回中，`net_asset` 和 `total_netasset` 均为 `null`。
- 根因：
  - 这不是代码 bug，而是当前 `tushare fund_nav` 在部分基金上的原始字段缺失。
- 当前处理：
  - 回退到 `fund_share × nav` 的近似规模口径。
- 剩余风险：
  - `fund_share` 是低频披露，不一定严格对应月末规模。
  - 该口径仍可能与公开网站展示的“官方最新规模”显著不同。
- 后续建议：
  - 优先接入 `fund_size` 接口，替换当前近似规模逻辑。

## 5. 未按约定同步维护 `error_log.md` 与 `changes.md`

- 发现时间：2026-03-19
- 影响模块：
  - 协作文档流程
- 现象：
  - 在多轮开发后，仓库中缺少 [`docs/error_log.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/error_log.md) 与 [`docs/changes.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/changes.md)。
- 根因：
  - 执行过程中把这两个文档错误地视为“可后补”，没有把 `AGENTS.md` 的文档要求当成强约束执行。
- 修复方案：
  - 立即补齐两个文档。
  - 后续每次实质性改动同步维护。
- 影响范围：
  - 降低协作可追踪性与变更审计质量。
- 当前状态：已补齐。

## 6. `available_date` 已落盘但未实际参与研究链路

- 发现时间：2026-03-19
- 影响模块：
  - [`filters.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/universe/filters.py)
  - [`feature_builder.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/features/feature_builder.py)
- 现象：
  - `fund_nav_monthly` 已保留 `available_date`，但基金池和特征仍直接按 `month` 全历史滚动。
- 根因：
  - 早期实现只把 `available_date` 当作预留字段，没有真正把它接进信号月可见性判断。
- 修复方案：
  - 在基金池和特征构建中统一采用“`available_date <= signal_month` 月末”规则。
  - 对当月净值尚不可见的情况新增 `no_available_nav_for_month` 审计原因码。
- 影响范围：
  - 修复前会存在净值披露延迟场景下的前视偏差。
  - 历史实验与新口径实验不再完全可比。
- 当前状态：已修复，并补充测试。

## 7. 历史月份误用当前经理，导致任期口径失真

- 发现时间：2026-03-19
- 影响模块：
  - [`providers.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
  - [`feature_builder.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/features/feature_builder.py)
- 现象：
  - 历史月份的 `manager_tenure_months` 实际是按当前经理起始月计算，而不是按当时在任经理计算。
  - 当基金发生换经理时，旧月份任期会被现任经理错误覆盖。
- 根因：
  - 早期数据契约只有实体主表中的“当前经理”字段，没有把经理任职历史展开到月频研究轴上。
- 修复方案：
  - 新增 `manager_assignment_monthly` 数据表。
  - 按月匹配 `fund_manager` 任职区间，优先选当月在任经理；同月多经理时取最近开始任职者。
  - 特征层优先使用该月经理映射计算任期，缺失时再安全回退。
- 影响范围：
  - 会影响 `manager_tenure_months`。
  - 会进一步影响 `stability_quality` 与最终排序。
  - 经理频繁更替基金的历史评分与旧版本不再可比。
- 当前状态：已修复，并补充测试。

## 8. 基金池审计曾用最新规模解释历史月份

- 发现时间：2026-03-19
- 影响模块：
  - [`filters.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/universe/filters.py)
  - [`reports.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/reporting/reports.py)
- 现象：
  - 基金池规模门槛虽然按月判断，但审计报告里仍展示 `latest_assets_cny_mn`，容易把历史月份错误理解为“当时规模已经很大/很小”。
- 根因：
  - 基金池结果表没有显式保存“当月可见规模”，报告只能回头取实体主表最新值解释历史。
- 修复方案：
  - 在 `fund_universe_monthly` 中落盘 `visible_assets_cny_mn` 等时点字段。
  - 审计报告统一使用这些逐月字段解释基金池结果。
- 影响范围：
  - 不会改变最新代码下的规模筛选逻辑，但会显著改善历史审计解释的准确性。
- 当前状态：已修复，并补充测试。
