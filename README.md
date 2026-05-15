# tdx-stocks

Local TDX daily data pipeline:

```text
.day -> raw_daily -> checks -> adj_daily -> checks -> factors -> checks -> atomic latest
```

Version 0.1 intentionally does not fetch real corporate actions. It writes an empty
`corporate_actions` table and builds `adj_daily` with `adj_factor = 1.0`, so the full
pipeline can be validated before adding a rights/dividend data source.

## Paths

Default local paths for this workspace:

```text
TDX vipdoc: /mnt/d/ProgramFiles/Tdx/vipdoc
Data root:  /mnt/d/Zcyu/Chary-codex/tdx-stocks/Database
```

## Install

Use Python 3.11+:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

If you do not need dev tools, install without extras:

```bash
python -m pip install -e .
```

## Usage

Create a config file:

```bash
tdx-stocks init-config --path tdx_stocks.toml
```

Inspect the local TDX directory:

```bash
tdx-stocks doctor --config tdx_stocks.toml
```

Run a small smoke build:

```bash
tdx-stocks build --config tdx_stocks.toml --limit-symbols 20 --overwrite-staging
```

Run a full A-share build:

```bash
tdx-stocks build --config tdx_stocks.toml --overwrite-staging
```

The committed dataset is written under:

```text
Database/versions/<run_id>/
Database/latest.json
```

DuckDB temporary files are kept under:

```text
Database/duckdb/tmp/
```

## Inspect Data

All inspection commands read `Database/latest.json` and register DuckDB views named
`raw_daily`, `adj_daily`, `factors`, and `corporate_actions`.

Show current version status:

```bash
tdx-stocks status
```

Show table-level row counts, date ranges, and disk usage:

```bash
tdx-stocks tables
```

Show schema:

```bash
tdx-stocks schema raw_daily
tdx-stocks schema factors
```

Show filtered rows:

```bash
tdx-stocks head raw_daily --symbol 600000 --from-date 2024-01-01 --desc --limit 20
tdx-stocks head factors --columns symbol,trade_date,pct_chg,ma20,range_20 --limit 30
```

Run ad hoc SQL:

```bash
tdx-stocks sql "select symbol, count(*) as row_count, max(trade_date) as last_date from raw_daily group by symbol order by symbol"
```

The SQL session also registers convenience macros:

```bash
tdx-stocks sql "select * from last_n_days('600519.SH', 10)"
tdx-stocks sql "select * from last_n_factors('600519.SH', 10)"
```

Export a filtered result to CSV:

```bash
tdx-stocks export factors --symbol 600000 --from-date 2024-01-01 --to ../Database/exports/factors_600000.csv --limit 1000
```

## Notes

- `raw_daily` stores unadjusted OHLCV parsed from TDX `.day` files.
- `corporate_actions` is present but empty in version 0.1.
- `adj_daily` stores adjusted OHLCV. In version 0.1 values equal raw prices.
- `factors` stores basic derived indicators based on adjusted close.
- `latest.json` is replaced only after all stages and checks complete.
