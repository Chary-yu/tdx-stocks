# tdx-stocks

Local TDX daily data pipeline:

```text
.day -> raw_daily -> checks -> adj_daily / hfq_daily -> checks -> factors -> checks -> atomic latest
```

`data update` refreshes the cached `corporate_actions` and
`adjustment_factors` tables. `data build` and `data rebuild` only consume those
local caches and do not fetch new rights/dividend data automatically. `data sync`
is the recommended macro command for refreshing export-derived data and
rebuilding the dataset. The legacy `sync` alias remains available for
compatibility.

Recommended workflow:

```text
init -> data sync -> run <config.toml> -> ui
```

Quick copy-paste commands:

```bash
./.venv/bin/python -m unittest tests.test_pipeline -q
./.venv/bin/python -m unittest tests.test_duckdb_ops -q
./.venv/bin/python -m unittest tests.test_adjustment_verify -q
./.venv/bin/python -m unittest tests.test_lock -q
./.venv/bin/python -m unittest discover -s tests -q
```

## Paths

Default local paths for this workspace:

```text
TDX vipdoc:   (set in config or TDX_STOCKS_TDX_VIPDOC)
TDX export:   (set in config or TDX_STOCKS_TDX_EXPORT)
Data root:    ./Database
Plugin dir:   ~/.tdx-stocks/plugins
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

CLI 手册见 `docs/cli_manual.md`，摘要版可用 `tdx-stocks help-summary` 或 `tools/generate_cli_help_summary.py` 生成到 `docs/cli_help_summary.md`。

New workflow docs:

- `docs/advanced_cli.md`
- `docs/experiments.md`
- `docs/run_config.md`

Strategy and portfolio docs:

- `docs/strategies.md`
- `docs/strategy_explain.md`
- `docs/strategy_examples.md`
- `docs/portfolio.md`
- `docs/portfolio_backtest.md`
- `docs/rebalance.md`
- `docs/risk.md`
- `docs/daily.md`

Main entry points:

```bash
tdx-stocks init
tdx-stocks data sync
tdx-stocks run experiments/daily.toml
tdx-stocks ui
tdx-stocks status
tdx-stocks report
tdx-stocks examples
tdx-stocks doctor
```

Create a config file:

```bash
tdx-stocks init --data-root ./Database
```

The generated template leaves `tdx_vipdoc` and `tdx_export` empty so you can
fill them explicitly or provide `TDX_STOCKS_TDX_VIPDOC` /
`TDX_STOCKS_TDX_EXPORT` at runtime.

Sync the local dataset:

```bash
tdx-stocks data sync --config tdx_stocks.toml
```

Inspect the local TDX directory:

```bash
tdx-stocks doctor --config tdx_stocks.toml
```

`doctor` now reports missing required paths as explicit errors and
suggests the matching environment variable fallback.

Inspect a stock in read-only mode:

```bash
tdx-stocks query price 600519.SH --config tdx_stocks.toml
```

Run a small smoke build:

```bash
tdx-stocks data build --config tdx_stocks.toml --limit-symbols 20 --overwrite-staging
```

Run a full A-share build:

```bash
tdx-stocks data build --config tdx_stocks.toml --overwrite-staging
```

Clear `Database/` and rebuild from local TDX data:

```bash
tdx-stocks data rebuild --config tdx_stocks.toml --overwrite-staging
```

Refresh cached rights/dividend data separately:

```bash
tdx-stocks data update --config tdx_stocks.toml --source file --input action_inputs/
tdx-stocks data update --config tdx_stocks.toml --source export
tdx-stocks data update --config tdx_stocks.toml --source export --dry-run
tdx-stocks data status --config tdx_stocks.toml
tdx-stocks audit verify 600519.SH --config tdx_stocks.toml
tdx-stocks sync --config tdx_stocks.toml --dry-run
```

Use `data status --json` when you want to inspect the current cache and the
latest update report from tooling or `jq`. `data update --dry-run` now writes
`action_update_report.dry_run.json` in addition to the legacy report file so
dry-run results can be inspected without mutating cache tables.

Use `audit verify --json` when you want to compare `adj_daily` against a
specific TDX export file from tooling or `jq`.

Web UI entry point:

```bash
tdx-stocks ui --config tdx_stocks.toml
```

The packaged import path is `tdx_stocks.web.app`.

`data build` and `data rebuild` print stage progress to stderr while they run.
Internally the factor build now runs in staged DuckDB temp tables so the heavy
rolling-window and recursive calculations stay easier to debug and less memory
hungry than one giant query.

The new portfolio layer is research-only:

- It can build target baskets from strategy or consensus candidates.
- It can generate rebalance plans and portfolio backtests.
- It does not connect to broker APIs.
- It does not place automatic trades.

Recommended daily entry point:

```bash
tdx-stocks run experiments/daily.toml
```

`run` reads the experiment TOML and dispatches to the matching runner.
`daily run` remains available as a compatibility command for direct orchestration.

Daily reports are written under:

```text
Database/reports/daily/latest.json
Database/reports/daily/latest.md
Database/reports/daily/by_date/YYYY-MM-DD/daily_report.json
Database/reports/daily/by_date/YYYY-MM-DD/daily_report.md
Database/reports/daily/by_date/YYYY-MM-DD/manifest.json
```

The daily workflow is orchestration only. It reuses the strategy, consensus,
portfolio, risk, and rebalance modules and does not place automatic trades.

## Test Map

If you want to verify a specific feature, run the matching test case below:

| 功能 | 测试用例 |
| --- | --- |
| 重建时保留缓存 | `tests.test_pipeline.PipelineTest.test_rebuild_dataset_preserves_cache_and_clears_staging` |
| `build` / `rebuild` 进度输出 | `tests.test_pipeline.PipelineTest.test_build_and_rebuild_commands_pass_progress` |
| `update-actions` 进度输出 | `tests.test_pipeline.PipelineTest.test_update_actions_command_passes_progress` |
| 导出源正常反推因子 | `tests.test_pipeline.PipelineTest.test_export_source_derives_adjustment_factors` |
| 导出源跳过非正价格行 | `tests.test_pipeline.PipelineTest.test_export_source_skips_nonpositive_export_rows` |
| `update-actions --dry-run` 报告跳过项 | `tests.test_pipeline.PipelineTest.test_update_actions_export_dry_run_reports_skipped_symbols` |
| 缓存状态与最近更新报告 | `tests.test_pipeline.PipelineTest.test_actions_status_reports_cache_and_update_report` |
| 复权对账零误差 | `tests.test_adjustment_verify.AdjustmentVerifyTest.test_verify_adjustment_reports_zero_error` |
| 复权对账偏差样本 | `tests.test_adjustment_verify.AdjustmentVerifyTest.test_verify_adjustment_reports_mismatch` |
| 稠密因子表 ASOF 结果等价 | `tests.test_duckdb_ops.CopyAdjDailyTest.test_dense_factor_map_matches_exact_trade_dates` |
| 稀疏区间因子跨停牌缺口 | `tests.test_duckdb_ops.CopyAdjDailyTest.test_sparse_interval_map_crosses_suspended_ex_date_gap` |
| 查询宏 `last_n_days` / `last_n_factors` | `tests.test_query.QueryHelpersTest.test_register_query_macros_last_n_days` |
| 股票查询 `--adjust` 模式 | `tests.test_query.QueryHelpersTest.test_build_stock_sql_supports_adjust_modes` |
| 核心指标与 KDJ 计算 | `tests.test_query.QueryHelpersTest.test_build_factors_generates_core_indicators_and_kdj` |
| ADX 边界收敛 | `tests.test_query.QueryHelpersTest.test_render_build_factors_sql_clamps_adx` |

Quick regression commands:

Daily:

```bash
./.venv/bin/python -m unittest tests.test_pipeline -q
./.venv/bin/python -m unittest tests.test_duckdb_ops -q
```

Pre-commit:

```bash
./.venv/bin/python -m unittest tests.test_query -q
./.venv/bin/python -m unittest discover -s tests -q
```

Targeted troubleshooting:

```bash
./.venv/bin/python -m unittest tests.test_pipeline.PipelineTest.test_actions_status_reports_cache_and_update_report -q
./.venv/bin/python -m unittest tests.test_pipeline.PipelineTest.test_update_actions_export_dry_run_reports_skipped_symbols -q
```

Recommended order:

1. `tests.test_pipeline` for update/build/cache flow.
2. `tests.test_duckdb_ops` for ASOF and factor join logic.
3. `tests.test_query` for SQL generation and factor checks.
4. Full `discover` run before you commit or push.

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
`raw_daily`, `corporate_actions`, `adjustment_factors`, `adj_daily`, `hfq_daily`,
and `factors`.

Show current version status:

```bash
tdx-stocks query status
```

Show table-level row counts, date ranges, and disk usage:

```bash
tdx-stocks query tables
```

Show schema:

```bash
tdx-stocks query schema raw_daily
tdx-stocks query schema factors
```

Show filtered rows:

```bash
tdx-stocks query table raw_daily --symbol 600000 --from-date 2024-01-01 --desc --limit 20
tdx-stocks query table factors --columns symbol,trade_date,pct_chg,ret_20,vol_20,rsi_14,adx_14 --limit 30
```

Show one stock's merged daily rows and factors:

```bash
tdx-stocks query price 600519.SH --limit 20
tdx-stocks query price 600519.SH --from-date 2024-01-01 --to-date 2024-12-31 --limit 50
tdx-stocks query price 600519.SH --no-limit
```

CLI output rounds numeric values to at most two decimals. `volume` and `amount`
are abbreviated with units like `K`, `M`, and `B` for readability.

Run ad hoc SQL:

```bash
tdx-stocks query sql "select symbol, count(*) as row_count, max(trade_date) as last_date from raw_daily group by symbol order by symbol"
```

The SQL session also registers convenience macros:

```bash
tdx-stocks query sql "select * from last_n_days('600519.SH', 10)"
tdx-stocks query sql "select * from last_n_factors('600519.SH', 10)"
```

Export a filtered result to CSV:

```bash
tdx-stocks query export factors --symbol 600000 --from-date 2024-01-01 --to ../Database/exports/factors_600000.csv --limit 1000
```

## Notes

- `raw_daily` stores unadjusted OHLCV parsed from TDX `.day` files.
- `corporate_actions` stores cached rights/dividend events when available.
- `adjustment_factors` stores cached qfq/hfq factors when available.
- `adj_daily` stores adjusted OHLCV in front-adjusted form.
- `hfq_daily` stores adjusted OHLCV in back-adjusted form.
- `factors` stores derived indicators based on adjusted close, including
  `ret_1`, `ret_5`, `ret_10`, `ret_20`, `ret_60`, `ret_120`, `ret_250`,
  `ma5`, `ma10`, `ma20`, `ma60`, `ma120`, `ma250`, `vol_5`, `vol_10`,
  `vol_20`, `vol_60`, `range_20`, `dd_20`, `dd_60`, `pos_20`, `pos_60`,
  `atr_14`, `atr_pct_14`, `bb_width_20`, `rsi_6`, `rsi_14`, `bias_5`,
  `bias_10`, `bias_20`, `bias_60`, `rsv_9`, `k_9`, `d_9`, `j_9`,
  `plus_di_14`, `minus_di_14`, `adx_14`, `amount_ma20`, `amount_ma60`,
  `vol_ratio_20`, `amp_1`, and MACD.
- `query price` shows a compact subset of the merged daily data and highlights core
  factor columns such as `ret_20`, `vol_20`, `rsi_14`, `atr_pct_14`, `adx_14`,
  and KDJ.
- `latest.json` is replaced only after all stages and checks complete.
