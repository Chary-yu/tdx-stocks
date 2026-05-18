# Portfolio Risk

Portfolio risk checks summarize the target basket before rebalance or backtest.

Checks include:

- single-position max weight
- position count
- market exposure
- high-risk tag counts
- average `risk_score`
- low-liquidity count
- missing required fields
- weight sum anomalies

The result shape is:

- `passed`
- `violations`
- `warnings`
- `summary`

Example:

```bash
tdx-stocks portfolio risk --portfolio latest
```

