# Fund Research V2

`fund_research_v2` 是一个面向中国市场场外公募主动权益基金的月频量化研究平台。  
它当前的目标不是“快速产出一个看起来能赚钱的策略”，而是先把研究链路搭成一个可复现、可测试、可审计、可持续迭代的系统。

这个仓库遵循 [AGENTS.md](/Users/liupeng/.codex/projects/fund_research_v2/AGENTS.md) 中定义的工作方式，因此系统设计优先强调：

- 金融逻辑正确
- 回测口径清晰
- 数据与策略边界明确
- 实验可追踪
- 后续迭代不依赖手工修补

## 1. 当前定位

当前版本是一个研究内核，不是实盘交易系统。

已实现的能力：

- `sample` 与 `tushare` 两种数据入口
- 基金实体与 A/C 份额映射
- 月频基金池构建
- 月频特征计算
- 横截面评分与排序
- 规则约束组合构建
- 月频回测引擎
- 实验记录与 Markdown 报告输出
- 中文设计文档与基础测试

当前不在默认范围内的内容：

- 实盘申购赎回执行
- 高频或日频策略
- 完整 Web 平台
- 黑盒机器学习模型
- 依赖人工修补原始数据的流程

## 2. 当前默认研究范围

首期默认研究对象为：

- 中国市场场外公募基金
- 主动权益方向
- 当前只纳入：
  - `主动股票`
  - `偏股混合`

当前默认研究节奏为：

- 月频调仓
- 月末信号
- 下一月执行

当前默认组合方法为：

- 规则约束法
- 等权为主
- 单基金权重上限
- 单基金公司暴露上限

## 3. 你应该先读什么

如果你第一次看这个项目，建议阅读顺序如下：

1. [AGENTS.md](/Users/liupeng/.codex/projects/fund_research_v2/AGENTS.md)
2. [docs/architecture.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/architecture.md)
3. [docs/data_contracts.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_contracts.md)
4. [docs/data_dictionary.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_dictionary.md)
5. [docs/strategy_spec_v1.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/strategy_spec_v1.md)
6. [docs/factor_catalog.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_catalog.md)
7. [docs/backtest_conventions.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/backtest_conventions.md)
8. [docs/experiment_guide.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)
9. [docs/error_log.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/error_log.md)
10. [docs/changes.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/changes.md)

这几份文档分别回答：

- 系统怎么分层
- 数据表和字段长什么样
- 当前策略口径是什么
- 当前因子和评分口径是什么
- 回测时序和成本假设是什么
- 一次实验应该怎么跑、怎么比
- 已知错误和近期变更是什么

## 4. 文档索引

当前 `docs/` 目录下各文档职责如下：

- [architecture.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/architecture.md)：系统分层、模块职责、默认设计选择
- [data_contracts.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_contracts.md)：表级数据契约、主键与时间字段约定
- [data_dictionary.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_dictionary.md)：字段级数据字典、单位和缺失语义
- [strategy_spec_v1.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/strategy_spec_v1.md)：当前策略范围与研究口径
- [factor_catalog.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_catalog.md)：当前已实现因子、合成分与评分逻辑
- [backtest_conventions.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/backtest_conventions.md)：信号时点、执行时点、成本与回测边界
- [experiment_guide.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)：实验运行、结果阅读、可比性判断
- [error_log.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/error_log.md)：已确认错误、根因、修复方案与影响范围
- [changes.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/changes.md)：主线迭代的变更记录

## 5. 当前目录结构

```text
fund_research_v2/
├─ src/fund_research_v2/
│  ├─ common/            # 配置、契约、IO、工作流编排
│  ├─ data_ingestion/    # sample/tushare 数据接入
│  ├─ data_processing/   # 样例数据与数据处理辅助
│  ├─ universe/          # 基金池规则
│  ├─ features/          # 月频特征
│  ├─ ranking/           # 横截面打分与排序
│  ├─ portfolio/         # 组合构建
│  ├─ backtest/          # 回测引擎
│  ├─ evaluation/        # 绩效指标
│  └─ reporting/         # 报告输出
├─ configs/              # 配置文件
├─ docs/                 # 中文设计与口径文档
├─ tests/                # 单元与流程测试
├─ data/raw/             # 原始或接近原始的数据缓存
└─ outputs/              # clean/feature/result/reports/experiments
```

## 6. 研究主流程

当前的标准研究链路是：

1. 获取或生成数据
2. 构建基金池
3. 计算月频特征
4. 做横截面评分
5. 构建组合
6. 运行回测
7. 输出报告与实验记录

对应的职责模块分别是：

- 数据接入：[providers.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
- 基金池：[filters.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/universe/filters.py)
- 特征：[feature_builder.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/features/feature_builder.py)
- 排名：[scoring_engine.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/ranking/scoring_engine.py)
- 组合：[construction.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/portfolio/construction.py)
- 回测：[engine.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/backtest/engine.py)
- 工作流入口：[workflows.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/workflows.py)

## 7. 命令说明

日常使用优先通过 [Makefile](/Users/liupeng/.codex/projects/fund_research_v2/Makefile) 调用。

先看全部可用命令：

```bash
make help
```

默认存在两套配置：

- `sample`：使用 [default.json](/Users/liupeng/.codex/projects/fund_research_v2/configs/default.json)
- `tushare`：使用 [tushare.json](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)

如果你需要绕过 `make`，仍然可以直接调用 CLI。

### 6.1 拉取或生成数据

```bash
make fetch-sample
make fetch-tushare
```

说明：

- 当 `data_source=sample` 时，会生成样例数据并写入原始层
- 当 `data_source=tushare` 时，会读取本地 token 并尝试抓取真实数据

### 6.2 只构建基金池

```bash
make universe-sample
make universe-tushare
```

输出：

- `outputs/clean/fund_universe_monthly.csv`
- `outputs/reports/universe_audit_report.md`

### 6.3 计算特征

```bash
make features-sample
make features-tushare
```

输出：

- `outputs/feature/fund_feature_monthly.csv`

### 6.4 执行排名

```bash
make rank-sample
make rank-tushare
```

输出：

- `outputs/result/fund_score_monthly.csv`

### 6.5 生成最新组合

```bash
make portfolio-sample
make portfolio-tushare
```

输出：

- `outputs/result/portfolio_target_monthly.csv`
- `outputs/result/portfolio_snapshot.json`
- `outputs/reports/portfolio_report.md`
- `outputs/reports/universe_audit_report.md`

### 6.6 执行回测

```bash
make backtest-sample
make backtest-tushare
```

输出：

- `outputs/result/backtest_monthly.csv`
- `outputs/result/backtest_summary.json`
- `outputs/reports/universe_audit_report.md`

### 6.7 跑完整实验

```bash
make run-sample
make run-tushare
```

输出：

- 清洗层数据
- 特征
- 排名结果
- 组合结果
- 回测结果
- 基金池审计报告
- Markdown 报告
- 实验登记

### 6.8 运行测试

```bash
make test
```

### 6.9 清理目录

```bash
make clean-outputs
make clean-raw
```

### 6.10 直接调用 CLI

如果你要调试某个具体入口，也可以直接运行：

```bash
PYTHONPATH=src python3 -m fund_research_v2 <command> --config <config_path>
```

例如：

```bash
PYTHONPATH=src python3 -m fund_research_v2 run-ranking --config configs/tushare.json
```

## 7. 输出目录说明

### 7.1 `data/raw/`

用于存放原始或接近原始的数据快照。

当前典型文件：

- `fund_entity_master.csv`
- `fund_share_class_map.csv`
- `fund_nav_monthly.csv`
- `benchmark_monthly.csv`
- `dataset_snapshot.json`

### 7.2 `outputs/clean/`

用于存放清洗后、结构标准化的数据。

当前典型文件：

- `fund_entity_master.csv`
- `fund_share_class_map.csv`
- `fund_nav_monthly.csv`
- `fund_universe_monthly.csv`
- `benchmark_monthly.csv`

### 7.3 `outputs/feature/`

用于存放特征层数据。

当前典型文件：

- `fund_feature_monthly.csv`

### 7.4 `outputs/result/`

用于存放研究结果层。

当前典型文件：

- `fund_score_monthly.csv`
- `portfolio_target_monthly.csv`
- `portfolio_snapshot.json`
- `backtest_monthly.csv`
- `backtest_summary.json`

### 7.5 `outputs/reports/`

用于存放 Markdown 报告。

当前典型文件：

- `portfolio_report.md`
- `experiment_report.md`
- `backtest_report.md`

### 7.6 `outputs/experiments/`

用于存放实验登记。

当前典型文件：

- `experiment_registry.jsonl`

## 8. 配置说明

配置文件在 [default.json](/Users/liupeng/.codex/projects/fund_research_v2/configs/default.json)。

当前主要配置段包括：

- `data_source`
- `lookback_months`
- `universe`
- `ranking`
- `portfolio`
- `backtest`
- `reporting`
- `tushare`
- `paths`

这意味着：

- 基金池规则是配置驱动的
- 因子权重是配置驱动的
- 组合约束是配置驱动的
- 回测成本与 benchmark 是配置驱动的

## 9. 测试

运行测试：

```bash
make test
```

当前测试覆盖了：

- 主流程输出
- 基金池过滤
- 组合约束
- 回测执行时序
- CLI 基本入口
- 缓存读取

## 10. 当前实现中的关键约定

为了与你们的 `AGENTS.md` 保持一致，当前版本明确遵循这些默认约定：

- A/C 份额默认按基金实体归并
- 同月只在可投资基金之间进行横截面比较
- 因子只使用当月及历史数据
- 回测采用“本月信号、下一月执行”
- 原始输出、特征输出、结果输出分层落盘
- 实验结果通过 `experiment_registry.jsonl` 追踪


## 11. 首次阅读代码建议路径

如果你是第一次进入这个仓库，建议不要一上来就从某个因子函数开始读。更高效的方式是按“入口 -> 数据 -> 研究链路 -> 回测”的顺序看。

### 第一步：先看命令入口

先读 [cli.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/cli.py)。

这里回答两个最基础的问题：

- 这个项目能执行哪些命令
- 每个命令最终会调用哪条工作流

如果你不知道系统是怎么跑起来的，先看这里最省时间。

### 第二步：再看工作流编排

接着读 [workflows.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/workflows.py)。

这里是全项目最关键的“总装配层”，能看到：

- 配置在哪加载
- 数据在哪进入系统
- 基金池、特征、排名、组合、回测是怎么串起来的
- 输出文件写到哪里
- 实验记录怎么生成

如果只能选一个文件先看，优先看这个。

### 第三步：理解配置和数据契约

然后看这两个文件：

- [config.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/config.py)
- [contracts.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/contracts.py)

这一步的目的不是看实现技巧，而是先搞清楚：

- 系统允许配置什么
- 数据对象在系统内部长什么样
- 哪些字段是核心字段

如果这一步没看明白，后面读策略逻辑会一直在猜字段含义。

### 第四步：看数据如何进入系统

再读：

- [providers.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
- [sample_data.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_processing/sample_data.py)

建议先看 `sample_data.py`，因为它最容易帮助你理解系统当前期待的数据形状。

然后再看 `providers.py`，理解：

- `sample` 和 `tushare` 是怎么切换的
- 原始层缓存如何落盘
- A/C 份额如何映射到基金实体

### 第五步：按研究链路顺着往下看

理解完入口和数据，再按下面顺序读核心研究模块：

1. [filters.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/universe/filters.py)
2. [feature_builder.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/features/feature_builder.py)
3. [scoring_engine.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/ranking/scoring_engine.py)
4. [construction.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/portfolio/construction.py)
5. [engine.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/backtest/engine.py)

这样读的好处是你能自然看到一条完整链路：

- 哪些基金先进入基金池
- 基金池上的基金怎么算特征
- 特征如何变成分数
- 分数如何变成组合
- 组合如何变成回测结果

### 第六步：最后再看报告和测试

最后看：

- [reports.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/reporting/reports.py)
- [test_pipeline.py](/Users/liupeng/.codex/projects/fund_research_v2/tests/test_pipeline.py)

`reports.py` 适合理解系统最后向使用者输出了什么。  
`test_pipeline.py` 适合理解当前项目作者认为哪些行为是必须稳定的。

### 推荐的理解顺序总结

最推荐的首次阅读顺序是：

1. `README.md`
2. `AGENTS.md`
3. `docs/architecture.md`
4. `src/fund_research_v2/cli.py`
5. `src/fund_research_v2/common/workflows.py`
6. `src/fund_research_v2/common/config.py`
7. `src/fund_research_v2/common/contracts.py`
8. `src/fund_research_v2/data_ingestion/providers.py`
9. `src/fund_research_v2/universe/filters.py`
10. `src/fund_research_v2/features/feature_builder.py`
11. `src/fund_research_v2/ranking/scoring_engine.py`
12. `src/fund_research_v2/portfolio/construction.py`
13. `src/fund_research_v2/backtest/engine.py`
14. `tests/test_pipeline.py`

如果你按这个顺序读，通常不会在模块关系上迷路。
