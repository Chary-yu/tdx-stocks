# tdx-stocks

Local TDX daily data pipeline:

```text
.day -> raw_daily -> checks -> adj_daily / hfq_daily -> checks -> factors -> checks -> atomic latest
```

`update-actions` refreshes the cached `corporate_actions` and `adjustment_factors`
tables. `build` and `rebuild` only consume those local caches and do not fetch
new rights/dividend data automatically.

## Paths

Default local paths for this workspace:

```text
TDX vipdoc: /mnt/d/ProgramFiles/Tdx/vipdoc
TDX export: /mnt/d/ProgramFiles/Tdx/T0002/export
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

CLI 手册见 `docs/cli_manual.md`，摘要版可用 `tdx-stocks help-summary` 或 `tools/generate_cli_help_summary.py` 生成到 `docs/cli_help_summary.md`。

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

Clear `Database/` and rebuild from local TDX data:

```bash
tdx-stocks rebuild --config tdx_stocks.toml --overwrite-staging
```

Refresh cached rights/dividend data separately:

```bash
tdx-stocks update-actions --config tdx_stocks.toml --source file --input action_inputs/
tdx-stocks update-actions --config tdx_stocks.toml --source export
tdx-stocks update-actions --config tdx_stocks.toml --source export --dry-run
tdx-stocks actions-status --config tdx_stocks.toml
```

Use `actions-status --json` when you want to inspect the current cache and the
latest update report from tooling or `jq`.

`build` and `rebuild` print stage progress to stderr while they run.
Internally the factor build now runs in staged DuckDB temp tables so the heavy
rolling-window and recursive calculations stay easier to debug and less memory
hungry than one giant query.

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
tdx-stocks head factors --columns symbol,trade_date,pct_chg,ret_20,vol_20,rsi_14,adx_14 --limit 30
```

Show one stock's merged daily rows and factors:

```bash
tdx-stocks stock 600519.SH --limit 20
tdx-stocks stock 600519.SH --from-date 2024-01-01 --to-date 2024-12-31 --limit 50
tdx-stocks stock 600519.SH --no-limit
```

CLI output rounds numeric values to at most two decimals. `volume` and `amount`
are abbreviated with units like `K`, `M`, and `B` for readability.

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
- `stock` shows a compact subset of the merged daily data and highlights core
  factor columns such as `ret_20`, `vol_20`, `rsi_14`, `atr_pct_14`, `adx_14`,
  and KDJ.
- `latest.json` is replaced only after all stages and checks complete.
