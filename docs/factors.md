# Factors

## Current contract

The strategy engine reads the latest `factors` table and depends on a stable
core field set:

- `adj_close`
- `ma20`
- `ma60`
- `ret_5`
- `ret_20`
- `amount_ma20`
- `pos_20`
- `dd_20`
- `vol_ratio_20`
- `rsi_14`
- `atr_pct_14`
- `vol_20`

## Compatibility rule

Strategy presets should not require callers to know which SQL expression built
the table. Missing fields should be treated as a data-quality error, not a
silent fallback.

## Planned factor configuration

The long-term goal is to let configured windows add extra factors without
removing required ones. The safe model is:

`configured windows ∪ required windows ∪ technical windows`

This keeps preset behavior stable while still allowing new fields to be added
without editing every strategy by hand.

## Build report

The build report now records:

- `factor_version`
- `configured_windows`
- `effective_ma_windows`
- `effective_ret_windows`
- `effective_range_windows`
- `effective_vol_windows`
