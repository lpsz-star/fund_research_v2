from __future__ import annotations

import re


def classify_fund_type(
    *,
    fund_type: str,
    invest_type: str,
    fund_name: str,
    benchmark_text: str,
) -> dict[str, object]:
    """把上游基金类型字段标准化为项目内部可审计的类型标签。"""
    normalized_fund_type = _normalize_text(fund_type)
    normalized_invest_type = _normalize_text(invest_type)
    normalized_name = _normalize_text(fund_name)
    normalized_benchmark = _normalize_text(benchmark_text)
    text_bundle = " ".join([normalized_fund_type, normalized_invest_type, normalized_name, normalized_benchmark]).strip()
    non_benchmark_text = " ".join([normalized_fund_type, normalized_invest_type, normalized_name]).strip()

    # 先识别被动/增强指数产品，是因为这类产品常常也带“股票”“混合”字样，若顺序靠后容易被误归为主动权益。
    if _contains_any(text_bundle, ["指数增强", "增强指数", "enhanced index"]):
        return _payload(
            primary_type="指数增强",
            raw_fund_type=fund_type,
            invest_type=invest_type,
            rule_code="index_enhanced_keyword",
            confidence="high",
            reason="命中“指数增强/增强指数”关键词，优先识别为指数增强产品。",
        )
    if _looks_like_passive_index(non_benchmark_text):
        return _payload(
            primary_type="被动指数",
            raw_fund_type=fund_type,
            invest_type=invest_type,
            rule_code="passive_index_keyword",
            confidence="high",
            reason="命中指数/ETF/联接等被动产品关键词，优先识别为被动指数。",
        )

    # 再处理主动股票。这里显式排除指数字样，是为了避免“股票指数基金”被误归成主动股票。
    if "股票" in normalized_fund_type and "指数" not in non_benchmark_text:
        return _payload(
            primary_type="主动股票",
            raw_fund_type=fund_type,
            invest_type=invest_type,
            rule_code="equity_fund_type",
            confidence="high",
            reason="fund_type 包含“股票”且未命中指数类特征，归为主动股票。",
        )

    if "混合" in normalized_fund_type or "混合" in normalized_invest_type or "混合" in normalized_name:
        if _contains_any(text_bundle, ["灵活配置", "灵活", "灵活配置型"]):
            return _payload(
                primary_type="灵活配置混合",
                raw_fund_type=fund_type,
                invest_type=invest_type,
                rule_code="flexible_mix_keyword",
                confidence="medium",
                reason="命中“灵活配置”关键词，先归为灵活配置混合。",
            )
        if _contains_any(text_bundle, ["偏债", "债券", "二级债", "一级债", "固收+"]):
            return _payload(
                primary_type="偏债混合",
                raw_fund_type=fund_type,
                invest_type=invest_type,
                rule_code="bond_mix_keyword",
                confidence="medium",
                reason="命中偏债/债券关键词，归为偏债混合。",
            )
        if _contains_any(text_bundle, ["平衡", "配置"]):
            return _payload(
                primary_type="偏股混合",
                raw_fund_type=fund_type,
                invest_type=invest_type,
                rule_code="balanced_mix_keyword",
                confidence="medium",
                reason="命中平衡/配置类关键词，但未出现偏债特征，暂归为偏股混合。",
            )
        return _payload(
            primary_type="偏股混合",
            raw_fund_type=fund_type,
            invest_type=invest_type,
            rule_code="mixed_fund_type_default",
            confidence="medium",
            reason="fund_type 命中“混合”，且未识别为偏债或指数类，默认归为偏股混合。",
        )

    return _payload(
        primary_type="其他",
        raw_fund_type=fund_type,
        invest_type=invest_type,
        rule_code="fallback_other",
        confidence="low",
        reason="未命中当前主动权益研究范围内的明确规则，回退为其他。",
    )


def _normalize_text(value: object) -> str:
    """把多来源文本标准化为便于规则匹配的紧凑字符串。"""
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    return text.lower()


def _contains_any(text: str, keywords: list[str]) -> bool:
    """判断文本是否命中任一关键词。"""
    return any(keyword.lower() in text for keyword in keywords)


def _looks_like_passive_index(text: str) -> bool:
    """识别 ETF、联接、LOF、指数基金等被动指数特征。"""
    return _contains_any(text, ["指数", "etf", "联接", "lof"])


def _payload(
    *,
    primary_type: str,
    raw_fund_type: str,
    invest_type: str,
    rule_code: str,
    confidence: str,
    reason: str,
) -> dict[str, object]:
    """组装标准分类结果。"""
    return {
        "primary_type": primary_type,
        "raw_fund_type": raw_fund_type,
        "raw_invest_type": invest_type,
        "rule_code": rule_code,
        "confidence": confidence,
        "reason": reason,
    }
