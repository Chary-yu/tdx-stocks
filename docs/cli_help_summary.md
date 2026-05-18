# tdx-stocks CLI 摘要

## 支持命令

| 命令 | 功能 |
| --- | --- |
| `data` | Data pipeline commands. |
| `audit` | Audit and diagnostics commands. |
| `query` | Read-only inspection and query commands. |
| `strategy` | Strategy analysis commands. |
| `factors` | Factor catalog and research commands. |
| `init-config` | Write a default TOML config. |
| `sync` | Synchronize export-derived data and rebuild. |
| `help-summary` | Generate a markdown summary of the CLI. |

## 兼容别名

| 命令 | 替代 |
| --- | --- |
| `build` | `data build` |
| `rebuild` | `data rebuild` |
| `update-actions` | `data update` |
| `actions-status` | `data status` |
| `verify-adjustment` | `audit verify` |
| `doctor` | `audit doctor` |
| `status` | `query status` |
| `tables` | `query tables` |
| `schema` | `query schema` |
| `head` | `query table` |
| `stock` | `query price` |
| `sql` | `query sql` |
| `export` | `query export` |

## 命令参数

### 子命令

| 命令 | 功能 |
| --- | --- |
| `data` | Data pipeline commands. |
| `audit` | Audit and diagnostics commands. |
| `query` | Read-only inspection and query commands. |
| `strategy` | Strategy analysis commands. |
| `factors` | Factor catalog and research commands. |
| `init-config` | Write a default TOML config. |
| `sync` | Synchronize export-derived data and rebuild. |
| `help-summary` | Generate a markdown summary of the CLI. |

#### `data`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `update` | Refresh cached corporate actions. |
| `status` | Show cached corporate actions and adjustment factor status. |
| `build` | Build a versioned local dataset. |
| `rebuild` | Clear the current database and rebuild from local TDX data. |
| `quality-report` | Write a data quality report for the latest dataset. |

##### `data update`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--source` | Update source label for the report. (default: local) |
| `--input` | Optional CSV file or directory containing corporate_actions.csv and adjustment_factors.csv. |
| `--dry-run` |  |
| `--json` |  |

##### `data status`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

##### `data build`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from-date` |  |
| `--to-date` |  |
| `--limit-symbols` |  |
| `--overwrite-staging` |  |

##### `data rebuild`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from-date` |  |
| `--to-date` |  |
| `--limit-symbols` |  |
| `--overwrite-staging` |  |

##### `data quality-report`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

#### `audit`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `doctor` | Check paths and dependency imports. |
| `verify` | Compare adj_daily against TDX export front-adjusted text. |

##### `audit doctor`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |

##### `audit verify`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `symbol` | Stock code such as 600519.SH or sh600519. |
| `--input` | Optional export file or directory override. |
| `--from-date` |  |
| `--to-date` |  |
| `--threshold` | (default: 0.01) |
| `--json` |  |

#### `query`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `status` | Show latest dataset status. |
| `price` | Show merged daily rows and factors for one stock code. |
| `table` | Show rows from a latest table. |
| `tables` | Show latest table summaries. |
| `schema` | Show a table schema. |
| `sql` | Run SQL against latest table views. |
| `export` | Export a filtered table query to CSV. |

##### `query status`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

##### `query price`

| 参数 | 说明 |
| --- | --- |
| `symbol` | Stock code such as 600519.SH or sh600519. |
| `--limit` | (default: 100) |
| `--adjust` | (default: qfq) |
| `--from-date` |  |
| `--to-date` |  |
| `--asc` | (default: True) |
| `--no-limit` |  |
| `--json` |  |

##### `query table`

| 参数 | 说明 |
| --- | --- |
| `table` |  |
| `--limit` | (default: 20) |
| `--columns` | Comma-separated output columns. |
| `--symbol` |  |
| `--market` |  |
| `--from-date` |  |
| `--to-date` |  |
| `--where` | Extra SQL WHERE expression. |
| `--order-by` |  |
| `--desc` |  |
| `--json` |  |

##### `query tables`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

##### `query schema`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `table` |  |
| `--json` |  |

##### `query sql`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `sql` |  |
| `--limit` | (default: 100) |
| `--json` |  |

##### `query export`

| 参数 | 说明 |
| --- | --- |
| `table` |  |
| `--limit` | (default: 1000) |
| `--columns` | Comma-separated output columns. |
| `--symbol` |  |
| `--market` |  |
| `--from-date` |  |
| `--to-date` |  |
| `--where` | Extra SQL WHERE expression. |
| `--order-by` |  |
| `--desc` |  |
| `--json` |  |
| `--to` |  |
| `--no-limit` |  |

#### `strategy`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `list` | List available strategy presets. |
| `run` | Run a strategy and emit a report. |
| `compare` | Compare strategy candidates. |
| `consensus` | Find strategy consensus candidates. |
| `backtest` | Backtest a strategy on historical dates. |
| `backtest-compare` | Compare backtests across strategies. |
| `tune` | Scan strategy parameter combinations. |
| `analyze-forward-returns` | Analyze forward returns after strategy hits. |
| `analyze-risk-tags` | Analyze forward returns by risk tags. |
| `backtest-consensus` | Backtest consensus hits across multiple strategies. |
| `reports` | Manage saved strategy reports. |

##### `strategy list`

| 参数 | 说明 |
| --- | --- |
| `--json` |  |

##### `strategy run`

| 参数 | 说明 |
| --- | --- |

##### 子命令

| 命令 | 功能 |
| --- | --- |
| `low-vol-breakout` | Generate a low-volatility breakout observation pool. |
| `ma-pullback` | Generate a moving-average pullback observation pool. |
| `relative-strength` | Generate a relative-strength observation pool. |
| `trend-strength` | Generate the short-term trend observation pool. |
| `volume-breakout` | Generate a volume breakout observation pool. |

###### `strategy run low-vol-breakout`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--limit` | (default: 20) |
| `--json` |  |
| `--save` |  |
| `--as-of` |  |
| `--market` |  |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--min-score` | (default: 60.0) |
| `--candidate-type` |  |
| `--include-excluded` |  |
| `--show-excluded-limit` | (default: 20) |
| `--explain-symbol` |  |
| `--to` |  |

###### `strategy run ma-pullback`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--limit` | (default: 20) |
| `--json` |  |
| `--save` |  |
| `--as-of` |  |
| `--market` |  |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--min-score` | (default: 60.0) |
| `--candidate-type` |  |
| `--include-excluded` |  |
| `--show-excluded-limit` | (default: 20) |
| `--explain-symbol` |  |
| `--to` |  |

###### `strategy run relative-strength`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--limit` | (default: 20) |
| `--json` |  |
| `--save` |  |
| `--as-of` |  |
| `--market` |  |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--min-score` | (default: 60.0) |
| `--candidate-type` |  |
| `--include-excluded` |  |
| `--show-excluded-limit` | (default: 20) |
| `--explain-symbol` |  |
| `--to` |  |

###### `strategy run trend-strength`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--limit` | (default: 20) |
| `--json` |  |
| `--save` |  |
| `--as-of` |  |
| `--market` |  |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--min-score` | (default: 60.0) |
| `--candidate-type` |  |
| `--include-excluded` |  |
| `--show-excluded-limit` | (default: 20) |
| `--explain-symbol` |  |
| `--to` |  |

###### `strategy run volume-breakout`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--limit` | (default: 20) |
| `--json` |  |
| `--save` |  |
| `--as-of` |  |
| `--market` |  |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--min-score` | (default: 60.0) |
| `--candidate-type` |  |
| `--include-excluded` |  |
| `--show-excluded-limit` | (default: 20) |
| `--explain-symbol` |  |
| `--to` |  |

##### `strategy compare`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--as-of` | (default: latest) |
| `--strategies` | Comma-separated strategy names. Defaults to all registered strategies. |
| `--format` | (default: table) |
| `--json` |  |
| `--to` |  |

##### `strategy consensus`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--as-of` | (default: latest) |
| `--strategies` | Comma-separated strategy names. Defaults to all registered strategies. |
| `--min-hit` | (default: 2) |
| `--format` | (default: table) |
| `--json` |  |
| `--to` |  |

##### `strategy backtest`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from` |  |
| `--to` |  |
| `--top` | (default: 20) |
| `--hold-days` | (default: 5) |
| `--fee-rate` |  |
| `--slippage` |  |
| `--market` |  |
| `--min-score` | (default: 60.0) |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--candidate-type` |  |
| `--format` | (default: table) |
| `--json` |  |
| `--output` |  |
| `strategy_name` |  |

##### `strategy backtest-compare`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--strategies` | Comma-separated strategy names. Defaults to all registered strategies. |
| `--from` |  |
| `--to` |  |
| `--top` | (default: 20) |
| `--hold-days` | (default: 5) |
| `--fee-rate` |  |
| `--slippage` |  |
| `--market` |  |
| `--min-score` | (default: 60.0) |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--candidate-type` |  |
| `--format` | (default: table) |
| `--json` |  |
| `--output` |  |

##### `strategy tune`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from` |  |
| `--to` |  |
| `--min-score` | (default: 55,60,65) |
| `--top` | (default: 10,20,30) |
| `--hold-days` | (default: 5,10,20) |
| `--fee-rate` |  |
| `--slippage` |  |
| `--market` |  |
| `--candidate-type` |  |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--format` | (default: table) |
| `--json` |  |
| `--output` |  |
| `strategy_name` |  |

##### `strategy analyze-forward-returns`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from` |  |
| `--to` |  |
| `--horizons` | (default: 1,5,10,20) |
| `--limit` | (default: 20) |
| `--market` |  |
| `--min-score` | (default: 60.0) |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--candidate-type` |  |
| `--format` | (default: table) |
| `--json` |  |
| `--output` |  |
| `strategy_name` |  |

##### `strategy analyze-risk-tags`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from` |  |
| `--to` |  |
| `--horizons` | (default: 5,10,20) |
| `--limit` | (default: 20) |
| `--market` |  |
| `--min-score` | (default: 60.0) |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--candidate-type` |  |
| `--format` | (default: table) |
| `--json` |  |
| `--output` |  |
| `strategy_name` |  |

##### `strategy backtest-consensus`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--strategies` | Comma-separated strategy names. Defaults to all registered strategies. |
| `--from` |  |
| `--to` |  |
| `--top` | (default: 20) |
| `--hold-days` | (default: 5) |
| `--min-hit` | (default: 2) |
| `--fee-rate` |  |
| `--slippage` |  |
| `--market` |  |
| `--min-score` | (default: 60.0) |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--candidate-type` |  |
| `--format` | (default: table) |
| `--json` |  |
| `--output` |  |

##### `strategy reports`

| 参数 | 说明 |
| --- | --- |

##### 子命令

| 命令 | 功能 |
| --- | --- |
| `list` | List saved strategy reports. |
| `show` | Show a saved strategy report. |

###### `strategy reports list`

| 参数 | 说明 |
| --- | --- |
| `--json` |  |

###### `strategy reports show`

| 参数 | 说明 |
| --- | --- |
| `strategy_name` |  |
| `--as-of` | (default: latest) |
| `--run-id` |  |
| `--json` |  |

#### `factors`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `list` | List available factors. |
| `describe` | Describe one factor. |
| `schema` | Show factor table schema. |
| `rank` | Rank one factor on a chosen date. |

##### `factors list`

| 参数 | 说明 |
| --- | --- |
| `--json` |  |

##### `factors describe`

| 参数 | 说明 |
| --- | --- |
| `factor` |  |
| `--json` |  |

##### `factors schema`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

##### `factors rank`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `factor` |  |
| `--as-of` | (default: latest) |
| `--limit` | (default: 50) |
| `--market` |  |
| `--json` |  |

#### `init-config`

| 参数 | 说明 |
| --- | --- |
| `--path` | (default: tdx_stocks.toml) |

#### `sync`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from-date` |  |
| `--to-date` |  |
| `--limit-symbols` |  |
| `--overwrite-staging` |  |
| `--dry-run` |  |
| `--json` |  |

#### `help-summary`

| 参数 | 说明 |
| --- | --- |
| `--output` | Output markdown path, or - for stdout. (default: docs/cli_help_summary.md) |
