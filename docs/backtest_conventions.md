# 回测约定说明

## 1. 目标

本文件用于明确当前回测引擎的时间口径、收益口径和异常处理方式，避免研究结果因默认假设不清而失真。

## 2. 时间口径

当前回测按月进行。

具体规则：

- 在 `backtest.start_month ~ backtest.end_month` 闭区间内按完整月历推进
- 正式 `signal_month` 统一取 `as_of_date` 之前最后一个完整结束的自然月及其历史月份
- 在 `signal_month` 末观察基金特征与评分
- 在 `signal_month` 生成组合权重
- 在下一月 `execution_month` 月初，把组合视为提交申购的研究代理动作
- 当前把 `execution_month` 月初同时视为 `execution_request_date_proxy` 和 `execution_effective_date_proxy`
- 用下一月 `execution_month` 的基金收益作为该组合的实现收益
- 进入 `signal_month` 信号构造的数据，必须满足 `available_date <= signal_month` 月末

例如：

- `signal_month = 2025-01`
- `execution_month = 2025-02`
- `execution_request_date_proxy = 2025-02-01`
- `execution_effective_date_proxy = 2025-02-01`

含义是：

- 2025 年 1 月末形成选基结果
- 2025 年 2 月初按研究代理口径提交申购并开始承担 2025 年 2 月收益
- 2025 年 2 月收益用于评价这次选基

这意味着：

- 即使某条净值属于 `2025-01`
- 只要它在 2025 年 1 月月末前尚未披露
- 它也不能进入 2025-01 的基金池和特征计算
- 即使 raw 数据里已经出现 `2025-02` 的月内记录
- 只要 `as_of_date` 还没走到 `2025-02` 月末，它也不能成为正式最新信号月

## 3. 收益计算

组合毛收益：

- 各基金在 `execution_month` 的月收益按目标权重加权求和
- 若 `signal_month` 无可投资组合，则该期视为空仓，组合毛收益记为 `0`

组合净收益：

- 组合毛收益减去换手带来的交易成本

## 4. 换手定义

当前换手采用目标权重变化的绝对值和的一半：

`turnover = sum(abs(w_new - w_old)) / 2`

含义：

- 如果组合完全不变，则换手为 0
- 如果组合完全替换，则换手会显著上升
- 如果从有持仓变为空仓，或从空仓变为建仓，也会产生换手

## 5. 成本模型

当前成本模型为固定费率：

- `transaction_cost = turnover * transaction_cost_bps / 10000`

这是一个研究用的简化成本模型。

当前没有纳入：

- 场外基金真实申购费差异
- 大额赎回约束
- 暂停申赎
- 不同基金费率表

## 6. Benchmark 口径

当前 benchmark 收益来自 `benchmark_monthly` 表中的 `benchmark_return_1m`。

当前分两种使用场景：

- 特征阶段
  - `excess_ret_12m` 只使用 `signal_month` 月末前已可见的 benchmark 月收益
- 回测评估阶段
  - 组合收益与 `execution_month` benchmark 收益做事后对比

回测只比较同一 `execution_month` 下：

- 策略净收益
- benchmark 月收益

## 7. 当前异常处理

当前版本采用以下简化规则：

- 若组合中的某只基金在下一月缺少收益，则按 0 处理
- 同时把该类情况显式记录为持有期缺失收益审计，而不再完全隐含在组合收益中
- 若当月无可投资基金，则该期显式记为空仓，不再跳过该月
- 若某只基金因约束被过滤，不进入组合

当前回测结果表会额外输出以下审计字段：

- `missing_weight`
  - 当前月组合中，缺少 `execution_month` 收益记录的持仓权重之和
- `missing_position_count`
  - 当前月缺少 `execution_month` 收益记录的持仓基金数量
- `low_confidence_flag`
  - 若 `missing_weight` 超过 `backtest.missing_weight_warning_threshold`，该月记为低置信度月份
- `return_validity`
  - 当前支持：
    - `valid`
    - `partial_missing`
    - `all_missing`
    - `empty_portfolio`

当前配置中还增加了：

- `backtest.missing_return_policy`
  - 当前支持：
    - `zero_fill_legacy`
    - `audit_only`

注意：

- 当前这两个策略在收益计算上仍都保留“缺失收益按 `0` 计”的兼容口径
- `audit_only` 的作用主要是为后续更严格处理预留配置入口，而不是现在就改变历史收益定义
- 当前系统仍不尝试把缺失收益解释为清盘、暂停申赎或其他生命周期事件
- 这部分仅回答“有多少权重缺少收益观测”，不回答“为什么缺失”

## 8. 当前未覆盖的重要现实问题

当前回测尚未处理：

- 基金清盘后的持仓退出细则
- 暂停申购/赎回
- 实际申购确认日
- 不同份额申购限制

因此当前“按场外基金申购确认口径”应理解为：

- 我们已经明确采用“信号月末决策、次月月初代理申购并生效”的研究语义
- 但由于没有基金开放日、暂停申购、确认规则和日频净值，`execution_request_date_proxy` / `execution_effective_date_proxy` 仍然只是月频代理字段
- 它们的作用是把时间边界说清楚，而不是伪装成真实成交明细

当前已经部分处理：

- 净值披露延迟
  - 已通过 `available_date` 约束信号月可见数据
  - 但 benchmark 与经理历史化仍未纳入同一套可得性框架

当前基金池默认不再额外使用独立的基金成立月数门槛：

- 主要原因是 `min_history_months` 在当前主线下已经承担了更强的样本成熟度约束
- `fund_age_months` 仍保留在基金池输出中，用于审计解释

因此当前回测结果的正确定位是：

- 用于研究比较和框架验证
- 不应用作直接实盘收益承诺
