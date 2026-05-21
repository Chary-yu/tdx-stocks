"""SQL render helpers for staged factor builds."""

# ruff: noqa
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

from .config_validators import validate_compression

WINDOW_SPEC = "PARTITION BY market, symbol ORDER BY trade_date"
DEFAULT_FACTOR_WINDOWS = (5, 10, 20, 60)
DEFAULT_REQUIRED_WINDOWS = (5, 10, 20, 60, 120, 250)
DEFAULT_FIXED_RET_WINDOWS = (1, 5, 10, 20, 60, 120, 250)
DEFAULT_FIXED_MA_WINDOWS = (5, 10, 20, 60, 120, 250)
DEFAULT_FIXED_VOL_WINDOWS = (5, 10, 20, 60)
DEFAULT_FIXED_RANGE_WINDOWS = (20,)
DEFAULT_FIXED_POS_WINDOWS = (20, 60)
DEFAULT_FIXED_DD_WINDOWS = (20, 60)


@dataclass(frozen=True)
class FactorSpec:
    configured_windows: tuple[int, ...] = DEFAULT_FACTOR_WINDOWS
    required_windows: tuple[int, ...] = DEFAULT_REQUIRED_WINDOWS

    @property
    def extra_windows(self) -> tuple[int, ...]:
        required = set(self.required_windows)
        return tuple(window for window in self.configured_windows if window not in required)

    @property
    def effective_windows(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.required_windows).union(self.configured_windows)))

    @property
    def effective_ma_windows(self) -> tuple[int, ...]:
        return self.effective_windows

    @property
    def effective_ret_windows(self) -> tuple[int, ...]:
        return self.effective_windows

    @property
    def effective_range_windows(self) -> tuple[int, ...]:
        return self.effective_windows

    @property
    def effective_vol_windows(self) -> tuple[int, ...]:
        return self.effective_windows


def build_factor_spec(factor_windows: Iterable[int] | None = None) -> FactorSpec:
    configured = _normalize_windows(factor_windows or DEFAULT_FACTOR_WINDOWS)
    return FactorSpec(configured_windows=configured)


def factor_build_report(spec: FactorSpec) -> dict[str, object]:
    extra_windows = list(spec.extra_windows)
    generated_ma_windows = sorted(set(DEFAULT_FIXED_MA_WINDOWS).union(extra_windows))
    generated_ret_windows = sorted(set(DEFAULT_FIXED_RET_WINDOWS).union(extra_windows))
    generated_vol_windows = sorted(set(DEFAULT_FIXED_VOL_WINDOWS).union(extra_windows))
    generated_range_windows = sorted(set(DEFAULT_FIXED_RANGE_WINDOWS).union(extra_windows))
    generated_pos_windows = sorted(set(DEFAULT_FIXED_POS_WINDOWS).union(extra_windows))
    generated_drawdown_windows = sorted(set(DEFAULT_FIXED_DD_WINDOWS).union(extra_windows))
    return {
        "factor_version": "windowed-v1",
        "configured_windows": list(spec.configured_windows),
        "generated_ma_windows": generated_ma_windows,
        "generated_ret_windows": generated_ret_windows,
        "generated_range_windows": generated_range_windows,
        "generated_pos_windows": generated_pos_windows,
        "generated_drawdown_windows": generated_drawdown_windows,
        "generated_vol_windows": generated_vol_windows,
        "effective_ma_windows": generated_ma_windows,
        "effective_ret_windows": generated_ret_windows,
        "effective_range_windows": generated_range_windows,
        "effective_vol_windows": generated_vol_windows,
    }


def parquet_glob(path: Path) -> str:
    return (path / "**" / "*.parquet").as_posix()


def sql_literal(value: str | Path) -> str:
    return str(value).replace("'", "''")


def _window(frame: int) -> str:
    return f"{WINDOW_SPEC} ROWS BETWEEN {frame - 1} PRECEDING AND CURRENT ROW"


def _select_lines(items: Iterable[tuple[str, str]], indent: str = "    ") -> str:
    return ",\n".join(f"{indent}{expr} AS {alias}" for alias, expr in items)


def _stage_header(name: str) -> str:
    return f"-- Stage: {name}"


def _normalize_windows(values: Iterable[int]) -> tuple[int, ...]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw in values:
        window = int(raw)
        if window <= 0:
            raise ValueError(f"factor windows must be positive integers, got {window}")
        if window not in seen:
            seen.add(window)
            normalized.append(window)
    return tuple(sorted(normalized))


def _extra_windows(factor_spec: FactorSpec | None) -> tuple[int, ...]:
    return factor_spec.extra_windows if factor_spec is not None else ()


def _extra_window_metrics(window: int) -> list[tuple[str, str]]:
    window_spec = _window(window)
    return [
        (f"lag_close_{window}", f"lag(adj_close, {window}) OVER ({WINDOW_SPEC})"),
        (f"cnt_{window}", f"count(*) OVER ({window_spec})"),
        (f"ret_cnt_{window}", f"count(pct_chg) OVER ({window_spec})"),
        (f"ma{window}", f"avg(adj_close) OVER ({window_spec})"),
        (f"vol_ma{window}", f"avg(volume) OVER ({window_spec})"),
        (f"high_{window}", f"max(adj_high) OVER ({window_spec})"),
        (f"low_{window}", f"min(adj_low) OVER ({window_spec})"),
        (f"std_pctchg_{window}", f"stddev_samp(pct_chg) OVER ({window_spec})"),
    ]


def _extra_window_technical_items(window: int) -> list[tuple[str, str]]:
    return [
        (f"ma{window}", f"ma{window}"),
        (f"vol_ma{window}", f"vol_ma{window}"),
        (f"high_{window}", f"high_{window}"),
        (f"low_{window}", f"low_{window}"),
        (f"ret_{window}", f"CASE WHEN lag_close_{window} IS NULL THEN NULL ELSE adj_close / lag_close_{window} - 1 END"),
        (f"vol_{window}", f"CASE WHEN ret_cnt_{window} < {window} THEN NULL ELSE std_pctchg_{window} END"),
        (f"bias_{window}", f"CASE WHEN cnt_{window} < {window} OR ma{window} IS NULL OR ma{window} = 0 THEN NULL ELSE adj_close / ma{window} - 1 END"),
        (f"dd_{window}", f"CASE WHEN cnt_{window} < {window} OR high_{window} IS NULL OR low_{window} IS NULL OR high_{window} = low_{window} THEN NULL ELSE adj_close / high_{window} - 1 END"),
        (f"pos_{window}", f"CASE WHEN cnt_{window} < {window} OR high_{window} IS NULL OR low_{window} IS NULL OR high_{window} = low_{window} THEN NULL ELSE (adj_close - low_{window}) / (high_{window} - low_{window}) END"),
        (f"range_{window}", f"CASE WHEN cnt_{window} < {window} OR high_{window} IS NULL OR low_{window} IS NULL OR low_{window} = 0 THEN NULL ELSE high_{window} / low_{window} - 1 END"),
    ]


def build_factors_statements(
    adj_daily_dir: Path,
    output_dir: Path,
    compression: str,
    factor_windows: Iterable[int] | None = None,
    from_date: date | None = None,
    max_window_days: int | None = None,
) -> list[str]:
    factor_spec = build_factor_spec(factor_windows)
    history_from_date = _history_from_date(from_date, factor_spec, max_window_days)
    return [
        render_create_base_data_sql(adj_daily_dir, from_date=history_from_date),
        render_create_rolling_windows_sql(factor_spec),
        render_create_rolling_stats_sql(factor_spec),
        render_create_macd_state_sql(),
        render_create_kdj_inputs_sql(),
        render_create_kdj_state_sql(),
        render_copy_factors_sql(
            output_dir,
            compression,
            factor_spec,
            append_after_date=from_date,
            append=from_date is not None,
        ),
    ]


def render_build_factors_sql(
    adj_daily_dir: Path,
    output_dir: Path,
    compression: str,
    factor_windows: Iterable[int] | None = None,
    from_date: date | None = None,
    max_window_days: int | None = None,
) -> str:
    return (
        ";\n\n".join(
            build_factors_statements(
                adj_daily_dir,
                output_dir,
                compression,
                factor_windows,
                from_date=from_date,
                max_window_days=max_window_days,
            )
        )
        + ";\n"
    )


def render_create_base_data_sql(adj_daily_dir: Path, from_date: date | None = None) -> str:
    source = f"read_parquet('{sql_literal(parquet_glob(adj_daily_dir))}', hive_partitioning=true)"
    source_where = []
    if from_date is not None:
        source_where.append(f"    WHERE trade_date >= DATE '{sql_literal(from_date.isoformat())}'")
    return "\n".join(
        [
            _stage_header("tmp_base_data"),
            "CREATE TEMP TABLE tmp_base_data AS",
            "WITH base_lag AS (",
            "    SELECT",
            "        market,",
            "        symbol,",
            "        trade_date,",
            "        trade_year,",
            "        adj_open,",
            "        adj_high,",
            "        adj_low,",
            "        adj_close,",
            "        volume,",
            "        amount,",
            "        adj_factor,",
            f"        row_number() OVER ({WINDOW_SPEC}) AS rn,",
            f"        lag(adj_close) OVER ({WINDOW_SPEC}) AS prev_close,",
            f"        lag(adj_high) OVER ({WINDOW_SPEC}) AS prev_high,",
            f"        lag(adj_low) OVER ({WINDOW_SPEC}) AS prev_low",
            f"    FROM {source}",
            *source_where,
            ")",
            "SELECT",
            "    market,",
            "    symbol,",
            "    trade_date,",
            "    trade_year,",
            "    adj_open,",
            "    adj_high,",
            "    adj_low,",
            "    adj_close,",
            "    volume,",
            "    amount,",
            "    adj_factor,",
            "    rn,",
            "    prev_close,",
            "    prev_high,",
            "    prev_low,",
            "    CASE WHEN prev_close IS NOT NULL AND adj_open = adj_high AND adj_close > prev_close * 1.04 THEN 1 ELSE 0 END AS is_limit_up,",
            "    CASE WHEN prev_close IS NOT NULL AND adj_open = adj_low AND adj_close < prev_close * 0.96 THEN 1 ELSE 0 END AS is_limit_down,",
            "    CASE WHEN volume = 0 THEN 1 ELSE 0 END AS is_suspended,",
            "    adj_close - prev_close AS diff,",
            "    CASE WHEN prev_close IS NULL OR prev_close = 0 THEN NULL ELSE adj_close / prev_close - 1 END AS pct_chg,",
            "    CASE WHEN adj_close - prev_close > 0 THEN adj_close - prev_close ELSE 0 END AS gain,",
            "    CASE WHEN adj_close - prev_close < 0 THEN prev_close - adj_close ELSE 0 END AS loss,",
            "    (adj_high + adj_low + adj_close) / 3.0 AS tp,",
            "    adj_high - prev_high AS up_move,",
            "    prev_low - adj_low AS down_move,",
            "    CASE",
            "        WHEN prev_close IS NULL OR prev_close = 0 THEN adj_high - adj_low",
            "        ELSE greatest(adj_high - adj_low, abs(adj_high - prev_close), abs(adj_low - prev_close))",
            "    END AS tr,",
            "    CASE",
            "        WHEN prev_close IS NULL OR prev_close = 0 THEN NULL",
            "        ELSE (adj_high - adj_low) / prev_close",
            "    END AS amp_1,",
            "    CASE",
            "        WHEN adj_high - prev_high > prev_low - adj_low AND adj_high - prev_high > 0 THEN adj_high - prev_high",
            "        ELSE 0",
            "    END AS plus_dm,",
            "    CASE",
            "        WHEN prev_low - adj_low > adj_high - prev_high AND prev_low - adj_low > 0 THEN prev_low - adj_low",
            "        ELSE 0",
            "    END AS minus_dm",
            "FROM base_lag",
        ]
    )


def render_create_rolling_windows_sql(factor_spec: FactorSpec | None = None) -> str:
    cols: list[tuple[str, str]] = [
        ("lag_close_5", "lag(adj_close, 5) OVER ({window})".format(window=WINDOW_SPEC)),
        ("lag_close_10", "lag(adj_close, 10) OVER ({window})".format(window=WINDOW_SPEC)),
        ("lag_close_20", "lag(adj_close, 20) OVER ({window})".format(window=WINDOW_SPEC)),
        ("lag_close_60", "lag(adj_close, 60) OVER ({window})".format(window=WINDOW_SPEC)),
        ("lag_close_120", "lag(adj_close, 120) OVER ({window})".format(window=WINDOW_SPEC)),
        ("lag_close_250", "lag(adj_close, 250) OVER ({window})".format(window=WINDOW_SPEC)),
        ("cnt_5", "count(*) OVER ({window})".format(window=_window(5))),
        ("cnt_9", "count(*) OVER ({window})".format(window=_window(9))),
        ("cnt_10", "count(*) OVER ({window})".format(window=_window(10))),
        ("cnt_14", "count(*) OVER ({window})".format(window=_window(14))),
        ("cnt_20", "count(*) OVER ({window})".format(window=_window(20))),
        ("cnt_60", "count(*) OVER ({window})".format(window=_window(60))),
        ("cnt_120", "count(*) OVER ({window})".format(window=_window(120))),
        ("cnt_250", "count(*) OVER ({window})".format(window=_window(250))),
        ("ret_cnt_5", "count(pct_chg) OVER ({window})".format(window=_window(5))),
        ("ret_cnt_6", "count(pct_chg) OVER ({window})".format(window=_window(6))),
        ("ret_cnt_10", "count(pct_chg) OVER ({window})".format(window=_window(10))),
        ("ret_cnt_14", "count(pct_chg) OVER ({window})".format(window=_window(14))),
        ("ret_cnt_20", "count(pct_chg) OVER ({window})".format(window=_window(20))),
        ("ret_cnt_60", "count(pct_chg) OVER ({window})".format(window=_window(60))),
        ("ma5", "avg(adj_close) OVER ({window})".format(window=_window(5))),
        ("ma10", "avg(adj_close) OVER ({window})".format(window=_window(10))),
        ("ma20", "avg(adj_close) OVER ({window})".format(window=_window(20))),
        ("ma60", "avg(adj_close) OVER ({window})".format(window=_window(60))),
        ("ma120", "avg(adj_close) OVER ({window})".format(window=_window(120))),
        ("ma250", "avg(adj_close) OVER ({window})".format(window=_window(250))),
        ("vol_ma5", "avg(volume) OVER ({window})".format(window=_window(5))),
        ("vol_ma20", "avg(volume) OVER ({window})".format(window=_window(20))),
        ("vol_ma60", "avg(volume) OVER ({window})".format(window=_window(60))),
        ("amount_ma20", "avg(amount) OVER ({window})".format(window=_window(20))),
        ("amount_ma60", "avg(amount) OVER ({window})".format(window=_window(60))),
        ("high_9", "max(adj_high) OVER ({window})".format(window=_window(9))),
        ("low_9", "min(adj_low) OVER ({window})".format(window=_window(9))),
        ("high_20", "max(adj_high) OVER ({window})".format(window=_window(20))),
        ("low_20", "min(adj_low) OVER ({window})".format(window=_window(20))),
        ("high_60", "max(adj_high) OVER ({window})".format(window=_window(60))),
        ("low_60", "min(adj_low) OVER ({window})".format(window=_window(60))),
        ("high_120", "max(adj_high) OVER ({window})".format(window=_window(120))),
        ("low_120", "min(adj_low) OVER ({window})".format(window=_window(120))),
        ("high_250", "max(adj_high) OVER ({window})".format(window=_window(250))),
        ("low_250", "min(adj_low) OVER ({window})".format(window=_window(250))),
        ("std_pctchg_5", "stddev_samp(pct_chg) OVER ({window})".format(window=_window(5))),
        ("std_pctchg_10", "stddev_samp(pct_chg) OVER ({window})".format(window=_window(10))),
        ("std_pctchg_20", "stddev_samp(pct_chg) OVER ({window})".format(window=_window(20))),
        ("std_pctchg_60", "stddev_samp(pct_chg) OVER ({window})".format(window=_window(60))),
        ("sum_gain_6", "sum(gain) OVER ({window})".format(window=_window(6))),
        ("sum_loss_6", "sum(loss) OVER ({window})".format(window=_window(6))),
        ("sum_gain_14", "sum(gain) OVER ({window})".format(window=_window(14))),
        ("sum_loss_14", "sum(loss) OVER ({window})".format(window=_window(14))),
        ("sum_tr_14", "sum(tr) OVER ({window})".format(window=_window(14))),
        ("sum_plus_dm_14", "sum(plus_dm) OVER ({window})".format(window=_window(14))),
        ("sum_minus_dm_14", "sum(minus_dm) OVER ({window})".format(window=_window(14))),
        ("tp_ma20", "avg(tp) OVER ({window})".format(window=_window(20))),
        ("tp_std20", "stddev_samp(tp) OVER ({window})".format(window=_window(20))),
        ("close_std20", "stddev_samp(adj_close) OVER ({window})".format(window=_window(20))),
        ("close_std60", "stddev_samp(adj_close) OVER ({window})".format(window=_window(60))),
    ]
    for window in _extra_windows(factor_spec):
        cols.extend(_extra_window_metrics(window))
    base_cols = [
        ("market", "market"),
        ("symbol", "symbol"),
        ("trade_date", "trade_date"),
        ("trade_year", "trade_year"),
        ("adj_open", "adj_open"),
        ("adj_high", "adj_high"),
        ("adj_low", "adj_low"),
        ("adj_close", "adj_close"),
        ("volume", "volume"),
        ("amount", "amount"),
        ("adj_factor", "adj_factor"),
        ("rn", "rn"),
        ("prev_close", "prev_close"),
        ("prev_high", "prev_high"),
        ("prev_low", "prev_low"),
        ("is_limit_up", "is_limit_up"),
        ("is_limit_down", "is_limit_down"),
        ("is_suspended", "is_suspended"),
        ("diff", "diff"),
        ("pct_chg", "pct_chg"),
        ("gain", "gain"),
        ("loss", "loss"),
        ("tp", "tp"),
        ("up_move", "up_move"),
        ("down_move", "down_move"),
        ("tr", "tr"),
        ("amp_1", "amp_1"),
        ("plus_dm", "plus_dm"),
        ("minus_dm", "minus_dm"),
    ]
    return "\n".join(
        [
            _stage_header("tmp_rolling_windows"),
            "CREATE TEMP TABLE tmp_rolling_windows AS",
            "SELECT",
            _select_lines(base_cols + cols),
            "FROM tmp_base_data",
            f"WINDOW w AS ({WINDOW_SPEC})",
        ]
    )


def render_create_rolling_stats_sql(factor_spec: FactorSpec | None = None) -> str:
    extra_windows = _extra_windows(factor_spec)
    technical_lines = [
        "    SELECT",
        "        market,",
        "        symbol,",
        "        trade_date,",
        "        trade_year,",
        "        adj_open,",
        "        adj_high,",
        "        adj_low,",
        "        adj_close,",
        "        volume,",
        "        amount,",
        "        adj_factor,",
        "        rn,",
        "        prev_close,",
        "        prev_high,",
        "        prev_low,",
        "        is_limit_up,",
        "        is_limit_down,",
        "        is_suspended,",
        "        diff,",
        "        pct_chg,",
        "        pct_chg AS ret_1,",
        "        CASE WHEN lag_close_5 IS NULL THEN NULL ELSE adj_close / lag_close_5 - 1 END AS ret_5,",
        "        CASE WHEN lag_close_10 IS NULL THEN NULL ELSE adj_close / lag_close_10 - 1 END AS ret_10,",
        "        CASE WHEN lag_close_20 IS NULL THEN NULL ELSE adj_close / lag_close_20 - 1 END AS ret_20,",
        "        CASE WHEN lag_close_60 IS NULL THEN NULL ELSE adj_close / lag_close_60 - 1 END AS ret_60,",
        "        CASE WHEN lag_close_120 IS NULL THEN NULL ELSE adj_close / lag_close_120 - 1 END AS ret_120,",
        "        CASE WHEN lag_close_250 IS NULL THEN NULL ELSE adj_close / lag_close_250 - 1 END AS ret_250,",
        "        gain,",
        "        loss,",
        "        tp,",
        "        up_move,",
        "        down_move,",
        "        tr,",
        "        amp_1,",
        "        plus_dm,",
        "        minus_dm,",
        "        lag_close_5,",
        "        lag_close_10,",
        "        lag_close_20,",
        "        lag_close_60,",
        "        lag_close_120,",
        "        lag_close_250,",
        "        cnt_5,",
        "        cnt_9,",
        "        cnt_10,",
        "        cnt_14,",
        "        cnt_20,",
        "        cnt_60,",
        "        cnt_120,",
        "        cnt_250,",
        "        ret_cnt_5,",
        "        ret_cnt_6,",
        "        ret_cnt_10,",
        "        ret_cnt_14,",
        "        ret_cnt_20,",
        "        ret_cnt_60,",
        "        ma5,",
        "        ma10,",
        "        ma20,",
        "        ma60,",
        "        ma120,",
        "        ma250,",
        "        vol_ma5,",
        "        vol_ma20,",
        "        vol_ma60,",
        "        amount_ma20,",
        "        amount_ma60,",
        "        high_9,",
        "        low_9,",
        "        high_20,",
        "        low_20,",
        "        high_60,",
        "        low_60,",
        "        high_120,",
        "        low_120,",
        "        high_250,",
        "        low_250,",
        "        std_pctchg_5,",
        "        std_pctchg_10,",
        "        std_pctchg_20,",
        "        std_pctchg_60,",
        "        sum_gain_6,",
        "        sum_loss_6,",
        "        sum_gain_14,",
        "        sum_loss_14,",
        "        sum_tr_14,",
        "        sum_plus_dm_14,",
        "        sum_minus_dm_14,",
        "        tp_ma20,",
        "        tp_std20,",
        "        close_std20,",
        "        close_std60,",
        "        CASE WHEN cnt_14 < 14 OR sum_tr_14 IS NULL OR sum_tr_14 = 0 THEN NULL ELSE 100.0 * sum_plus_dm_14 / sum_tr_14 END AS plus_di_14,",
        "        CASE WHEN cnt_14 < 14 OR sum_tr_14 IS NULL OR sum_tr_14 = 0 THEN NULL ELSE 100.0 * sum_minus_dm_14 / sum_tr_14 END AS minus_di_14,",
        "        CASE WHEN cnt_9 < 9 OR high_9 IS NULL OR low_9 IS NULL OR high_9 = low_9 THEN NULL ELSE (adj_close - low_9) / (high_9 - low_9) * 100 END AS rsv_9,",
        "        CASE WHEN ret_cnt_5 < 5 THEN NULL ELSE std_pctchg_5 END AS vol_5,",
        "        CASE WHEN ret_cnt_10 < 10 THEN NULL ELSE std_pctchg_10 END AS vol_10,",
        "        CASE WHEN ret_cnt_20 < 20 THEN NULL ELSE std_pctchg_20 END AS vol_20,",
        "        CASE WHEN ret_cnt_60 < 60 THEN NULL ELSE std_pctchg_60 END AS vol_60,",
        "        CASE WHEN cnt_20 < 20 OR vol_ma20 IS NULL OR vol_ma20 = 0 THEN NULL ELSE volume / vol_ma20 - 1 END AS vol_ratio_20,",
        "        CASE WHEN cnt_60 < 60 OR vol_ma60 IS NULL OR vol_ma60 = 0 THEN NULL ELSE vol_ma5 / vol_ma60 END AS vol_ratio_5_60,",
        "        CASE WHEN cnt_5 < 5 OR ma5 IS NULL OR ma5 = 0 THEN NULL ELSE adj_close / ma5 - 1 END AS bias_5,",
        "        CASE WHEN cnt_10 < 10 OR ma10 IS NULL OR ma10 = 0 THEN NULL ELSE adj_close / ma10 - 1 END AS bias_10,",
        "        CASE WHEN cnt_20 < 20 OR ma20 IS NULL OR ma20 = 0 THEN NULL ELSE adj_close / ma20 - 1 END AS bias_20,",
        "        CASE WHEN cnt_60 < 60 OR ma60 IS NULL OR ma60 = 0 THEN NULL ELSE adj_close / ma60 - 1 END AS bias_60,",
        "        CASE WHEN cnt_20 < 20 OR ma20 IS NULL OR ma20 = 0 THEN NULL ELSE ma5 / ma20 - 1 END AS ma_cross_5_20,",
        "        CASE WHEN cnt_60 < 60 OR ma60 IS NULL OR ma60 = 0 THEN NULL ELSE ma20 / ma60 - 1 END AS ma_cross_20_60,",
        "        CASE WHEN cnt_20 < 20 OR high_20 IS NULL OR low_20 IS NULL OR high_20 = low_20 THEN NULL ELSE adj_close / high_20 - 1 END AS dd_20,",
        "        CASE WHEN cnt_60 < 60 OR high_60 IS NULL OR low_60 IS NULL OR high_60 = low_60 THEN NULL ELSE adj_close / high_60 - 1 END AS dd_60,",
        "        CASE WHEN cnt_20 < 20 OR high_20 IS NULL OR low_20 IS NULL OR high_20 = low_20 THEN NULL ELSE (adj_close - low_20) / (high_20 - low_20) END AS pos_20,",
        "        CASE WHEN cnt_60 < 60 OR high_60 IS NULL OR low_60 IS NULL OR high_60 = low_60 THEN NULL ELSE (adj_close - low_60) / (high_60 - low_60) END AS pos_60,",
        "        CASE WHEN cnt_20 < 20 OR high_20 IS NULL OR low_20 IS NULL OR low_20 = 0 THEN NULL ELSE high_20 / low_20 - 1 END AS range_20,",
        "        CASE WHEN cnt_14 < 14 THEN NULL ELSE sum_tr_14 / 14 END AS atr_14,",
        "        CASE WHEN cnt_14 < 14 OR adj_close IS NULL OR adj_close = 0 THEN NULL ELSE (sum_tr_14 / 14) / adj_close END AS atr_pct_14,",
        "        CASE WHEN cnt_20 < 20 THEN NULL ELSE ma20 END AS bb_mid_20,",
        "        CASE WHEN cnt_20 < 20 THEN NULL ELSE close_std20 END AS bb_std_20,",
        "        CASE WHEN cnt_20 < 20 THEN NULL ELSE ma20 + 2 * close_std20 END AS bb_upper_20,",
        "        CASE WHEN cnt_20 < 20 THEN NULL ELSE ma20 - 2 * close_std20 END AS bb_lower_20,",
        "        CASE WHEN cnt_20 < 20 OR ma20 IS NULL OR ma20 = 0 THEN NULL ELSE 4 * close_std20 / ma20 END AS bb_width_20,",
        "        CASE WHEN cnt_20 < 20 OR close_std20 IS NULL OR close_std20 = 0 THEN NULL ELSE (adj_close - ma20) / close_std20 END AS bb_z_20,",
        "        CASE WHEN cnt_20 < 20 THEN NULL ELSE corr(adj_close, volume) OVER ({window}) END AS price_vol_corr_20,".format(window=_window(20)),
        "        CASE WHEN ret_cnt_14 < 14 OR sum_loss_14 IS NULL THEN NULL WHEN sum_loss_14 = 0 AND sum_gain_14 = 0 THEN NULL WHEN sum_loss_14 = 0 THEN 100 ELSE 100 - 100 / (1 + (sum_gain_14 / 14) / (sum_loss_14 / 14)) END AS rsi_14,",
        "        CASE WHEN ret_cnt_6 < 6 OR sum_loss_6 IS NULL THEN NULL WHEN sum_loss_6 = 0 AND sum_gain_6 = 0 THEN NULL WHEN sum_loss_6 = 0 THEN 100 ELSE 100 - 100 / (1 + (sum_gain_6 / 6) / (sum_loss_6 / 6)) END AS rsi_6,",
        "        CASE WHEN cnt_20 < 20 OR tp_std20 IS NULL OR tp_std20 = 0 THEN NULL ELSE (tp - tp_ma20) / (0.015 * tp_std20) END AS cci_20,",
        "        CASE WHEN cnt_14 < 14 OR sum_plus_dm_14 IS NULL OR sum_tr_14 IS NULL OR sum_tr_14 = 0 OR sum_plus_dm_14 + sum_minus_dm_14 = 0 THEN NULL ELSE 100 * abs((100 * sum_plus_dm_14 / sum_tr_14) - (100 * sum_minus_dm_14 / sum_tr_14)) / ((100 * sum_plus_dm_14 / sum_tr_14) + (100 * sum_minus_dm_14 / sum_tr_14)) END AS dx_14",
    ]
    if extra_windows:
        technical_lines[-1] += ","
    for window in extra_windows:
        for alias, expr in _extra_window_technical_items(window):
            technical_lines.append(f"        {expr} AS {alias},")
    if extra_windows:
        technical_lines[-1] = technical_lines[-1].rstrip(",")

    final_lines = [
        "    market,",
        "    symbol,",
        "    trade_date,",
        "    trade_year,",
        "    adj_close,",
        "    rn,",
        "    is_limit_up,",
        "    is_limit_down,",
        "    is_suspended,",
        "    pct_chg,",
        "    ret_1,",
        "    ret_5,",
        "    ret_10,",
        "    ret_20,",
        "    ret_60,",
        "    ret_120,",
        "    ret_250,",
        "    adj_close,",
        "    ma5,",
        "    ma10,",
        "    ma20,",
        "    ma60,",
        "    ma120,",
        "    ma250,",
        "    vol_ma5,",
        "    vol_ma20,",
        "    vol_5,",
        "    vol_10,",
        "    vol_20,",
        "    vol_60,",
        "    std_pctchg_5,",
        "    std_pctchg_10,",
        "    std_pctchg_20,",
        "    std_pctchg_60,",
        "    high_60,",
        "    low_60,",
        "    high_120,",
        "    low_120,",
        "    high_250,",
        "    low_250,",
        "    high_20,",
        "    low_20,",
        "    range_20,",
        "    dd_20,",
        "    dd_60,",
        "    pos_20,",
        "    pos_60,",
        "    tr,",
        "    atr_14,",
        "    atr_pct_14,",
        "    bb_mid_20,",
        "    bb_std_20,",
        "    bb_upper_20,",
        "    bb_lower_20,",
        "    bb_width_20,",
        "    bb_z_20,",
        "    rsi_6,",
        "    rsi_14,",
        "    bias_5,",
        "    bias_10,",
        "    bias_20,",
        "    bias_60,",
        "    ma_cross_5_20,",
        "    ma_cross_20_60,",
        "    rsv_9,",
        "    plus_di_14,",
        "    minus_di_14,",
        "    amount_ma20,",
        "    amount_ma60,",
        "    vol_ratio_20,",
        "    vol_ratio_5_60,",
        "    price_vol_corr_20,",
        "    amp_1,",
        "    cci_20,",
    ]
    for window in extra_windows:
        final_lines.extend(
            [
                f"    ret_{window},",
                f"    ma{window},",
                f"    vol_ma{window},",
                f"    vol_{window},",
                f"    high_{window},",
                f"    low_{window},",
                f"    range_{window},",
                f"    dd_{window},",
                f"    pos_{window},",
                f"    bias_{window},",
            ]
        )
    final_lines.append(
        "    CASE WHEN cnt_14 < 14 THEN NULL ELSE least(100.0, greatest(0.0, ROUND(avg(dx_14) OVER (PARTITION BY market, symbol ORDER BY trade_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW), 6))) END AS adx_14"
    )

    return "\n".join(
        [
            _stage_header("tmp_rolling_stats"),
            "CREATE TEMP TABLE tmp_rolling_stats AS",
            "WITH technical AS (",
            *technical_lines,
            "    FROM tmp_rolling_windows",
            ")",
            "SELECT",
            *final_lines,
            "FROM technical",
        ]
    )


def render_create_macd_state_sql() -> str:
    return "\n".join(
        [
            _stage_header("tmp_macd_state"),
            "CREATE TEMP TABLE tmp_macd_state AS",
            "WITH RECURSIVE macd AS (",
            "    SELECT",
            "        market,",
            "        symbol,",
            "        trade_date,",
            "        trade_year,",
            "        rn,",
            "        adj_close::DOUBLE AS adj_close,",
            "        adj_close::DOUBLE AS ema12_state,",
            "        adj_close::DOUBLE AS ema26_state,",
            "        0.0::DOUBLE AS macd_dif,",
            "        0.0::DOUBLE AS macd_dea,",
            "        0.0::DOUBLE AS macd_hist",
            "    FROM tmp_base_data",
            "    WHERE rn = 1",
            "    UNION ALL",
            "    SELECT",
            "        s.market,",
            "        s.symbol,",
            "        s.trade_date,",
            "        s.trade_year,",
            "        s.rn,",
            "        s.adj_close::DOUBLE,",
            "        2.0 / 13.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 13.0) * m.ema12_state AS ema12_state,",
            "        2.0 / 27.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 27.0) * m.ema26_state AS ema26_state,",
            "        (2.0 / 13.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 13.0) * m.ema12_state) - (2.0 / 27.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 27.0) * m.ema26_state) AS macd_dif,",
            "        2.0 / 10.0 * ((2.0 / 13.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 13.0) * m.ema12_state) - (2.0 / 27.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 27.0) * m.ema26_state)) + (1.0 - 2.0 / 10.0) * m.macd_dea AS macd_dea,",
            "        2.0 * ((2.0 / 13.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 13.0) * m.ema12_state) - (2.0 / 27.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 27.0) * m.ema26_state)) - 2.0 * (2.0 / 10.0 * ((2.0 / 13.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 13.0) * m.ema12_state) - (2.0 / 27.0 * s.adj_close::DOUBLE + (1.0 - 2.0 / 27.0) * m.ema26_state)) + (1.0 - 2.0 / 10.0) * m.macd_dea) AS macd_hist",
            "    FROM macd AS m",
            "    JOIN tmp_base_data AS s",
            "        ON s.market = m.market",
            "        AND s.symbol = m.symbol",
            "        AND s.rn = m.rn + 1",
            ")",
            "SELECT market, symbol, trade_date, trade_year, rn, macd_dif, macd_dea, macd_hist",
            "FROM macd",
        ]
    )


def render_create_kdj_inputs_sql() -> str:
    return "\n".join(
        [
            _stage_header("tmp_kdj_inputs"),
            "CREATE TEMP TABLE tmp_kdj_inputs AS",
            "SELECT",
            "    market,",
            "    symbol,",
            "    trade_date,",
            "    trade_year,",
            "    rn,",
            "    rsv_9,",
            "    row_number() OVER (PARTITION BY market, symbol ORDER BY trade_date) AS kdj_valid_rn",
            "FROM tmp_rolling_stats",
            "WHERE rsv_9 IS NOT NULL",
        ]
    )


def render_create_kdj_state_sql() -> str:
    return "\n".join(
        [
            _stage_header("tmp_kdj_state"),
            "CREATE TEMP TABLE tmp_kdj_state AS",
            "WITH RECURSIVE kdj AS (",
            "    SELECT",
            "        market,",
            "        symbol,",
            "        trade_date,",
            "        trade_year,",
            "        rn,",
            "        kdj_valid_rn,",
            "        rsv_9,",
            "        2.0 / 3.0 * 50.0 + 1.0 / 3.0 * rsv_9 AS k_9,",
            "        2.0 / 3.0 * 50.0 + 1.0 / 3.0 * (2.0 / 3.0 * 50.0 + 1.0 / 3.0 * rsv_9) AS d_9,",
            "        3.0 * (2.0 / 3.0 * 50.0 + 1.0 / 3.0 * rsv_9) - 2.0 * (2.0 / 3.0 * 50.0 + 1.0 / 3.0 * (2.0 / 3.0 * 50.0 + 1.0 / 3.0 * rsv_9)) AS j_9",
            "    FROM tmp_kdj_inputs",
            "    WHERE kdj_valid_rn = 1",
            "    UNION ALL",
            "    SELECT",
            "        i.market,",
            "        i.symbol,",
            "        i.trade_date,",
            "        i.trade_year,",
            "        i.rn,",
            "        i.kdj_valid_rn,",
            "        i.rsv_9,",
            "        2.0 / 3.0 * m.k_9 + 1.0 / 3.0 * i.rsv_9 AS k_9,",
            "        2.0 / 3.0 * m.d_9 + 1.0 / 3.0 * (2.0 / 3.0 * m.k_9 + 1.0 / 3.0 * i.rsv_9) AS d_9,",
            "        3.0 * (2.0 / 3.0 * m.k_9 + 1.0 / 3.0 * i.rsv_9) - 2.0 * (2.0 / 3.0 * m.d_9 + 1.0 / 3.0 * (2.0 / 3.0 * m.k_9 + 1.0 / 3.0 * i.rsv_9)) AS j_9",
            "    FROM kdj AS m",
            "    JOIN tmp_kdj_inputs AS i",
            "        ON i.market = m.market",
            "        AND i.symbol = m.symbol",
            "        AND i.kdj_valid_rn = m.kdj_valid_rn + 1",
            ")",
            "SELECT market, symbol, trade_date, trade_year, rn, kdj_valid_rn, rsv_9, k_9, d_9, j_9",
            "FROM kdj",
        ]
    )


def render_copy_factors_sql(
    output_dir: Path,
    compression: str,
    factor_spec: FactorSpec | None = None,
    append_after_date: date | None = None,
    append: bool = False,
) -> str:
    compression = validate_compression(compression)
    columns = [
        "market",
        "symbol",
        "trade_date",
        "trade_year",
        "adj_close",
        "is_limit_up",
        "is_limit_down",
        "is_suspended",
        "pct_chg",
        "ret_1",
        "ret_5",
        "ret_10",
        "ret_20",
        "ret_60",
        "ret_120",
        "ret_250",
        "ma5",
        "ma10",
        "ma20",
        "ma60",
        "ma120",
        "ma250",
        "vol_ma5",
        "vol_ma20",
        "vol_5",
        "vol_10",
        "vol_20",
        "vol_60",
        "std_pctchg_5",
        "std_pctchg_10",
        "std_pctchg_20",
        "std_pctchg_60",
        "high_60",
        "low_60",
        "high_120",
        "low_120",
        "high_250",
        "low_250",
        "high_20",
        "low_20",
        "range_20",
        "dd_20",
        "dd_60",
        "pos_20",
        "pos_60",
        "tr",
        "atr_14",
        "atr_pct_14",
        "bb_mid_20",
        "bb_std_20",
        "bb_upper_20",
        "bb_lower_20",
        "bb_width_20",
        "bb_z_20",
        "rsi_6",
        "rsi_14",
        "bias_5",
        "bias_10",
        "bias_20",
        "bias_60",
        "ma_cross_5_20",
        "ma_cross_20_60",
        "rsv_9",
        "k_9",
        "d_9",
        "j_9",
        "plus_di_14",
        "minus_di_14",
        "adx_14",
        "amount_ma20",
        "amount_ma60",
        "vol_ratio_20",
        "vol_ratio_5_60",
        "price_vol_corr_20",
        "amp_1",
        "cci_20",
        "macd_dif",
        "macd_dea",
        "macd_hist",
    ]
    for window in _extra_windows(factor_spec):
        columns.extend(
            [
                f"ret_{window}",
                f"ma{window}",
                f"vol_ma{window}",
                f"vol_{window}",
                f"high_{window}",
                f"low_{window}",
                f"range_{window}",
                f"dd_{window}",
                f"pos_{window}",
                f"bias_{window}",
            ]
        )
    select_items: list[tuple[str, str]] = []
    for column in columns:
        if column in {"macd_dif", "macd_dea", "macd_hist"}:
            expr = f"macd.{column}"
        elif column in {"k_9", "d_9", "j_9"}:
            expr = f"kdj.{column}"
        elif column == "rsv_9":
            expr = "s.rsv_9"
        else:
            expr = f"s.{column}"
        select_items.append((column, expr))
    where_lines = []
    if append_after_date is not None:
        where_lines.append(f"    WHERE s.trade_date > DATE '{sql_literal(append_after_date.isoformat())}'")
    copy_options = f"(FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION {compression}"
    if append:
        copy_options += ", APPEND"
    copy_options += ")"

    return "\n".join(
        [
            _stage_header("copy_factors"),
            "COPY (",
            "    SELECT",
            _select_lines(select_items),
            "    FROM tmp_rolling_stats AS s",
            "    LEFT JOIN tmp_macd_state AS macd USING (market, symbol, trade_date, trade_year, rn)",
            "    LEFT JOIN tmp_kdj_state AS kdj USING (market, symbol, trade_date, trade_year, rn)",
            *where_lines,
            ")",
            f"TO '{sql_literal(output_dir.as_posix())}'",
            copy_options,
        ]
    )


def _history_from_date(
    from_date: date | None,
    factor_spec: FactorSpec,
    max_window_days: int | None,
) -> date | None:
    if from_date is None:
        return None
    window_days = max_window_days if max_window_days is not None else max(factor_spec.effective_windows)
    return from_date - timedelta(days=window_days)
