# Experiment Templates

`tdx-stocks init` creates a starter workspace with these configs:

- `experiments/daily.toml`
- `experiments/signal.toml`
- `experiments/backtest.toml`
- `experiments/grid_search.toml`
- `experiments/portfolio.toml`
- `experiments/rebalance.toml`

All templates are plain TOML files. They define a `[task]` section with a
`type` field, plus task-specific sections such as `[strategies]`, `[backtest]`,
`[portfolio]`, and `[rebalance]`.

Suggested start:

```bash
tdx-stocks run experiments/daily.toml
```

Suggested follow-up:

```bash
tdx-stocks run experiments/backtest.toml
tdx-stocks run experiments/portfolio.toml
```
