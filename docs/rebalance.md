# Rebalance Plan

`tdx-stocks portfolio rebalance-plan` compares current holdings against a target portfolio.

Supported actions:

- `BUY`
- `SELL`
- `HOLD`
- `INCREASE`
- `REDUCE`

Current holdings CSV format:

```csv
market,symbol,weight
sh,600000,0.05
sz,000001,0.04
```

Action rules:

- no current position and a target position exists -> `BUY`
- current position exists and target is removed -> `SELL`
- both exist and the delta is small -> `HOLD`
- target weight is above current weight -> `INCREASE`
- target weight is below current weight -> `REDUCE`

Turnover is reported as:

```text
sum(abs(target_weight - current_weight)) / 2
```

