# 变更记录

本文档按主题记录已经落地的主要改动，重点说明“改了什么”以及“为什么改”。

## 2026-04-02

### 1. 新增增量因子研究结论表

- 变更内容：
  - 在 [`outputs/tushare/factor_research/`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/factor_research/) 下新增 [`incremental_factor_research_summary.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/factor_research/incremental_factor_research_summary.csv) 与 [`incremental_factor_research_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/factor_research/incremental_factor_research_report.md)。
  - 把单因子评分卡、`replace-one`、`add-one` 和 `top6/top8/top12` 的结论沉淀为统一研究结论表。
  - [`data_contracts.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_contracts.md) 与 [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md) 同步补充新产物说明。
- 目的：
  - 让第三层增量贡献测试的关键结论不再散落在多轮对话和临时命令里，而是形成可复核、可引用的正式研究材料。

## 2026-03-30

### 1. 接入交易日历原始缓存，并落地 fund_nav 的首个可见版本选择规则

- 变更内容：
  - `DatasetSnapshot` 新增 `trade_calendar` 字段，`sample` 与 `tushare` raw 缓存都会持久化 `trade_calendar.csv`。
  - `tushare` 接入层新增 `trade_cal` 抓取与缓存，覆盖研究区间及其后一个月，作为后续 `decision_date` 与执行归属改造的基础设施。
  - `common/date_utils.py` 新增交易日工具函数，用于计算月内首个、最后一个以及下一个交易日。
  - `fund_nav` 月频构造逻辑不再默认取同一 `nav_date` 的最后修订版本，而是先做“最早公告且净值有效”的研究唯一版本选择，再据此生成月频净值和 `available_date`。
  - 新增针对交易日工具、`fund_nav` 多版本选择和 raw 缓存回读的回归测试。
- 目的：
  - 为后续“下月第 1 个交易日决策”和“卖出含当日、买入不含当日”的正式口径改造先铺好交易日历基础设施。
  - 修复 `fund_nav` 同一净值日多版本时默认取最后修订版的前视风险，统一切换到首个可见版本口径。

### 2. 基金池与特征层可得性边界改为 `decision_date`

- 变更内容：
  - 基金池不再使用“信号月月末前可见”判断净值是否可用，而是统一改为“下月第 1 个交易日 `decision_date` 前可见”。
  - 特征层和 benchmark 可见性判断同步改为 `decision_date` 口径，避免基金池、特征、benchmark 各自使用不同的时间边界。
  - 基金池输出新增 `decision_date` 字段，净值不可用原因码改为 `nav_not_available_by_decision_date`。
  - 新增回归测试，覆盖“月末净值在下月第 1 个交易日公告时仍可进入该估值月信号”的场景。
- 目的：
  - 解决大量基金月末净值在下月首个交易日才公告时，被现有“月末可见”规则错误排除的问题。
  - 让后续回测执行归属改造建立在统一、可审计的 `decision_date` 边界上。

### 3. 回测层切换到 `decision_date / T+2 / T+3` 研究执行代理

- 变更内容：
  - `fund_nav_pit_daily` 正式进入 `DatasetSnapshot` 的 raw 缓存契约，`sample` 与 `tushare` 都会持久化 `fund_nav_pit_daily.csv`。
  - `tushare` 接入层不再只生成月频净值，还会基于“最早公告且净值有效”的唯一版本生成日频 PIT 净值路径，并继续以代表份额承载收益、以全份额汇总实体规模。
  - 回测引擎新增交易日执行代理：`decision_date=T` 卖出旧组合且旧组合包含 `T` 日收益，`T+2` 现金到账后申购，`T+3` 新组合开始承担收益。
  - 回测持有期收益不再直接使用下月月收益，而是对 `fund_nav_pit_daily` 的持有期日收益做复利；benchmark 则用月收益展开成日频代理后按同一持有期复利。
  - `run_backtest`、主 workflow、候选验证和稳健性分析都已接入交易日历与日频 PIT 净值。
  - 新增回归测试，覆盖 `T / T+2 / T+3` 持有归属、PIT 日频缓存回读和 provider 新签名。
- 目的：
  - 把“卖出含当日收益、买入不含当日收益”的研究语义真正落实到回测层，而不是继续停留在月频近似。
  - 让回测、基金池、特征层共享同一套 `decision_date` 与 PIT 净值版本口径，降低时间边界漂移风险。

### 4. 新增 `run-experiment --fast` 快速模式

- 变更内容：
  - `run-experiment` 新增 `--fast` 参数，`Makefile` 新增 `make run-tushare-fast`。
  - 快速模式仍会执行完整主链路：数据加载、基金池、特征、评分、组合、回测、核心结果文件和核心报告。
  - 快速模式会跳过当前最重但不影响主回测结果的附加产物：因子评估、因子评估报告、最近两次实验 comparison 刷新。
  - 实验记录会显式标记当前为 fast 模式，避免把“缺少因子评估产物”误读成异常失败。
- 目的：
  - 缩短 `tushare` 全链路日常迭代时间，优先服务“调规则、看组合、看回测”的高频研究动作。
  - 保持主链路金融口径不变，只优化执行路径和附加产物开销。

### 5. 基金池新增 `fund_nav_daily_coverage_monthly` 预计算月表

- 变更内容：
  - `DatasetSnapshot` 与 raw 缓存契约新增 `fund_nav_daily_coverage_monthly`，`sample` 和 `tushare` 都会落盘 `fund_nav_daily_coverage_monthly.csv`。
  - 新增共享预计算逻辑，基于 `fund_nav_pit_daily`、`trade_calendar` 和当前覆盖率窗口，提前生成逐实体逐月的历史日频净值覆盖率。
  - 基金池构建时优先直接读取该月表；只有旧缓存缺失该表或窗口不匹配时，才回退到原先的逐月扫描日频 PIT 逻辑。
  - 新增回归测试，覆盖 raw 回读和“基金池优先使用预计算月表”的路径。
- 目的：
  - 降低 `build_universe()` 在 `tushare` 大样本下反复扫描数百万行日频 PIT 的开销。
  - 保持覆盖率定义、`decision_date` 边界和基金池过滤结果不变，只把计算位置前移到数据层。

### 6. 回测层新增 `prepared_execution_cache` 复用日频执行索引

- 变更内容：
  - 回测引擎新增 `prepare_backtest_execution_cache()` 与 `BacktestExecutionCache`，把交易日索引、实体日收益 lookup、benchmark 日频代理 lookup 和逐月执行日程统一预计算。
  - `run_backtest()` 新增可选 `prepared_execution_cache` 入参；主实验、稳健性分析、候选验证都会优先复用 bundle 中已准备好的 cache。
  - 新增回归测试，验证 prepared cache 路径与旧的直接日频路径产出完全一致。
- 目的：
  - 消除同一实验内主回测、候选验证、稳健性分析对同一份日频 PIT 和交易日历的重复预处理开销。
  - 保持 `T / T+2 / T+3` 执行语义、benchmark 代理方式和金额口径不变，只优化重复构建索引的成本。

### 7. 稳健性分析产物迁移到独立目录

- 变更内容：
  - `analyze-robustness` 不再把 CSV/JSON 写到 `result/`、Markdown 写到 `reports/`。
  - 当前所有稳健性分析产物统一写入 `outputs/<data_source>/robustness/`。
  - `workflow`、测试与核心文档引用已同步更新。
- 目的：
  - 把稳健性分析从主实验结果目录中拆出来，方便后续集中查看与归档。
  - 降低 `result/`、`reports/` 目录里主链路产物与诊断产物混杂的问题。

### 8. 因子评估产物迁移到独立目录

- 变更内容：
  - 完整实验生成的 `factor_evaluation.json/csv`、分布表、分桶表、相关性表和 `factor_evaluation_report.md` 不再写入 `result/` 与 `reports/`。
  - 当前统一写入 `outputs/<data_source>/factor_evaluation/`。
  - 主 workflow、测试和核心文档引用已同步调整。
- 目的：
  - 把因子诊断产物从主策略结果目录中拆分出来，便于和回测/组合主产物分层查看。
  - 与 `robustness/`、`candidate_validation/` 的目录组织保持一致。

### 9. 实验对比产物迁移到独立目录

- 变更内容：
  - `comparison_summary.json`、`backtest_summary_diff.json`、`type_baseline_diff.json`、`portfolio_diff.csv` 与 `comparison_report.md` 不再写入 `result/` 与 `reports/`。
  - 当前统一写入 `outputs/<data_source>/comparison/`。
  - 自动 comparison 刷新、测试和核心文档引用已同步调整。
- 目的：
  - 把“最近两次实验比较”的差异产物从主结果目录中拆分出来，降低 `result/` 和 `reports/` 的信息混杂。
  - 与 `robustness/`、`factor_evaluation/`、`candidate_validation/` 的目录组织保持一致。

### 10. 同步修正文档入口中的旧口径与旧路径

- 变更内容：
  - `README.md` 的默认回测节奏改为当前真实口径：下月第 1 个交易日决策，`T` 卖出、`T+2` 到账、`T+3` 新组合开始承担收益。
  - 修正 `README.md` 与 `experiment_guide.md` 中已经不存在的 `2026-03-24` 文档链接。
  - 修正 `experiment_guide.md` 中仍指向旧 `outputs/clean`、`outputs/result`、`outputs/reports` 根目录的示例路径，统一改为 `outputs/<data_source>/...`。
  - 补充 `fund_nav_daily_coverage_monthly.csv` 在实验产物清单中的位置。
  - `architecture.md` 的基金池与回测分层说明同步更新为当前真实实现，不再保留“信号月末生成、下一月收益直接作为执行结果”的旧描述。
- 目的：
  - 避免协作者继续按旧路径或旧回测口径解读当前产物。
  - 让入口文档、架构说明和实验指南与当前代码实现保持一致。

### 11. 新增 `tushare_scoring_v4` 候选评分配置

- 变更内容：
  - 新增 [`configs/archive/factor_research/tushare_scoring_v4.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/archive/factor_research/tushare_scoring_v4.json)。
  - `v4` 保持基金池、回测执行代理、benchmark 与组合约束不变，只调整评分体系。
  - 收益层改为以 `excess_ret_12m` 为主、`excess_consistency_12m` 为辅。
  - 风险层改为以 `drawdown_duration_ratio_12m` 为主、`drawdown_recovery_ratio_12m` 为辅。
  - 稳定层暂以 `hit_rate_12m` 与 `manager_tenure_months` 组成轻量补充，不再把当前样本中方向不稳定的规模稳定因子放进主线。
- 目的：
  - 基于当前因子评价结果，减少 `ret_12m` 与 `excess_ret_12m` 的重复加权。
  - 避免继续重押 bucket 结果不支持的波动/规模稳定因子。
  - 形成一版改动点清晰、便于与当前 baseline 做 A/B 对比的正式候选配置。

## 2026-03-29

### 1. 新增本地只读研究网站

- 变更内容：
  - 新增 `serve-web` CLI 命令与 `make serve-web-sample`、`make serve-web-tushare` 入口。
  - 新增 `src/fund_research_v2/web/viewer.py`，提供本地 HTTP 服务、只读视图装配、基础 Markdown 渲染和回测累计曲线展示。
  - 新增网站回归测试，覆盖 CLI 分发、已生成产物的页面展示和缺失产物的降级提示。
  - `README.md`、`architecture.md` 同步补充网站使用方式与展示层边界说明。
- 目的：
  - 让现有 `csv`、`json`、`markdown` 产物可以直接在浏览器中查看和分析。
  - 在不引入新前端栈、不改变研究输出契约的前提下，增加一个可持续维护的本地只读展示层。

## 2026-03-27

### 1. 将 `v2-lite` 正式升级为默认 baseline，并补齐 `10000` 样本决策记录

- 变更内容：
  - [`configs/tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json) 的评分结构正式对齐到 `v2-lite`。
  - 新增 [`v2_lite_baseline_review_2026-03-27.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_lite_baseline_review_2026-03-27.md)。
  - 新增 [`v2_lite_execution_risk_note_2026-03-27.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_lite_execution_risk_note_2026-03-27.md)。
  - 基于 `requested_max_funds = 10000` 的最新数据快照，重跑 baseline、`v2-lite`、`analyze-robustness` 与 `validate-baseline-candidate`。
  - `README.md` 同步补充最新评审记录入口。
- 目的：
  - 避免继续沿用 `5000` 样本阶段的评审结论，导致升级判断落后于当前样本规模。
  - 在 `10000` 样本、固定市场 benchmark、补齐执行风险说明后，正式把 `v2-lite` 升级为默认 baseline。

## 2026-03-26

### 1. 将 `tushare_scoring_v2_lite` 提升为当前主候选评分体系

- 变更内容：
  - 新增 [`configs/archive/factor_research/tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/archive/factor_research/tushare_scoring_v2_lite.json)。
  - 新增 [`v2_lite_baseline_review_2026-03-26.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_lite_baseline_review_2026-03-26.md)。
  - `README.md` 中将 `v2-lite` 标记为当前主候选，旧 `v2` 降为历史参考候选。
  - 候选补证文案去掉了对固定名称 `v2` 的硬编码，避免 `v2-lite` 报告误导。
- 目的：
  - 在当前真实样本与中证800 benchmark 口径下，验证删除 `manager_post_change_excess_delta_12m` 后的候选是否更优。
  - 把当前最值得继续跟踪的候选从旧 `v2` 收敛到更干净的 `v2-lite`。

### 2. 把回测主 benchmark 口径统一改回固定市场 benchmark

- 变更内容：
  - 回测中的 `benchmark_return` 不再按组合持仓权重动态聚合各类型 benchmark。
  - 主回测口径固定使用 `benchmark.default_key` 对应的市场 benchmark。
  - `backtest_report.md` 不再展示 `benchmark_mix`。
  - `backtest_conventions.md`、`data_contracts.md`、`data_dictionary.md` 同步更新 benchmark 说明。
- 目的：
  - 修复 `benchmark_cumulative_return` 会随组合结构、未满仓权重和扩样本变化而漂移的设计缺陷。
  - 让 `benchmark_cumulative_return` 与 `excess_cumulative_return` 恢复为跨实验稳定、可解释的固定市场 benchmark 口径。

### 3. 新增因子迭代框架文档

- 变更内容：
  - 新增 [`factor_iteration_framework.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_iteration_framework.md)。
  - `README.md` 中补充该文档索引。
- 目的：
  - 把“哪些因子该进入主候选评分体系、如何做竞争位替换、如何小步迭代”的方法单独沉淀成协作文档。
  - 让评分体系优化从临场讨论，收敛为可复用的固定框架。

## 2026-03-24

### 1. 把偏股混合的默认 benchmark 映射从沪深300切回中证800

- 变更内容：
  - `tushare`、`tushare_scoring_v2`、`tushare_scoring_v3` 与 `default` 配置中，`偏股混合` 的 `benchmark.primary_type_map` 从 `large_cap_equity` 调整为 `broad_equity`。
  - `README.md`、`factor_catalog.md` 与 `data_dictionary.md` 中同步更新默认映射说明。
- 目的：
  - 基于现有真实样本下近 36 个月日频贴近度旁路结果，降低把大多数 `偏股混合` 统一映射到沪深300带来的风格错配。
  - 先把 `偏股混合` 的默认 benchmark 调整为更中性的中证800，再为后续 300/800 动态二分映射预留空间。

### 2. 新增候选 baseline 补证命令与独立产物目录

- 变更内容：
  - 新增 `validate-baseline-candidate` CLI 命令与 `make validate-tushare-v2` 入口。
  - 新增 [`candidate_validation_spec.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)。
  - 新增 `src/fund_research_v2/evaluation/candidate_validation.py` 与 `src/fund_research_v2/reporting/candidate_validation_reports.py`。
  - A/B 两项补证产物统一写入 `outputs/<data_source>/candidate_validation/`。
  - `.gitignore` 明确忽略 `outputs/*/candidate_validation/`。
- 目的：
  - 把“风格/阶段集中性”和“beta vs selection 归因”变成标准 CLI 产物，而不是临时分析。
  - 让 A/B 补证和常规 `result/`、`reports/` 产物分层，降低协作时的阅读混淆。

### 3. 修复 `comparison_report` 容易陈旧的问题

- 变更内容：
  - `run-experiment` 在成功写入新的实验记录后，会自动刷新当前数据源下最近两次实验的 comparison 产物。
  - [`comparison_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/comparison_report.md) 头部新增时效性说明与 `previous/current_generated_at` 字段。
  - [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md) 补充 comparison 产物的语义边界和阅读提示。
- 目的：
  - 防止实验登记已经追加新记录，但 `comparison_report.md` 仍停在旧一轮。
  - 降低协作者把单文件 comparison 报告误读为“当前最新官方对比结论”的风险。

### 4. 新增候选评分稳健性分析说明文档

- 变更内容：
  - 新增 [`robustness_analysis.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)。
  - 在 [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md) 和 [`README.md`](/Users/liupeng/.codex/projects/fund_research_v2/README.md) 中补充入口说明。
- 目的：
  - 把 `analyze-robustness` 的诊断逻辑、flag 含义、输出字段和使用边界讲清楚。
  - 降低人类协作者把 `robustness_report.md` 当成“自动升级结论”的误读风险。

### 5. 新增 baseline 升级决策清单

- 变更内容：
  - 新增 [`baseline_upgrade_checklist.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md)。
  - 在 [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md) 和 [`README.md`](/Users/liupeng/.codex/projects/fund_research_v2/README.md) 中补充入口说明。
- 目的：
  - 把“候选配置是否升级为默认 baseline”的判断标准单独沉淀成一页清单。
  - 让评审时优先比较证据质量，而不是只盯单次收益提升。

### 6. 补充 `tushare_scoring_v2` 的 baseline 升级评审记录

- 变更内容：
  - 新增 [`v2_baseline_review_2026-03-25.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_baseline_review_2026-03-25.md)。
  - 在 [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md) 和 [`README.md`](/Users/liupeng/.codex/projects/fund_research_v2/README.md) 中补充索引。
- 目的：
  - 把这次关于 `v2` 是否升级 baseline 的讨论按中证800新口径沉淀成正式记录。
  - 避免后续重复回忆口头结论，或把“主候选基线”误读为“已升级默认 baseline”。

### 7. 新增 `v2` 最小验证实施计划

- 变更内容：
  - 新增 [`v2_min_validation_plan_2026-03-24.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/v2_min_validation_plan_2026-03-24.md)。
  - 在 [`README.md`](/Users/liupeng/.codex/projects/fund_research_v2/README.md) 中补充索引。
- 目的：
  - 把“`v2` 还差哪一步证据”进一步收敛成最小实施计划。
  - 避免后续验证重新发散成无边界的策略优化讨论。

## 2026-03-19

### 1. 修复 `sample` / `tushare` 缓存串仓

- 变更内容：
  - 为 `data/raw` 缓存增加数据源与 benchmark 口径校验。
- 目的：
  - 防止运行 `tushare` 流程时误读旧的 `sample` 快照。

### 2. 接入 `tushare` 指数基准并落地为中证800

- 变更内容：
  - 使用 `index_daily` 构建真实月度 benchmark。
  - 默认 benchmark 配置为 `000906.SH`，即中证800。
- 目的：
  - 用常规市场 benchmark 替代样例基准，先保证研究主线有真实可比对象。

### 3. 修复经理任期月数口径

- 变更内容：
  - `manager_tenure_months` 改为优先使用真实 `manager_start_month`。
  - 对未来日期、缺失日期和非法日期增加回退与截断处理。
- 目的：
  - 让经理稳定性相关因子不再依赖粗糙近似。

### 4. 补齐组合独立流程

- 变更内容：
  - 新增 `run-portfolio` 命令。
  - 新增 `portfolio-sample` 与 `portfolio-tushare` 的 `make` 入口。
  - 输出组合 CSV、组合快照与组合报告。
- 目的：
  - 支持“不跑回测，只看当前组合建议”的工作模式。

### 5. 重写 `README` 并统一为中文文档

- 变更内容：
  - 重写 [`README.md`](/Users/liupeng/.codex/projects/fund_research_v2/README.md)。
  - 增加首次阅读代码建议路径。
  - 统一使用 `make` 命令说明。
- 目的：
  - 提升项目可读性与协作上手效率。

### 6. 为 `src/` 增补中文注释与文档字符串

- 变更内容：
  - 为模块、类、函数、方法增加中文注释与 docstring。
  - 注释重点解释金融语义、时间边界和工程约束。
- 目的：
  - 让协作者能直接理解研究口径，而不是只看到实现细节。

### 7. 修复 `run-experiment` 未刷新组合报告的问题

- 变更内容：
  - 抽出统一的 `write_portfolio_outputs()`。
  - 让完整实验与独立组合流程写出同一套组合产物。
- 目的：
  - 消除 `portfolio_report.md`、`portfolio_snapshot.json` 与实验报告之间的口径不一致。

### 8. 拉开 `portfolio_report` 与 `experiment_report` 的职责边界

- 变更内容：
  - `portfolio_report` 强化当期组合决策解释。
  - `experiment_report` 强化实验上下文、数据快照与回测摘要。
- 目的：
  - 避免两份报告内容高度重复，提升可读性。

### 9. 新增基金池审计报告

- 变更内容：
  - 新增 [`universe_audit_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/reports/universe_audit_report.md)。
  - 自动输出最新月漏斗、剔除原因计数、可投基金清单、被规模门槛阻挡基金清单。
- 目的：
  - 把“59 个主体为什么只剩 7 个可投”变成可审计的标准产物。

### 10. 修复基金实体规模口径

- 变更内容：
  - 规模不再取代表份额，而是同一实体下各份额月度规模求和。
  - 新增缓存版本字段 `entity_asset_aggregation = sum_of_share_classes`。
- 目的：
  - 让基金池规模筛选和规模稳定性特征真正基于“基金实体”而不是“代表份额”。

### 11. 增补测试与协作文档

- 变更内容：
  - 新增缓存校验、组合输出、基金池审计、实体规模汇总等回归测试。
  - 新增 [`docs/error_log.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/error_log.md) 与 [`docs/changes.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/changes.md)。
- 目的：
  - 让本轮迭代具备更好的可验证性和可追踪性。

### 12. 新增字段可得性审计主线与因子研究框架

- 变更内容：
  - 新增 CLI 命令 `audit-field-availability`，输出 `outputs/<data_source>/factor_research/field_availability_audit.csv`、`field_availability_summary.json` 与 `field_availability_report.md`。
  - 新增 [`factor_research_framework.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_research_framework.md)，把字段审计、单因子评价、增量贡献测试、组合层验证和 baseline 升级决策串成统一研究流程。
  - `README.md` 同步加入新的研究框架文档索引。
- 目的：
  - 先补齐“字段是否历史可得”和“单因子如何进入正式评分体系”的研究底座，再推进下一版候选评分体系。

### 13. 补齐缺失的协作文档

- 变更内容：
  - 新增 [`docs/factor_catalog.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_catalog.md)
  - 新增 [`docs/data_dictionary.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_dictionary.md)
  - 新增 [`docs/experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)
- 目的：
  - 按 `AGENTS.md` 要求补齐字段定义、因子说明和实验管理文档，降低协作理解成本。

### 14. 引入 `available_date` 驱动的净值可得性约束

- 变更内容：
  - 基金池和特征构建改为只使用 `signal_month` 月末前已可见的净值记录。
  - 新增基金池原因码 `no_available_nav_for_month`。
  - 增补对应回归测试与文档说明。
- 目的：
  - 先在净值链路上收紧前视偏差边界，避免未来才披露的数据提前进入信号月。

### 15. 把 benchmark 可得性约束接入 `excess_ret_12m`

- 变更内容：
  - `benchmark_monthly` 增加 `available_date` 口径。
  - `excess_ret_12m` 改为只使用信号月月末前已可见的 benchmark 月收益。
- 目的：
  - 让超额收益因子和净值链路使用同一套时间边界，避免 benchmark 侧前视偏差。

### 16. 把经理任职历史映射到月频研究时间轴

- 变更内容：
  - `DatasetSnapshot` 新增 `manager_assignment_monthly`。
  - `tushare` / `sample` 数据入口都会产出月度经理映射表。
  - `manager_tenure_months` 改为优先使用“该月实际经理”的任职起点计算。
  - clean 层同步落盘 `manager_assignment_monthly.csv`。
- 目的：
  - 避免把当前经理错误地映射到历史月份，提升经理稳定性因子的历史真实性。

### 17. 把基金池规模筛选与审计解释统一为“当月可见规模”

- 变更内容：
  - `fund_universe_monthly` 新增 `visible_history_months`、`fund_age_months`、`visible_assets_cny_mn`、`nav_available_date`。
  - 基金池规模门槛显式使用 `visible_assets_cny_mn`。
  - `universe_audit_report` 改为展示当月可见规模，而不是实体主表中的最新规模。
- 目的：
  - 防止历史月份被“最新规模”错误解释，继续收紧研究时点一致性。

### 18. 为报告与实验阅读补上时点边界审计说明

- 变更内容：
  - `portfolio_report` 与 `experiment_report` 新增 `Time Boundary Notes`。
  - 相关时点边界约束后续已并入 `data_contracts.md`、`backtest_conventions.md` 与 `experiment_guide.md`，不再单独维护独立审计文档。
  - `experiment_guide.md` 增加月度经理映射表与时点边界阅读提示。
- 目的：
  - 防止协作者把静态主表字段误读为历史月份口径，提升结果解释的一致性。

### 19. 把回测引擎改为连续月份回放

- 变更内容：
  - 回测改为按 `start_month ~ end_month` 的完整月历推进。
  - 无评分结果的月份不再静默跳过，而是显式记录为空仓期。
  - 增补连续月份与空仓月份的回归测试。
- 目的：
  - 防止回测月数、收益路径和年化统计因“跳月”而失真。

### 20. 把 raw 与 outputs 目录按数据源隔离

- 变更内容：
  - `sample` 与 `tushare` 现在分别写入 `data/raw/<data_source>/...` 与 `outputs/<data_source>/...`。
  - 工作流、缓存读取、实验记录和测试同步适配新目录结构。
- 目的：
  - 防止跑完 `tushare` 后，又被后续 `sample` 验证流程覆盖产物。

### 21. 新增接入层审计产物

- 变更内容：
  - 在 `dataset_snapshot.metadata` 中增加 `ingestion_audit`。
  - clean 层新增 `dropped_entities.csv`。
  - reports 层新增 `ingestion_audit_report.md`。
- 目的：
  - 把 `fund_basic -> clean` 这段漏斗标准化，直接回答“为什么某些份额/实体没进入 clean 层”。

### 22. 移除默认基金池中的独立 `fund_age` 门槛

- 变更内容：
  - 删除 `min_fund_age_months` 配置与 `fund_too_new` 原因码。
  - `fund_age_months` 仍保留在基金池输出中，仅作为审计字段。
- 目的：
  - 减少和 `min_history_months` 的重复约束，让基金池口径更简洁、更容易解释。

### 23. 把 benchmark 从单序列升级为“多序列 + 基金类型映射”

- 变更内容：
  - `benchmark` 配置改为支持 `default_key`、`series` 与 `primary_type_map`。
  - `benchmark_monthly.csv` 现在以 `benchmark_key + month` 为主键保存多条指数序列。
  - `excess_ret_12m` 改为按 `primary_type` 选择对应 benchmark。
  - 回测中的 `benchmark_return` 改为按组合持仓权重聚合各类型 benchmark。
  - 报告新增 `Benchmark Mapping` 段落，显式展示当前基准映射关系。
- 目的：
  - 解决“主动股票和偏股混合共用同一条 benchmark”过于粗糙的问题。
  - 为后续继续升级更细 benchmark 体系保留稳定配置与数据契约。

### 24. 新增基金类型标准化规则与类型审计产物

- 变更内容：
  - 把基金类型判断从 `providers.py` 中抽离为独立规则模块。
  - 分类输入改为综合使用 `fund_type`、`invest_type`、`fund_name`、`benchmark_text`。
  - clean 层新增 `fund_type_audit.csv`。
  - reports 层新增 `fund_type_audit_report.md`。
- 目的：
  - 解决原先“只要 fund_type 含股票/混合就直接归类”的规则过粗问题。
  - 让基金池准入、benchmark 映射和报告解释都能回溯到同一套可审计分类依据。

### 25. 把 `灵活配置混合` 纳入默认基金池

- 变更内容：
  - `allowed_primary_types` 新增 `灵活配置混合`。
  - benchmark 映射中新增 `灵活配置混合 -> broad_equity -> 中证800`。
  - sample 数据中补入该类型样本，保证默认流程能覆盖新口径。
- 目的：
  - 让主线研究范围从“主动股票 + 偏股混合”扩展到更常见的主动权益混合基金。
  - 同时避免 `灵活配置混合` 继续被混在 `其他` 或被手工例外处理。

### 26. 新增类型对比基线快照

- 变更内容：
  - 在 result 层新增 `type_baseline_snapshot.json`。
  - 在 `experiment_registry.jsonl` 中同步写入 `type_baseline` 摘要。
- 目的：
  - 为后续真实重抓后的类型迁移比较提供机器可读基线。
  - 避免未来只知道“结果变了”，却说不清是基金类型分布、最新月基金池还是可投样本结构发生了变化。

### 27. 新增单因子有效性评估框架

- 变更内容：
  - 在 `evaluation/` 下新增 `factor_evaluator.py`。
  - 完整实验新增 `factor_evaluation.json`、`factor_evaluation.csv` 与 `factor_evaluation_report.md`。
  - 实验记录中新增 `factor_evaluation_summary`。
- 目的：
  - 把“因子是否真的对下一月收益有区分度”变成标准产物，而不是靠人工感觉判断。
  - 为后续淘汰弱因子、重构评分体系提供证据基线。

### 28. 优化 tushare 抓数性能与可观测性

- 变更内容：
  - 为 `fund_manager` 与单份额月频净值请求增加内存缓存，消除重复抓取。
  - 为 Tushare 请求增加统一重试、失败样本记录、接口耗时统计。
  - 为 `fund_nav` 增加默认节流与限频感知退避。
  - 新增 `fetch_diagnostics_report.md`，显式输出抓数耗时与错误样本。
- 目的：
  - 缓解“抓数很慢但不知道慢在哪里、错在哪里”的问题。
  - 为后续扩大真实样本时的分批抓取和限频治理提供观测基础。

### 29. 新增失败项增量补抓工作流

- 变更内容：
  - 新增 CLI 命令 `fetch-failed` 与 `make fetch-failed-tushare`。
  - 根据上一份 raw `dataset_snapshot.json` 中的 `fetch_diagnostics.api_error_samples` 提取失败 `ts_code`。
  - 只对失败份额预热单接口缓存，不重写整份 raw 快照。
  - 新增 `fetch_retry_summary.json` 与 `fetch_retry_report.md`。
  - 增补 CLI 分发与失败补抓结果落盘测试。
- 目的：
  - 避免真实抓数因少量接口失败而被迫整批重来。
  - 先补齐失败接口缓存，再执行全量研究流程，降低重复联网成本并提升可观测性。

### 30. 新增实验对比与回归审计工作流

- 变更内容：
  - 新增 CLI 命令 `compare-experiments`。
  - 新增 `make compare-sample` 与 `make compare-tushare`。
  - 输出 `comparison_report.md`、`comparison_summary.json`、`backtest_summary_diff.json`、`type_baseline_diff.json` 与 `portfolio_diff.csv`。
  - 实验记录中新增 `portfolio_snapshot_summary`，用于稳定比较最新组合变化。
- 目的：
  - 让协作者直接回答“这次结果为什么和上次不一样”，而不是手工翻配置、报告和 CSV。
  - 把配置变化、样本变化、基金类型变化、回测变化与组合变化沉淀成标准审计产物。

### 31. 基金池新增最低持有期流动性过滤

- 变更内容：
  - 新增基金名称驱动的最低持有期识别规则。
  - clean 层新增 `fund_liquidity_audit.csv`。
  - reports 层新增 `fund_liquidity_audit_report.md`。
  - 基金池新增 `holding_period_restricted` 原因码，直接排除最低持有期基金。
- 目的：
  - 当前策略明确要求场外基金月频调仓的资金流动性，因此不在回测中复杂模拟锁定期，而是在基金池前置剔除相关产品。

### 32. 把“正式最新月”统一收敛为最后一个完整自然月

- 变更内容：
  - 在主工作流中新增统一的“正式最新研究月”判断逻辑。
  - `portfolio`、`experiment_report`、`portfolio_report`、`universe_audit_report`、`portfolio_snapshot.json`、`type_baseline_snapshot.json` 不再直接使用 raw 数据中的最大 `month`。
  - 当 `as_of_date` 仍处于月中时，正式最新研究月自动回退到上一个完整月。
  - 同步更新 `README`、`experiment_guide`、`strategy_spec_v1`、`backtest_conventions`、`architecture`、`factor_catalog`、`data_contracts`、`data_dictionary`、`time_boundary_audit`。
- 目的：
  - 避免把尚未走完的当月月内快照误当成正式月末信号。
  - 让组合建议、基金池审计、实验报告与回测口径在时间边界上保持一致。

### 33. 把评分体系升级为“因子集合可配置”，并新增 `tushare_scoring_v2`

- 变更内容：
  - `ranking` 配置新增 `category_factors`，允许分别定义三大评分大类内部使用哪些因子以及类内权重。
  - 评分引擎不再把三大类内部因子集合完全写死在代码里。
  - 对事件类因子缺失值增加中性分 `0.5` 处理，避免真实数据下直接报错。
  - 新增候选配置 [`configs/archive/factor_research/tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/archive/factor_research/tushare_scoring_v2.json)。
- 目的：
  - 让“因子评价 -> 评分优化 -> 对照实验”形成标准工作流，而不是每次都直接改死旧 baseline。
  - 先把更强的候选评分体系以配置形式固化下来，再决定是否替代默认版本。

### 34. 把 `strategy_spec_v1.md` 重构为瘦身版策略总纲

- 变更内容：
  - 删除与 `backtest_conventions`、`factor_catalog`、`experiment_guide`、`data_contracts` 等文档重复的细节规则。
  - `strategy_spec_v1.md` 现在只保留策略版本定位、基金池范围、信号与执行定义、评分体系角色、组合定义、benchmark 定义和版本变更触发条件。
  - 具体实现细节统一改为跳转引用专门文档。
- 目的：
  - 减少多份文档同时维护同一规则带来的重复、漂移和冲突。
  - 让 `strategy_spec_v1.md` 真正承担“策略总纲”职责，而不是变成第二份细则手册。

### 35. 为持有期缺失收益补上显式审计字段

- 变更内容：
  - `backtest` 配置新增 `missing_return_policy` 与 `missing_weight_warning_threshold`。
  - `backtest_monthly.csv` 新增 `missing_weight`、`missing_position_count`、`low_confidence_flag` 与 `return_validity`。
  - result 层新增 `backtest_position_audit.csv`。
  - `backtest_summary.json` 与 `backtest_report.md` 新增缺失收益诊断指标。
- 目的：
  - 保留旧版“缺失收益按 0 计”的兼容口径，同时把持有期缺失收益从黑盒处理升级为可审计结果。
  - 为后续更严格的缺失收益处理和生命周期事件建模预留稳定接口。

### 36. 新增第二批观察层候选因子

- 变更内容：
  - `feature_builder.py` 新增 `excess_streak_6m`、`drawdown_duration_ratio_12m`、`manager_post_change_downside_vol_delta_12m`、`asset_flow_volatility_12m`。
  - `factor_evaluator.py` 把上述字段纳入标准单因子评估与相关性诊断。
  - `tests/test_pipeline.py` 增补第二批观察因子回归测试。
  - `factor_catalog.md` 同步补充 4 个观察层字段说明。
- 目的：
  - 继续在“观察层”扩充候选因子，但先不直接进入评分体系。
  - 优先补足路径连续性、回撤拖延、换帅后风险变化和资金流波动等与现有动量幅度因子不完全重合的观察维度。

### 37. 重组 `tushare_scoring_v2` 候选评分体系

- 变更内容：
  - `performance_quality` 引入 `excess_hit_rate_12m`，并下调 `ret_12m` 权重。
  - `stability_quality` 用 `asset_flow_volatility_12m` 替换 `asset_stability_12m`，保留 `manager_post_change_excess_delta_12m` 的弱权重事件补充。
  - 同步更新 `factor_catalog.md` 中的 `tushare_scoring_v2` 说明。
- 目的：
  - 在不改默认 baseline 的前提下，把“保留观察”的新因子纳入候选评分体系做真实对照。
  - 尽量减少与旧候选体系中高相关字段的重复暴露。

### 38. 拆分 `tushare_scoring_v2` 与 `tushare_scoring_v3`

- 变更内容：
  - 将 [`tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/archive/factor_research/tushare_scoring_v2.json) 恢复为上一版表现更强的候选评分配置。
  - 新增 [`tushare_scoring_v3.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/archive/factor_research/tushare_scoring_v3.json)，承接本轮把 `excess_hit_rate_12m` 与 `asset_flow_volatility_12m` 纳入评分体系的实验配置。
  - 同步更新 `factor_catalog.md` 的 `v2` / `v3` 说明。
- 目的：
  - 保留历史上表现更好的 `v2` 作为稳定候选基线。
  - 让后续新因子评分实验在 `v3` 上独立迭代，避免反复覆盖旧对照配置。

### 39. 新增候选评分稳健性验证工作流

- 变更内容：
  - 新增 CLI 命令 `analyze-robustness`。
  - 新增 [`evaluation/robustness.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/evaluation/robustness.py) 与 [`reporting/robustness_reports.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/reporting/robustness_reports.py)。
  - result 层新增 `robustness_summary.json`、`robustness_time_slices.csv`、`robustness_month_contribution.csv`、`robustness_portfolio_behavior.csv`、`robustness_factor_regime.csv`。
  - reports 层新增 `robustness_report.md`。
  - `experiment_guide.md` 同步补充命令与产物说明。
- 目的：
  - 在不改变基金池、评分、组合和回测逻辑的前提下，验证候选评分体系的收益是否集中于少数阶段、少数月份或更激进的组合行为。

### 40. 修正新观察层字段进入评分体系时的方向映射

- 变更内容：
  - 在 [`scoring_engine.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/ranking/scoring_engine.py) 中补齐 `excess_hit_rate_12m`、`asset_flow_volatility_12m` 等新字段的方向定义。
  - 增补对应回归测试，避免候选配置中引用新字段时被错误按默认高值方向处理。
- 目的：
  - 防止 `v3` 这类实验配置在接入新观察层因子后，因方向表缺失而得到错误评分结果。

### 41. 升级因子评价输出为研究评分卡

- 变更内容：
  - 在 [`factor_evaluator.py`](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/evaluation/factor_evaluator.py) 中新增因子研究元数据和评分卡生成逻辑。
  - 因子评价结果除了原有统计诊断外，新增 `scorecard_rows`，每个因子输出语义合理性、时间边界洁净度、排序能力、时变稳定性、覆盖质量、风格解释、研究角色和准入结论。
  - 完整实验新增产物 [`factor_research_scorecard.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/factor_evaluation/factor_research_scorecard.csv)。
  - [`factor_evaluation_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/factor_evaluation/factor_evaluation_report.md) 新增 `Research Scorecard` 段落。
  - [`data_contracts.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_contracts.md) 与 [`experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md) 同步补充新产物说明。
- 目的：
  - 让现有单因子评价不再只是统计展示，而是能直接支撑因子准入、观察层保留和淘汰判断。


