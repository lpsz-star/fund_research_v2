from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatasetSnapshot:
    """描述研究流程消费的数据快照。"""
    # 这里约定的是“研究流程可消费的数据快照”，不是对 tushare 原始响应的逐字段镜像。
    fund_entity_master: list[dict[str, object]]
    fund_share_class_map: list[dict[str, object]]
    fund_nav_monthly: list[dict[str, object]]
    benchmark_monthly: list[dict[str, object]]
    manager_assignment_monthly: list[dict[str, object]]
    fund_type_audit: list[dict[str, object]]
    metadata: dict[str, object]
    fund_liquidity_audit: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class UniverseSnapshot:
    """描述逐月基金池及其审计元信息。"""
    # 基金池必须保留元信息和原因码，否则后续无法审计某只基金为什么未进入排序。
    rows: list[dict[str, object]]
    metadata: dict[str, object]
