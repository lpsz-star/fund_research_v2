# 配置治理说明

本文档定义 `configs/` 目录的最小治理规则，目标是让主线配置、正式候选和历史研究配置彼此隔离，同时保持可追溯。

## 1. 目录分层

- `configs/tushare.json`
  - 当前 `tushare` 默认 baseline
- `configs/default.json`
  - 当前 `sample` 默认 baseline
- `configs/local.json`
  - 本地密钥与环境相关配置
- `configs/candidates/`
  - 当前仍在正式跟踪的候选配置
- `configs/archive/factor_research/`
  - 已完成研究、需要保留复现能力的历史配置

## 2. 当前约定

- 当前 `tushare` 默认 baseline：
  - `configs/tushare.json`
- 当前 `tushare` 正式候选：
  - `configs/candidates/tushare_scoring_v5_candidate.json`
- 本轮因子研究过程产生的 `v2/v3/v4`、`incremental`、`portfolio8/12` 配置：
  - 统一归档到 `configs/archive/factor_research/`

## 3. 命名规则

- baseline：
  - `<data_source>.json`
- candidate：
  - `<data_source>_scoring_vX_candidate.json`
- archive：
  - 保留原始研究命名，不再为历史配置重命名

## 4. 维护原则

- 默认主线只保留 baseline
- 同一时间正式候选尽量不超过 1 到 2 个
- 研究配置不再堆在 `configs/` 根目录
- 迁移配置时，优先更新文档和标准命令引用，不直接删除历史配置
