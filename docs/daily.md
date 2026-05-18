# Daily Workflow

`tdx-stocks daily run` is the recommended entry point for the end-to-end
research workflow.

## What It Does

The workflow is orchestration only:

1. load config
2. load the latest dataset
3. collect data quality summary
4. run strategies
5. save strategy reports
6. build strategy compare
7. build strategy consensus
8. build portfolio
9. run portfolio risk checks
10. build rebalance plan when current holdings are provided
11. generate daily report
12. save manifest

By default it does not rebuild data. Pass `--build` only when you want to
refresh the dataset before running the daily workflow.

## Config

The main config file supports a `[daily]` section. The first release supports
these fields:

- `enabled_strategies`
- `strategy_limit`
- `strategy_min_score`
- `consensus_min_hit`
- `consensus_limit`
- `portfolio_top`
- `portfolio_weighting`
- `exclude_risk_tags`

## Commands

Run the workflow:

```bash
tdx-stocks daily run --config tdx_stocks.toml
```

Check the latest status:

```bash
tdx-stocks daily status --config tdx_stocks.toml
```

Render a saved report:

```bash
tdx-stocks daily report --as-of latest --config tdx_stocks.toml
```

Use `--format json` when you want machine-readable output.

## Save Paths

Daily reports are saved under:

```text
Database/reports/daily/latest.json
Database/reports/daily/latest.md
Database/reports/daily/by_date/YYYY-MM-DD/daily_report.json
Database/reports/daily/by_date/YYYY-MM-DD/daily_report.md
Database/reports/daily/by_date/YYYY-MM-DD/manifest.json
```

## Limits

- No automatic trading
- No broker integration
- No HTML report in this version
