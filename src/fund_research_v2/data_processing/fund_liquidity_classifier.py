from __future__ import annotations

import re


def classify_fund_liquidity(fund_name: str) -> dict[str, str | int]:
    """根据基金名称识别最低持有期限制，服务于当前“优先保留流动性”的基金池定义。"""
    normalized_name = str(fund_name or "").strip()
    holding_lock_months = _extract_holding_lock_months(normalized_name)
    if holding_lock_months is not None:
        return {
            "liquidity_restricted": 1,
            "holding_lock_months": holding_lock_months,
            "rule_code": "holding_period_name_rule",
            "confidence": "medium",
            "reason": f"基金名称命中最低持有期关键词，按 {holding_lock_months} 个月持有约束处理；为保证月频调仓流动性，当前基金池直接排除。",
        }
    return {
        "liquidity_restricted": 0,
        "holding_lock_months": 0,
        "rule_code": "liquid_default",
        "confidence": "high",
        "reason": "基金名称未命中最低持有期关键词，默认视为满足当前流动性要求。",
    }


def _extract_holding_lock_months(fund_name: str) -> int | None:
    """把名称中的持有期文本统一折算为月数。"""
    digit_patterns = [
        (r"(\d+)年持有期?", 12),
        (r"(\d+)个月持有期?", 1),
        (r"(\d+)月持有期?", 1),
    ]
    for pattern, multiplier in digit_patterns:
        matched = re.search(pattern, fund_name)
        if matched:
            return int(matched.group(1)) * multiplier

    chinese_patterns = [
        ("一年持有", 12),
        ("二年持有", 24),
        ("两年持有", 24),
        ("三年持有", 36),
        ("三个月持有", 3),
        ("六个月持有", 6),
        ("一年持有期", 12),
        ("二年持有期", 24),
        ("两年持有期", 24),
        ("三年持有期", 36),
        ("三个月持有期", 3),
        ("六个月持有期", 6),
    ]
    for keyword, months in chinese_patterns:
        if keyword in fund_name:
            return months

    if "持有期" in fund_name or "滚动持有" in fund_name:
        # 名称已显式提示存在持有约束，即使未能准确抽出月数，也不应被当作高流动性产品。
        return 1
    return None
