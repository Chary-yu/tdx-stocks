# Strategy Framework

`tdx-stocks` exposes strategy metadata through `query` and strategy execution
through `run`.

Available commands:

- `tdx-stocks query strategies`
- `tdx-stocks query strategy trend-strength`
- `tdx-stocks query strategy trend-strength --symbol 600000.SH --explain`
- `tdx-stocks run signal`
- `tdx-stocks run daily`

## Output shape

All strategy runners return a report with the same top-level keys:

- `summary`
- `picks`
- `excluded`
- `explain`

This keeps JSON output, table output, exports, and future backtest adapters aligned.

## Compatibility

`trend-strength` remains the compatibility baseline. Existing imports from
`tdx_stocks.strategy` still work for internal code.

## Current implementation notes

- Strategy registration lives in `src/tdx_stocks/strategies/registry.py`.
- Shared candidate classification and scoring live in `signals.py` and `scoring.py`.
- Data access lives in `data.py`.
- Hard filters and basic symbol formatting live in `universe.py`.
