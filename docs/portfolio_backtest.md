# Portfolio Backtest

`tdx-stocks portfolio backtest` simulates a rebalance schedule with T+1 execution.

Assumptions:

- signals are generated on the rebalance date
- execution happens on the next trading day
- the portfolio is held until the next rebalance cycle
- fees and slippage are applied as basis points
- missing prices are skipped instead of forcing a future lookup

Example:

```bash
tdx-stocks portfolio backtest --from consensus --from-date 2022-01-01 --to-date 2024-12-31 --top 20 --rebalance-days 5
```

Reported metrics include:

- `total_return`
- `annual_return`
- `max_drawdown`
- `volatility`
- `win_rate`
- `turnover`
- `avg_holdings`
- `max_single_weight`
- `market_exposure`

This is a research simulation only. It is not an automatic trading system.

