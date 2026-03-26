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

## 9. 回测曾静默跳过无评分月份

- 发现时间：2026-03-19
- 影响模块：
  - [`engine.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/backtest/engine.py)
- 现象：
  - 回测结果只保留“有评分结果的月份”，中间无信号月份会直接消失。
  - 会出现 `2023-04 -> 2024-08` 这类跳月结果，看起来不像正常月频回测。
- 根因：
  - 旧实现直接使用 `score_rows` 中出现的月份序列做 `zip(months, months[1:])`。
- 修复方案：
  - 改为按 `backtest.start_month ~ backtest.end_month` 的完整月历推进。
  - 无评分月份显式记为空仓期，收益记为 `0`，同时保留换手与 benchmark 对比。
- 影响范围：
  - 会改变回测月数。
  - 会改变年化收益、波动率、胜率、最大回撤等统计结果。
  - 新旧 baseline 不再完全可比。
- 当前状态：已修复，并补充测试。

## 10. `sample` 与 `tushare` 共用 outputs 导致结果被后续运行覆盖

- 发现时间：2026-03-19
- 影响模块：
  - [`workflows.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/workflows.py)
  - [`providers.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
- 现象：
  - 明明刚跑完真实 `tushare`，但后面一轮 `sample` 验证后，`outputs/` 和 `data/raw/` 看起来又像 sample 结果。
- 根因：
  - 旧实现只对缓存口径做了校验，但产物目录本身没有按数据源隔离。
- 修复方案：
  - 把 raw 与 outputs 统一切到 `data/raw/<data_source>/...` 和 `outputs/<data_source>/...`。
- 影响范围：
  - 旧的未分流产物会继续留在根目录，容易造成视觉混淆。
  - 新代码下，sample 与 tushare 产物已经互不覆盖。
- 当前状态：已修复。

## 11. 接入层缺少标准审计，导致 `80 -> 45 -> 36` 难以解释

- 发现时间：2026-03-19
- 影响模块：
  - [`providers.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
  - [`workflows.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/workflows.py)
- 现象：
  - 用户能看到最终 clean 层数量，但看不到哪些份额/实体在接入阶段被挡掉。
- 根因：
  - 旧实现只保留成功进入研究快照的数据，没有把接入阶段的丢弃明细单独落盘。
- 修复方案：
  - 新增 `ingestion_audit_report.md` 与 `dropped_entities.csv`。
  - 把接入层漏斗与被丢弃实体原因写入 `dataset_snapshot.metadata.ingestion_audit`。
- 影响范围：
  - 修复前，很多数据接入问题只能临时排查，无法稳定复盘。
- 当前状态：已修复。

## 12. `fund_age` 与 `history` 双重门槛在主线下高度重叠

- 发现时间：2026-03-19
- 影响模块：
  - [`filters.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/universe/filters.py)
  - 基金池配置
- 现象：
  - `min_history_months = 24` 与 `min_fund_age_months = 12` 同时启用时，`fund_too_new` 在真实数据里几乎没有独立筛选贡献。
- 根因：
  - 历史净值长度门槛已经是更强约束，导致成立月数门槛在当前主线下大多只是重复报错。
- 修复方案：
  - 移除默认基金池中的独立 `fund_age` 门槛。
  - 保留 `fund_age_months` 作为审计字段。
- 影响范围：
  - 基金池原因码更简洁。
  - 新旧 baseline 不再完全可比。
- 当前状态：已修复。

## 13. 单一 benchmark 同时用于 `主动股票` 与 `偏股混合`

- 发现时间：2026-03-20
- 影响模块：
  - [`feature_builder.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/features/feature_builder.py)
  - [`engine.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/backtest/engine.py)
  - benchmark 配置与报告模块
- 现象：
  - `excess_ret_12m` 和回测比较基准都默认使用同一条中证800。
  - `主动股票` 与 `偏股混合` 的市场暴露差异没有被 benchmark 口径反映。
- 根因：
  - 早期实现把 benchmark 视作“全策略唯一序列”，数据契约只有 `month -> return` 这一维。
- 修复方案：
  - benchmark 配置升级为 `default_key + series + primary_type_map`。
  - `benchmark_monthly` 升级为多序列结构。
  - 特征层按基金类型映射 benchmark，回测按组合权重聚合 benchmark。
- 影响范围：
  - 新旧版本的 `excess_ret_12m`、`performance_quality` 与回测超额收益不再完全可比。
  - 旧缓存若仍保留单 benchmark 结构，会被新的 benchmark 配置签名校验拒绝复用。
- 当前状态：已修复，并补充测试。

## 14. 基金类型判断过于依赖 `fund_type` 单字段

- 发现时间：2026-03-20
- 影响模块：
  - [`providers.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
  - benchmark 映射、基金池与审计解释
- 现象：
  - 旧实现只要 `fund_type` 含“股票”就归为 `主动股票`，含“混合”就归为 `偏股混合`。
  - 被动指数、指数增强、灵活配置混合等产品容易被粗暴归类。
- 根因：
  - 类型标准化逻辑过早简化，没有综合使用 `invest_type`、基金名称和业绩比较基准文本。
- 修复方案：
  - 抽出独立基金类型分类模块。
  - 新增 `fund_type_audit.csv` 与 `fund_type_audit_report.md`，把规则命中、置信度和中文解释显式落盘。
- 影响范围：
  - 新旧版本在 `primary_type`、基金池原因码、benchmark 映射与超额收益解释上不再完全可比。

## 15. 月内快照曾被误当成正式最新信号月

- 发现时间：2026-03-21
- 影响模块：
  - [`workflows.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/workflows.py)
  - [`reports.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/reporting/reports.py)
  - 组合快照、实验报告、基金池审计报告与类型基线快照
- 现象：
  - 当前日期仍在月中时，系统会直接把 raw 数据中出现的最大 `month` 当成 `latest_month`。
  - 例如在 `2026-03-21` 运行时，会把 `2026-03` 月内数据当成正式最新信号月。
- 根因：
  - 旧实现多个模块都直接使用 `max(row["month"])` 推导最新月。
  - 系统没有统一定义“正式研究月”和“raw 快照最大月份”的区别。
- 修复方案：
  - 新增统一的“正式最新研究月”判断：正式最新月取 `as_of_date` 之前最后一个完整结束的自然月。
  - 组合、实验记录、基金池审计、类型基线和报告全部改走同一套时间边界。
  - 文档同步明确：月内数据只能视为观察快照，不能直接进入正式组合建议。
- 影响范围：
  - 修复前，最新组合建议、最新月基金池统计和实验报告都可能带有月内前视风险。
  - 修复后，`latest_month` 可能小于 raw 快照中的最大 `month`，新旧实验不再完全可比。
- 当前状态：已修复，并补充测试。
- 当前状态：已修复，并补充测试。

## 16. 持有期缺失收益曾被静默按 0 处理，缺乏显式审计

- 发现时间：2026-03-23
- 影响模块：
  - [`engine.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/backtest/engine.py)
  - [`metrics.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/evaluation/metrics.py)
  - [`reports.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/reporting/reports.py)
- 现象：
  - 当持仓基金在 `execution_month` 缺少收益时，回测会直接按 `0` 计入组合，但结果表与报告无法回答“有多少权重其实缺少收益观测”。
- 根因：
  - 旧实现把缺失收益处理视为引擎内部细节，没有把缺失权重、缺失持仓数和月份置信度显式落盘。
- 修复方案：
  - 保留 `zero_fill_legacy` 兼容口径。
  - 新增 `missing_weight`、`missing_position_count`、`low_confidence_flag`、`return_validity` 与 `backtest_position_audit.csv`。
- 影响范围：
  - 修复前，协作者容易把存在缺失收益的月份误读为与普通月份同等可靠。
  - 修复后，历史收益定义未变，但回测结果的可解释性显著增强。
- 当前状态：已修复，并补充测试。

## 17. benchmark 配置保留多序列映射，但主回测已固定使用默认市场 benchmark，容易被误读

- 发现时间：2026-03-26
- 影响模块：
  - [`configs/tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)
  - [`configs/tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)
  - [`configs/tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json)
  - [`engine.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/backtest/engine.py)
  - 报告与协作文档
- 现象：
  - 配置里同时保留 `series` 与 `primary_type_map`，看起来像“主回测仍会按基金类型切换 benchmark”。
  - 但当前主回测实际只使用 `benchmark.default_key`，也就是固定市场 benchmark。
  - 如果只看配置、不看引擎实现，协作者很容易误以为 `偏股混合 -> broad_equity`、`主动股票 -> broad_equity` 这些映射仍直接驱动主回测。
- 根因：
  - 为了兼容特征层、多 benchmark 原始数据和历史元数据，配置结构保留了多序列映射。
  - 但主回测逻辑已切回固定市场 benchmark，配置结构与主执行语义没有同步收敛，导致“看配置像多 benchmark、看引擎才知道是固定 benchmark”的表达断层。
- 修复方案：
  - 在文档和报告中明确写清：主回测固定使用 `benchmark.default_key`，`primary_type_map` 当前只保留为元数据和扩展位。
  - 后续若继续保留该配置结构，所有 benchmark 相关文档都必须同时说明“配置能力”和“主回测实际用法”。
  - 若未来再次启用多 benchmark 主回测，必须单独记录到 `changes.md` 与 `error_log.md`，避免口径回摆却没有显式审计。
- 影响范围：
  - 容易导致 benchmark 口径被错误理解，进而误判超额收益、比较报告和升级评审结论。
  - 容易在后续协作中再次出现“以为主回测按基金类型挂 benchmark，实际上并没有”的重复错误。
- 当前状态：已记录，并已在当前文档中补充固定市场 benchmark 说明。
