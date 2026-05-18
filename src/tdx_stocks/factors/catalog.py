from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    group: str
    description: str
    depends_on: tuple[str, ...]
    strategies: tuple[str, ...] = ()
    higher_is_better: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


FACTOR_CATALOG: tuple[FactorDefinition, ...] = (
    FactorDefinition("rank_ret_20", "xsec", "20日收益横截面排名", ("ret_20",), higher_is_better=False),
    FactorDefinition("rank_ret_60", "xsec", "60日收益横截面排名", ("ret_60",), higher_is_better=False),
    FactorDefinition("pct_rank_ret_20", "xsec", "20日收益横截面百分位", ("ret_20",)),
    FactorDefinition("pct_rank_amount_ma20", "xsec", "20日均成交额横截面百分位", ("amount_ma20",)),
    FactorDefinition("pct_rank_vol_20", "xsec", "20日波动率横截面百分位", ("vol_20",)),
    FactorDefinition("rs_ret_20", "relative_strength", "相对强弱 20日收益偏离值", ("ret_20",)),
    FactorDefinition("rs_ret_60", "relative_strength", "相对强弱 60日收益偏离值", ("ret_60",)),
    FactorDefinition("rs_score", "relative_strength", "综合相对强弱得分", ("ret_20", "ret_60")),
    FactorDefinition("is_top_ret_20", "relative_strength", "是否属于20日收益前列", ("ret_20",)),
    FactorDefinition("is_top_ret_60", "relative_strength", "是否属于60日收益前列", ("ret_60",)),
    FactorDefinition("is_new_high_60", "trend", "是否创60日新高", ("adj_close", "high_60")),
    FactorDefinition("is_new_high_120", "trend", "是否创120日新高", ("adj_close", "high_120")),
    FactorDefinition("is_new_high_250", "trend", "是否创250日新高", ("adj_close", "high_250")),
    FactorDefinition("pct_from_high_60", "trend", "距离60日高点的百分比", ("adj_close", "high_60")),
    FactorDefinition("pct_from_high_120", "trend", "距离120日高点的百分比", ("adj_close", "high_120")),
    FactorDefinition("amount_ma20_pct_rank", "liquidity", "20日均成交额百分位", ("amount_ma20",)),
    FactorDefinition("amount_stability_20", "liquidity", "20日成交额稳定度", ("amount_ma20", "amount_ma60")),
    FactorDefinition("vol_20_pct_rank", "risk", "20日波动率百分位", ("vol_20",)),
    FactorDefinition("atr_pct_14_pct_rank", "risk", "ATR 百分位", ("atr_pct_14",)),
    FactorDefinition("risk_score", "risk", "综合风险评分", ("vol_20", "atr_pct_14", "rsi_14"), higher_is_better=False),
    FactorDefinition("is_high_volatility", "risk", "高波动标记", ("vol_20", "atr_pct_14"), higher_is_better=False),
    FactorDefinition("missing_price_flag", "quality", "缺失价格标记", ("adj_open", "adj_high", "adj_low", "adj_close"), higher_is_better=False),
    FactorDefinition("zero_amount_flag", "quality", "零成交额标记", ("amount", "amount_ma20"), higher_is_better=False),
    FactorDefinition("invalid_ohlc_flag", "quality", "OHLC 异常标记", ("adj_open", "adj_high", "adj_low", "adj_close"), higher_is_better=False),
    FactorDefinition("stale_price_flag", "quality", "价格停滞标记", ("adj_close", "volume"), higher_is_better=False),
    FactorDefinition("extreme_return_flag", "quality", "极端收益标记", ("pct_chg", "ret_5"), higher_is_better=False),
    FactorDefinition("low_history_flag", "quality", "历史长度不足标记", ("rn",), higher_is_better=False),
)


def list_factor_definitions() -> list[FactorDefinition]:
    return list(FACTOR_CATALOG)
