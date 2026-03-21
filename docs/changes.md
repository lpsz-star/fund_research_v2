# 变更记录

本文档按主题记录已经落地的主要改动，重点说明“改了什么”以及“为什么改”。

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

### 12. 补齐缺失的协作文档

- 变更内容：
  - 新增 [`docs/factor_catalog.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_catalog.md)
  - 新增 [`docs/data_dictionary.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_dictionary.md)
  - 新增 [`docs/experiment_guide.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)
- 目的：
  - 按 `AGENTS.md` 要求补齐字段定义、因子说明和实验管理文档，降低协作理解成本。

### 13. 引入 `available_date` 驱动的净值可得性约束

- 变更内容：
  - 基金池和特征构建改为只使用 `signal_month` 月末前已可见的净值记录。
  - 新增基金池原因码 `no_available_nav_for_month`。
  - 增补对应回归测试与文档说明。
- 目的：
  - 先在净值链路上收紧前视偏差边界，避免未来才披露的数据提前进入信号月。

### 14. 把 benchmark 可得性约束接入 `excess_ret_12m`

- 变更内容：
  - `benchmark_monthly` 增加 `available_date` 口径。
  - `excess_ret_12m` 改为只使用信号月月末前已可见的 benchmark 月收益。
- 目的：
  - 让超额收益因子和净值链路使用同一套时间边界，避免 benchmark 侧前视偏差。

### 15. 把经理任职历史映射到月频研究时间轴

- 变更内容：
  - `DatasetSnapshot` 新增 `manager_assignment_monthly`。
  - `tushare` / `sample` 数据入口都会产出月度经理映射表。
  - `manager_tenure_months` 改为优先使用“该月实际经理”的任职起点计算。
  - clean 层同步落盘 `manager_assignment_monthly.csv`。
- 目的：
  - 避免把当前经理错误地映射到历史月份，提升经理稳定性因子的历史真实性。

### 16. 把基金池规模筛选与审计解释统一为“当月可见规模”

- 变更内容：
  - `fund_universe_monthly` 新增 `visible_history_months`、`fund_age_months`、`visible_assets_cny_mn`、`nav_available_date`。
  - 基金池规模门槛显式使用 `visible_assets_cny_mn`。
  - `universe_audit_report` 改为展示当月可见规模，而不是实体主表中的最新规模。
- 目的：
  - 防止历史月份被“最新规模”错误解释，继续收紧研究时点一致性。

### 17. 为报告与实验阅读补上时点边界审计说明

- 变更内容：
  - `portfolio_report` 与 `experiment_report` 新增 `Time Boundary Notes`。
  - 新增 [`time_boundary_audit.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/time_boundary_audit.md)。
  - `experiment_guide.md` 增加月度经理映射表与时点边界阅读提示。
- 目的：
  - 防止协作者把静态主表字段误读为历史月份口径，提升结果解释的一致性。

### 18. 把回测引擎改为连续月份回放

- 变更内容：
  - 回测改为按 `start_month ~ end_month` 的完整月历推进。
  - 无评分结果的月份不再静默跳过，而是显式记录为空仓期。
  - 增补连续月份与空仓月份的回归测试。
- 目的：
  - 防止回测月数、收益路径和年化统计因“跳月”而失真。

### 19. 把 raw 与 outputs 目录按数据源隔离

- 变更内容：
  - `sample` 与 `tushare` 现在分别写入 `data/raw/<data_source>/...` 与 `outputs/<data_source>/...`。
  - 工作流、缓存读取、实验记录和测试同步适配新目录结构。
- 目的：
  - 防止跑完 `tushare` 后，又被后续 `sample` 验证流程覆盖产物。

### 20. 新增接入层审计产物

- 变更内容：
  - 在 `dataset_snapshot.metadata` 中增加 `ingestion_audit`。
  - clean 层新增 `dropped_entities.csv`。
  - reports 层新增 `ingestion_audit_report.md`。
- 目的：
  - 把 `fund_basic -> clean` 这段漏斗标准化，直接回答“为什么某些份额/实体没进入 clean 层”。

### 21. 移除默认基金池中的独立 `fund_age` 门槛

- 变更内容：
  - 删除 `min_fund_age_months` 配置与 `fund_too_new` 原因码。
  - `fund_age_months` 仍保留在基金池输出中，仅作为审计字段。
- 目的：
  - 减少和 `min_history_months` 的重复约束，让基金池口径更简洁、更容易解释。

### 22. 把 benchmark 从单序列升级为“多序列 + 基金类型映射”

- 变更内容：
  - `benchmark` 配置改为支持 `default_key`、`series` 与 `primary_type_map`。
  - `benchmark_monthly.csv` 现在以 `benchmark_key + month` 为主键保存多条指数序列。
  - `excess_ret_12m` 改为按 `primary_type` 选择对应 benchmark。
  - 回测中的 `benchmark_return` 改为按组合持仓权重聚合各类型 benchmark。
  - 报告新增 `Benchmark Mapping` 段落，显式展示当前基准映射关系。
- 目的：
  - 解决“主动股票和偏股混合共用同一条 benchmark”过于粗糙的问题。
  - 为后续继续升级更细 benchmark 体系保留稳定配置与数据契约。

### 23. 新增基金类型标准化规则与类型审计产物

- 变更内容：
  - 把基金类型判断从 `providers.py` 中抽离为独立规则模块。
  - 分类输入改为综合使用 `fund_type`、`invest_type`、`fund_name`、`benchmark_text`。
  - clean 层新增 `fund_type_audit.csv`。
  - reports 层新增 `fund_type_audit_report.md`。
- 目的：
  - 解决原先“只要 fund_type 含股票/混合就直接归类”的规则过粗问题。
  - 让基金池准入、benchmark 映射和报告解释都能回溯到同一套可审计分类依据。

### 24. 把 `灵活配置混合` 纳入默认基金池

- 变更内容：
  - `allowed_primary_types` 新增 `灵活配置混合`。
  - benchmark 映射中新增 `灵活配置混合 -> broad_equity -> 中证800`。
  - sample 数据中补入该类型样本，保证默认流程能覆盖新口径。
- 目的：
  - 让主线研究范围从“主动股票 + 偏股混合”扩展到更常见的主动权益混合基金。
  - 同时避免 `灵活配置混合` 继续被混在 `其他` 或被手工例外处理。

### 25. 新增类型对比基线快照

- 变更内容：
  - 在 result 层新增 `type_baseline_snapshot.json`。
  - 在 `experiment_registry.jsonl` 中同步写入 `type_baseline` 摘要。
- 目的：
  - 为后续真实重抓后的类型迁移比较提供机器可读基线。
  - 避免未来只知道“结果变了”，却说不清是基金类型分布、最新月基金池还是可投样本结构发生了变化。

### 26. 新增单因子有效性评估框架

- 变更内容：
  - 在 `evaluation/` 下新增 `factor_evaluator.py`。
  - 完整实验新增 `factor_evaluation.json`、`factor_evaluation.csv` 与 `factor_evaluation_report.md`。
  - 实验记录中新增 `factor_evaluation_summary`。
- 目的：
  - 把“因子是否真的对下一月收益有区分度”变成标准产物，而不是靠人工感觉判断。
  - 为后续淘汰弱因子、重构评分体系提供证据基线。

### 27. 优化 tushare 抓数性能与可观测性

- 变更内容：
  - 为 `fund_manager` 与单份额月频净值请求增加内存缓存，消除重复抓取。
  - 为 Tushare 请求增加统一重试、失败样本记录、接口耗时统计。
  - 为 `fund_nav` 增加默认节流与限频感知退避。
  - 新增 `fetch_diagnostics_report.md`，显式输出抓数耗时与错误样本。
- 目的：
  - 缓解“抓数很慢但不知道慢在哪里、错在哪里”的问题。
  - 为后续扩大真实样本时的分批抓取和限频治理提供观测基础。

### 28. 新增失败项增量补抓工作流

- 变更内容：
  - 新增 CLI 命令 `fetch-failed` 与 `make fetch-failed-tushare`。
  - 根据上一份 raw `dataset_snapshot.json` 中的 `fetch_diagnostics.api_error_samples` 提取失败 `ts_code`。
  - 只对失败份额预热单接口缓存，不重写整份 raw 快照。
  - 新增 `fetch_retry_summary.json` 与 `fetch_retry_report.md`。
  - 增补 CLI 分发与失败补抓结果落盘测试。
- 目的：
  - 避免真实抓数因少量接口失败而被迫整批重来。
  - 先补齐失败接口缓存，再执行全量研究流程，降低重复联网成本并提升可观测性。

### 29. 新增实验对比与回归审计工作流

### 30. 把“正式最新月”统一收敛为最后一个完整自然月

- 变更内容：
  - 在主工作流中新增统一的“正式最新研究月”判断逻辑。
  - `portfolio`、`experiment_report`、`portfolio_report`、`universe_audit_report`、`portfolio_snapshot.json`、`type_baseline_snapshot.json` 不再直接使用 raw 数据中的最大 `month`。
  - 当 `as_of_date` 仍处于月中时，正式最新研究月自动回退到上一个完整月。
  - 同步更新 `README`、`experiment_guide`、`strategy_spec_v1`、`backtest_conventions`、`architecture`、`factor_catalog`、`data_contracts`、`data_dictionary`、`time_boundary_audit`。
- 目的：
  - 避免把尚未走完的当月月内快照误当成正式月末信号。
  - 让组合建议、基金池审计、实验报告与回测口径在时间边界上保持一致。

### 31. 把评分体系升级为“因子集合可配置”，并新增 `tushare_scoring_v2`

- 变更内容：
  - `ranking` 配置新增 `category_factors`，允许分别定义三大评分大类内部使用哪些因子以及类内权重。
  - 评分引擎不再把三大类内部因子集合完全写死在代码里。
  - 对事件类因子缺失值增加中性分 `0.5` 处理，避免真实数据下直接报错。
  - 新增候选配置 [`configs/tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)。
- 目的：
  - 让“因子评价 -> 评分优化 -> 对照实验”形成标准工作流，而不是每次都直接改死旧 baseline。
  - 先把更强的候选评分体系以配置形式固化下来，再决定是否替代默认版本。

### 32. 把 `strategy_spec_v1.md` 重构为瘦身版策略总纲

- 变更内容：
  - 删除与 `backtest_conventions`、`factor_catalog`、`experiment_guide`、`data_contracts` 等文档重复的细节规则。
  - `strategy_spec_v1.md` 现在只保留策略版本定位、基金池范围、信号与执行定义、评分体系角色、组合定义、benchmark 定义和版本变更触发条件。
  - 具体实现细节统一改为跳转引用专门文档。
- 目的：
  - 减少多份文档同时维护同一规则带来的重复、漂移和冲突。
  - 让 `strategy_spec_v1.md` 真正承担“策略总纲”职责，而不是变成第二份细则手册。

- 变更内容：
  - 新增 CLI 命令 `compare-experiments`。
  - 新增 `make compare-sample` 与 `make compare-tushare`。
  - 输出 `comparison_report.md`、`comparison_summary.json`、`backtest_summary_diff.json`、`type_baseline_diff.json` 与 `portfolio_diff.csv`。
  - 实验记录中新增 `portfolio_snapshot_summary`，用于稳定比较最新组合变化。
- 目的：
  - 让协作者直接回答“这次结果为什么和上次不一样”，而不是手工翻配置、报告和 CSV。
  - 把配置变化、样本变化、基金类型变化、回测变化与组合变化沉淀成标准审计产物。

### 30. 基金池新增最低持有期流动性过滤

- 变更内容：
  - 新增基金名称驱动的最低持有期识别规则。
  - clean 层新增 `fund_liquidity_audit.csv`。
  - reports 层新增 `fund_liquidity_audit_report.md`。
  - 基金池新增 `holding_period_restricted` 原因码，直接排除最低持有期基金。
- 目的：
  - 当前策略明确要求场外基金月频调仓的资金流动性，因此不在回测中复杂模拟锁定期，而是在基金池前置剔除相关产品。
