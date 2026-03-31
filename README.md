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
- 黑盒机器学习模型
- 依赖人工修补原始数据的流程

当前额外提供一个本地只读研究网站，用于浏览 `outputs/<data_source>/...` 下已经生成的实验、回测、组合和 Markdown 报告。它不修改研究产物，也不在页面里触发策略运行。

## 2. 当前默认研究范围

首期默认研究对象为：

- 中国市场场外公募基金
- 主动权益方向
- 当前只纳入：
  - `主动股票`
  - `偏股混合`
  - `灵活配置混合`

当前默认 benchmark 口径为：

- 主回测固定使用 `benchmark.default_key`
- 当前 `benchmark.default_key = broad_equity = 中证800 (000906.SH)`
- 因此当前默认 baseline、候选评分体系的主回测 benchmark 都是中证800
- 配置中的 `primary_type_map` 当前主要保留给特征层、原始多指数缓存与元数据说明，不再决定主回测 benchmark

当前默认研究节奏为：

- 月频调仓
- 信号基于完整结束的自然月月末
- `as_of_date` 若尚未走到当月月末，则正式最新信号月自动回退到上一个完整月
- 下月第 1 个交易日决策，`T` 卖出、`T+2` 到账、`T+3` 新组合开始承担收益


## 3. 阅读与文档索引

如果你第一次看这个项目，建议按下面顺序阅读：

1. [AGENTS.md](/Users/liupeng/.codex/projects/fund_research_v2/AGENTS.md)
2. [docs/architecture.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/architecture.md)
3. [docs/data_contracts.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_contracts.md)
4. [docs/data_dictionary.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_dictionary.md)
5. [docs/strategy_spec_v1.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/strategy_spec_v1.md)
6. [docs/factor_catalog.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_catalog.md)
7. [docs/factor_iteration_framework.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_iteration_framework.md)
8. [docs/backtest_conventions.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/backtest_conventions.md)
9. [docs/experiment_guide.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)
10. [docs/robustness_analysis.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)
11. [docs/baseline_upgrade_checklist.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md)
12. [docs/candidate_validation_spec.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)
13. [docs/error_log.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/error_log.md)
14. [docs/changes.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/changes.md)

这些文档分别覆盖：
- 系统分层和模块职责
- 数据表结构与字段定义
- 历史月份与最新快照的时点边界
- 当前策略、因子与回测口径
- 实验运行方式与可比性判断
- 已知错误与近期变更

当前 `docs/` 目录下各文档职责如下：

- [architecture.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/architecture.md)：系统分层、模块职责、默认设计选择
- [data_contracts.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_contracts.md)：表级数据契约、主键与时间字段约定，以及历史月份与最新快照的字段边界
- [data_dictionary.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/data_dictionary.md)：字段级数据字典、单位和缺失语义
- [strategy_spec_v1.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/strategy_spec_v1.md)：当前策略范围与研究口径
- [factor_catalog.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_catalog.md)：因子字典、评分体系权重、各因子使用位置总览
- [factor_iteration_framework.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/factor_iteration_framework.md)：主候选评分体系的因子去留、竞争位设计与小步迭代框架
- [backtest_conventions.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/backtest_conventions.md)：信号时点、执行时点、成本、收益计算与时间边界
- [experiment_guide.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/experiment_guide.md)：实验运行、结果阅读、时点边界提醒与可比性判断
- [robustness_analysis.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/robustness_analysis.md)：候选评分稳健性分析的逻辑、flag 定义与使用边界
- [baseline_upgrade_checklist.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/baseline_upgrade_checklist.md)：候选评分是否升级为默认 baseline 的决策清单
- [candidate_validation_spec.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/candidate_validation_spec.md)：A/B 两项候选基线验证的输出契约与当前决策规则
- [error_log.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/error_log.md)：已确认错误、根因、修复方案与影响范围
- [changes.md](/Users/liupeng/.codex/projects/fund_research_v2/docs/changes.md)：主线迭代的变更记录

当前 `sample` 与 `tushare` 的产物目录已按数据源隔离：
- `outputs/sample/...`
- `outputs/tushare/...`
这样做是为了避免跑完真实数据后，又被后续 `sample` 验证流程覆盖结果。

当前 `outputs/<data_source>/` 目录也已按产物职责进一步分层：
- `clean/`：标准化后的研究输入
- `feature/`：月频特征层
- `result/`：主策略结果，如评分、组合、回测摘要
- `reports/`：主链路 Markdown 报告
- `experiments/`：实验登记与追踪
- `factor_evaluation/`：因子评估诊断
- `robustness/`：稳健性分析
- `candidate_validation/`：候选 baseline 补证
- `comparison/`：最近两次实验的结构化对比

接入层现在还会额外输出一份标准审计产物：
- `outputs/<data_source>/reports/ingestion_audit_report.md`
- `outputs/<data_source>/reports/fund_type_audit_report.md`
- `outputs/<data_source>/reports/fund_liquidity_audit_report.md`
- `outputs/<data_source>/clean/dropped_entities.csv`
- `outputs/<data_source>/clean/fund_type_audit.csv`
- `outputs/<data_source>/clean/fund_liquidity_audit.csv`

它们专门回答两类问题：
- 为什么 `fund_basic` 里看到的份额/实体，没有进入 clean 层
- 为什么某只基金被判成 `主动股票`、`偏股混合`、`被动指数` 或 `其他`
- 为什么某只基金因为最低持有期而被当前重视流动性的基金池排除

当前 `benchmark_monthly.csv` 也已支持多条指数并行缓存：
- 不再假设整个研究流程只对应一条 benchmark 序列
- 特征层仍可按 `benchmark.primary_type_map` 读取对应指数
- 但主回测当前固定使用 `benchmark.default_key`，不会按基金类型动态切换 benchmark

真实 `tushare` 抓数现在还会额外保留单接口响应缓存：
- `data/raw/tushare/api_cache/`
它的作用是让后续重跑尽量复用已经成功的接口响应，而不是每次都从头联网全量抓。

它不会重写整份 raw 快照，而是只根据上一次 `dataset_snapshot.json` 中记录的 `fetch_diagnostics.api_error_samples`，
对失败的 `ts_code` 重新预热 `fund_manager` / `fund_nav` / `fund_share` 这类单接口缓存，降低下一次全量重跑的无效联网开销。

当前除了默认基线配置，还保留三条非默认评分体系配置：

- [`configs/tushare_scoring_v2.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2.json)
- [`configs/tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json)
- [`configs/tushare_scoring_v3.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v3.json)

它们的用途主要是：
- 作为历史候选或新候选继续做对照实验
- 验证不同因子组合是否值得进入下一轮默认 baseline 讨论
- 观察收益改善是否伴随波动、回撤和换仓恶化

当前默认 baseline 已升级为：
- [`configs/tushare.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)

它当前采用的评分结构与 [`configs/tushare_scoring_v2_lite.json`](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare_scoring_v2_lite.json) 一致。


## 4. 当前目录结构

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
└─ outputs/              # clean/feature/result/reports/experiments + 独立诊断目录
```

## 5. 研究主流程

当前的标准研究链路是：

1. 获取或生成数据
2. 构建基金池
3. 计算月频特征
4. 评估单因子有效性
5. 做横截面评分
6. 构建组合
7. 运行回测
8. 输出报告与实验记录

对应的职责模块分别是：

- 数据接入：[providers.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/data_ingestion/providers.py)
- 基金池：[filters.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/universe/filters.py)
- 特征：[feature_builder.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/features/feature_builder.py)
- 因子评估：[factor_evaluator.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/evaluation/factor_evaluator.py)
- 排名：[scoring_engine.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/ranking/scoring_engine.py)
- 组合：[construction.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/portfolio/construction.py)
- 回测：[engine.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/backtest/engine.py)
- 工作流入口：[workflows.py](/Users/liupeng/.codex/projects/fund_research_v2/src/fund_research_v2/common/workflows.py)

## 6. 快速开始

### 6.1 环境要求

- Python `>=3.10`
- 建议使用虚拟环境
- 如果要运行真实数据流程，需要有效的 `tushare token`

项目依赖声明位于：

- [pyproject.toml](/Users/liupeng/.codex/projects/fund_research_v2/pyproject.toml)

### 6.2 安装步骤

首次从 GitHub 拉取仓库后，建议按下面步骤初始化环境：

```bash
git clone https://github.com/lpsz-star/fund_research_v2.git
cd fund_research_v2

python3 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -e .
```

### 6.3 先跑样例流程

样例流程不依赖 `tushare token`，适合先验证项目是否安装成功：

```bash
make test
make run-sample
```

运行完成后，建议优先查看：

- [outputs/sample/reports/experiment_report.md](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/reports/experiment_report.md)
- [outputs/sample/factor_evaluation/factor_evaluation_report.md](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/factor_evaluation/factor_evaluation_report.md)
- [outputs/sample/reports/portfolio_report.md](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/reports/portfolio_report.md)
- [outputs/sample/reports/universe_audit_report.md](/Users/liupeng/.codex/projects/fund_research_v2/outputs/sample/reports/universe_audit_report.md)

### 6.4 运行真实 `tushare` 数据流程

如果要运行真实数据，请先创建本地密钥文件：

- [configs/local.json](/Users/liupeng/.codex/projects/fund_research_v2/configs/local.json)

文件格式如下：

```json
{
  "tushare_token": "你的token"
}
```

注意：

- 该文件已经在 `.gitignore` 中排除，不应提交到仓库
- `tushare` 流程会读取 [configs/tushare.json](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)

然后执行：

```bash
make run-tushare
```

如果上一次 `fetch-tushare` 或 `run-tushare` 主要是因为少量接口失败，可以先执行：

```bash
make fetch-failed-tushare
make run-tushare
```

建议阅读：

- `outputs/tushare/reports/fetch_retry_report.md`
- `outputs/tushare/result/fetch_retry_summary.json`

### 6.5 在浏览器里查看结果

先确保已经生成可读产物，例如：

```bash
make run-sample
```

然后启动本地只读网站：

```bash
make serve-web-sample
```

默认浏览地址：

- `http://127.0.0.1:8000/`

如果要查看真实数据产物：

```bash
make run-tushare
make serve-web-tushare
```

也可以直接调用 CLI：

```bash
PYTHONPATH=src python3 -m fund_research_v2 serve-web --config configs/default.json --host 127.0.0.1 --port 8000
```

当前网站提供 4 个只读视图：

- `/`：实验总览
- `/backtest`：回测指标、累计曲线、月度结果
- `/portfolio`：最新正式研究月组合与候选排名
- `/reports`：Markdown 报告浏览

重跑实验后，手动刷新页面即可读取最新结果。

### 6.6 常用验证命令

```bash
make help
make test
make fetch-failed-tushare
make compare-sample
make compare-tushare
make run-sample
make run-tushare
make serve-web-sample
make serve-web-tushare
make portfolio-tushare
make backtest-tushare
```

当前测试已按职责拆分为：

- `tests/pipeline_unit.py`
- `tests/pipeline_integration.py`
- `tests/pipeline_regression.py`

同时保留兼容入口：

- `tests/test_pipeline.py`

因此原有命令不需要改：

```bash
make test
python3 -m unittest tests.test_pipeline
```

## 7. 命令说明

日常使用优先通过 [Makefile](/Users/liupeng/.codex/projects/fund_research_v2/Makefile) 调用。

先看全部可用命令：

```bash
make help
```

默认存在两套配置：

- `sample`：使用 [default.json](/Users/liupeng/.codex/projects/fund_research_v2/configs/default.json)
- `tushare`：使用 [tushare.json](/Users/liupeng/.codex/projects/fund_research_v2/configs/tushare.json)

当前 clean / raw 层还会额外输出一张月度经理映射表：

- `manager_assignment_monthly.csv`

它的作用是把经理任职历史对齐到研究月份，避免用“当前经理”反向覆盖整段历史。

如果你需要绕过 `make`，仍然可以直接调用 CLI。

### 7.1 拉取或生成数据

```bash
make fetch-sample
make fetch-tushare
```

说明：

- 当 `data_source=sample` 时，会生成样例数据并写入原始层
- 当 `data_source=tushare` 时，会读取本地 token 并尝试抓取真实数据

### 7.2 只构建基金池

```bash
make universe-sample
make universe-tushare
```

输出：

- `outputs/<data_source>/clean/fund_universe_monthly.csv`
- `outputs/<data_source>/reports/universe_audit_report.md`

### 7.3 计算特征

```bash
make features-sample
make features-tushare
```

输出：

- `outputs/<data_source>/feature/fund_feature_monthly.csv`

### 7.4 执行排名

```bash
make rank-sample
make rank-tushare
```

输出：

- `outputs/<data_source>/result/fund_score_monthly.csv`

### 7.5 生成最新组合

```bash
make portfolio-sample
make portfolio-tushare
```

输出：

- `outputs/<data_source>/result/portfolio_target_monthly.csv`
- `outputs/<data_source>/result/portfolio_snapshot.json`
- `outputs/<data_source>/reports/portfolio_report.md`
- `outputs/<data_source>/reports/universe_audit_report.md`

### 7.6 执行回测

```bash
make backtest-sample
make backtest-tushare
```

输出：

- `outputs/<data_source>/result/backtest_monthly.csv`
- `outputs/<data_source>/result/backtest_summary.json`
- `outputs/<data_source>/reports/universe_audit_report.md`

### 7.7 跑完整实验

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

### 7.8 运行测试

```bash
make test
```

### 7.9 清理目录

```bash
make clean-outputs
make clean-raw
```

### 7.10 直接调用 CLI

如果你要调试某个具体入口，也可以直接运行：

```bash
PYTHONPATH=src python3 -m fund_research_v2 <command> --config <config_path>
```

例如：

```bash
PYTHONPATH=src python3 -m fund_research_v2 run-ranking --config configs/tushare.json
```

## 8. 输出目录说明

### 8.1 `data/raw/<data_source>/`

用于存放原始或接近原始的数据快照。

当前典型文件：

- `fund_entity_master.csv`
- `fund_share_class_map.csv`
- `fund_nav_monthly.csv`
- `benchmark_monthly.csv`
- `dataset_snapshot.json`

### 8.2 `outputs/<data_source>/clean/`

用于存放清洗后、结构标准化的数据。

当前典型文件：

- `fund_entity_master.csv`
- `fund_share_class_map.csv`
- `fund_nav_monthly.csv`
- `fund_universe_monthly.csv`
- `benchmark_monthly.csv`

### 8.3 `outputs/<data_source>/feature/`

用于存放特征层数据。

当前典型文件：

- `fund_feature_monthly.csv`

### 8.4 `outputs/<data_source>/result/`

用于存放研究结果层。

当前典型文件：

- `fund_score_monthly.csv`
- `portfolio_target_monthly.csv`
- `portfolio_snapshot.json`
- `backtest_monthly.csv`
- `backtest_summary.json`

### 8.5 `outputs/<data_source>/reports/`

用于存放 Markdown 报告。

当前典型文件：

- `portfolio_report.md`
- `experiment_report.md`
- `backtest_report.md`

### 8.6 `outputs/<data_source>/experiments/`

用于存放实验登记。

当前典型文件：

- `experiment_registry.jsonl`

## 9. 配置说明

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

## 10. 测试

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
