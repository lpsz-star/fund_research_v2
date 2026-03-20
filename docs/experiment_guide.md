# 实验管理说明

本文档说明如何运行、记录、比较和解释一次研究实验。
目标不是介绍所有实现细节，而是保证不同协作者在运行实验时遵循同一套最小流程。

## 1. 什么是一次实验

在本项目里，一次实验指的是：

- 固定一份配置
- 固定一份数据快照
- 固定一套代码逻辑
- 运行完整研究链路
- 产出组合、回测、报告与实验记录

这意味着：

- 不是单独跑某个函数就算实验
- 也不是手工改 CSV 再看结果
- 而是通过标准命令生成一套可审计产物

## 2. 标准实验入口

当前标准完整实验命令：

```bash
make run-sample
make run-tushare
```

当真实抓数上一次只失败了少量份额接口时，允许先走失败增量补抓：

```bash
make fetch-failed-tushare
make run-tushare
```

这一步的目的不是直接生成完整 clean/result 产物，而是先把上次失败的单接口缓存补齐，避免下一次全量实验再次从零联网重抓。

对应 CLI：

```bash
PYTHONPATH=src python3 -m fund_research_v2 run-experiment --config configs/default.json
PYTHONPATH=src python3 -m fund_research_v2 run-experiment --config configs/tushare.json
```

## 3. 一次完整实验会产出什么

运行完整实验后，当前会写出以下产物：

- 当前所有产物按数据源隔离到 `outputs/<data_source>/...`
- `sample` 默认查看 `outputs/sample/...`
- `tushare` 默认查看 `outputs/tushare/...`
- 若要解释 clean 层之前为什么丢掉基金，请优先查看 `ingestion_audit_report.md`
- 若要排查真实抓数慢点或接口报错，请优先查看 `fetch_diagnostics_report.md`

### 3.1 清洗层

- [`fund_entity_master.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/clean/fund_entity_master.csv)
- [`fund_share_class_map.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/clean/fund_share_class_map.csv)
- [`fund_nav_monthly.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/clean/fund_nav_monthly.csv)
- [`benchmark_monthly.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/clean/benchmark_monthly.csv)
- [`manager_assignment_monthly.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/clean/manager_assignment_monthly.csv)
- [`fund_universe_monthly.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/clean/fund_universe_monthly.csv)
- [`dataset_snapshot.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/clean/dataset_snapshot.json)

### 3.2 特征与结果层

- [`fund_feature_monthly.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/feature/fund_feature_monthly.csv)
- [`fund_score_monthly.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/result/fund_score_monthly.csv)
- [`portfolio_target_monthly.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/result/portfolio_target_monthly.csv)
- [`portfolio_snapshot.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/result/portfolio_snapshot.json)
- [`backtest_monthly.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/result/backtest_monthly.csv)
- [`backtest_summary.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/result/backtest_summary.json)
- [`factor_evaluation.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/result/factor_evaluation.json)
- [`factor_evaluation.csv`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/result/factor_evaluation.csv)
- [`type_baseline_snapshot.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/result/type_baseline_snapshot.json)

### 3.3 报告层

- [`portfolio_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/reports/portfolio_report.md)
- [`experiment_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/reports/experiment_report.md)
- [`backtest_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/reports/backtest_report.md)
- [`universe_audit_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/reports/universe_audit_report.md)
- [`factor_evaluation_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/reports/factor_evaluation_report.md)

### 3.4 实验追踪层

- [`experiment_registry.jsonl`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/experiments/experiment_registry.jsonl)

## 4. 如何判断两次实验是否可比

两次实验只有在以下条件都一致时，才适合直接比较：

1. 配置一致
2. 数据快照口径一致
3. benchmark 一致
4. 代码逻辑一致
5. 成本口径一致
6. 基金类型基线一致

至少要核对：

- `config`
- `dataset_snapshot`
- `benchmark_name`
- `benchmark_source`
- `benchmark_ts_code`
- `type_baseline`
- `entity_asset_aggregation`
- `backtest.transaction_cost_bps`

如果其中任一项变化，都应视为“新口径实验”，不能把结果当成同一 baseline 的连续版本。

## 5. 当前推荐实验流程

### 5.1 首次运行 sample

用于验证工程链路是否完整：

```bash
make run-sample
```

建议检查：

- 报告是否全部生成
- 测试是否通过
- 实验登记是否写入

### 5.2 运行真实数据实验

使用 `tushare` 数据：

```bash
make run-tushare
```

如果上一次抓数日志显示失败集中在少量 `ts_code`，建议先执行：

```bash
make fetch-failed-tushare
```

增量补抓后重点查看：

- [`fetch_retry_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/fetch_retry_report.md)
- [`fetch_retry_summary.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/result/fetch_retry_summary.json)

建议优先检查：

- [`dataset_snapshot.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/clean/dataset_snapshot.json)
- [`universe_audit_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/universe_audit_report.md)
- [`fetch_diagnostics_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/fetch_diagnostics_report.md)
- [`portfolio_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/reports/portfolio_report.md)
- [`backtest_summary.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/tushare/result/backtest_summary.json)

## 6. 实验阅读顺序建议

如果你要理解一次实验结果，建议按以下顺序阅读：

1. [`dataset_snapshot.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/clean/dataset_snapshot.json)
   - 先确认数据源、样本范围、benchmark 和规模口径
2. [`time_boundary_audit.md`](/Users/liupeng/.codex/projects/fund_research_v2/docs/time_boundary_audit.md)
   - 先确认哪些字段能解释历史月份，哪些只是最新快照
3. [`universe_audit_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/reports/universe_audit_report.md)
   - 确认基金池是如何收缩的
4. [`type_baseline_snapshot.json`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/result/type_baseline_snapshot.json)
   - 看基金主体、最新月基金池和最新月可投基金在各 `primary_type` 上的分布
5. [`portfolio_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/reports/portfolio_report.md)
   - 看当前组合建议和未入选高分基金
6. [`experiment_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/reports/experiment_report.md)
   - 看本次实验上下文与结果总览
7. [`backtest_report.md`](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/reports/backtest_report.md)
   - 再看历史表现

## 6.1 读报告时必须注意的时点边界

- `fund_entity_master` 主要解释当前实体画像，不直接解释历史月份。
- 历史月份的规模判断，要看 `fund_universe_monthly.visible_assets_cny_mn`。
- 历史月份的经理解释，要看 `fund_feature_monthly.manager_name` 与 `manager_tenure_months`。
- 报告中看到的 `Time Boundary Notes` 章节，应视为阅读结果前的硬性前提。

## 7. 什么时候必须重跑 baseline

以下情况应重跑 baseline，而不是沿用旧结果：

- 修改默认基金池定义
- 修改因子定义
- 修改评分权重
- 修改组合约束
- 修改 benchmark
- 修改信号时点或执行时点
- 修改交易成本口径
- 修改规模字段口径
- 修改缓存校验逻辑导致快照失效

当前已经发生过的典型案例：

- `sample` / `tushare` 缓存串仓修复后，旧结果不再可直接相信
- 基金实体规模从“代表份额规模”修正为“实体总规模”后，旧 baseline 不再完全可比
- 回测从“仅保留有评分月份”改为“按完整月历显式记录空仓月份”后，旧绩效摘要不再完全可比
- 默认基金池移除独立的 `fund_age` 门槛后，旧基金池和回测 baseline 不再完全可比

## 8. 如何记录一次有效实验

一次有效实验至少应满足：

- 命令成功执行
- 核心报告生成完整
- `experiment_registry.jsonl` 追加一条新记录
- 关键配置和数据口径可追溯

建议记录以下信息：

- 运行日期
- 使用配置文件
- benchmark
- 数据快照时间
- 类型基线快照
- 是否命中缓存
- 是否执行过 `fetch-failed-tushare`
- 是否存在已知近似口径
- 回测摘要

## 9. 当前已知实验风险

### 9.1 规模字段仍非完全官方口径

当前规模在部分基金上仍可能来自：

- `fund_nav` 直接净资产字段
- 或 `fund_share × nav` 的近似估算

因此：

- 它适合做研究筛选基线
- 但不应直接等同于公开网站展示的官方最新规模

### 9.2 当前 benchmark 仍为统一市场 benchmark

当前默认使用中证800，对不同风格基金并非最细口径。

### 9.3 当前实验目录不是 git 仓库

因此 `experiment_registry.jsonl` 中的 `git_commit` 当前为：

- `unknown`

这会降低代码版本可追踪性。

## 10. 后续建议

建议后续补强：

1. baseline 命名与版本冻结机制
2. 实验对比脚本
3. 配置差异自动摘要
4. 数据快照版本号
5. 实验失败日志与自动归档
