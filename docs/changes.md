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
