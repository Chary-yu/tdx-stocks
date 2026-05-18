# Strategy Framework

`tdx-stocks` currently exposes a registry-driven strategy entrypoint under `strategy`.

Available commands:

- `tdx-stocks strategy list`
- `tdx-stocks strategy run trend-strength`
- `tdx-stocks strategy run low-vol-breakout`
- `tdx-stocks strategy run ma-pullback`
- `tdx-stocks strategy run relative-strength`
- `tdx-stocks strategy run volume-breakout`

## Output shape

All strategy runners return a report with the same top-level keys:

- `summary`
- `picks`
- `excluded`
- `explain`

This keeps JSON output, table output, exports, and future backtest adapters aligned.

## Compatibility

`trend-strength` remains the compatibility baseline. Existing imports from
`tdx_stocks.strategy` still work.

## Current implementation notes

- Strategy registration lives in `src/tdx_stocks/strategies/registry.py`.
- Shared candidate classification and scoring live in `signals.py` and `scoring.py`.
- Data access lives in `data.py`.
- Hard filters and basic symbol formatting live in `universe.py`.

