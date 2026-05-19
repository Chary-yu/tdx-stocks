# tdx-stocks CLI 摘要

TDX Stocks - local stock research workflow

## 支持命令

| 命令 | 功能 |
| --- | --- |
| `data` | Data pipeline commands. |
| `init` | Initialize a new research workspace. |
| `run` | Run a TOML experiment config. |
| `ui` | Launch the read-only Web UI. |
| `help-summary` | Generate a markdown summary of the CLI. |

## Advanced commands

| 命令 | 功能 |
| --- | --- |
| `audit` | Audit and diagnostics commands. |
| `query` | Read-only inspection and query commands. |
| `strategy` | Strategy analysis commands. |
| `portfolio` | Portfolio construction and risk commands. |
| `daily` | Daily orchestration commands. |
| `factors` | Factor catalog and research commands. |

## 兼容别名

| 命令 | 替代 |
| --- | --- |
| `init-config` | `init` |
| `sync` | `data sync` |

## 命令参数

### 子命令

| 命令 | 功能 |
| --- | --- |
| `data` | Data pipeline commands. |
| `init` | Initialize a new research workspace. |
| `audit` | Audit and diagnostics commands. |
| `query` | Read-only inspection and query commands. |
| `strategy` | Strategy analysis commands. |
| `portfolio` | Portfolio construction and risk commands. |
| `daily` | Daily orchestration commands. |
| `factors` | Factor catalog and research commands. |
| `run` | Run a TOML experiment config. |
| `ui` | Launch the read-only Web UI. |
| `help-summary` | Generate a markdown summary of the CLI. |

#### `data`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `sync` | Synchronize data and rebuild the latest dataset. |
| `update` | Refresh cached corporate actions. |
| `status` | Show cached corporate actions and adjustment factor status. |
| `build` | Build a versioned local dataset. |
| `rebuild` | Clear the current database and rebuild from local TDX data. |
| `quality-report` | Write a data quality report for the latest dataset. |

##### `data sync`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--full` |  |
| `--from-date` |  |
| `--to-date` |  |
| `--limit-symbols` |  |
| `--overwrite-staging` |  |
| `--dry-run` |  |
| `--json` |  |

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

#### `init`

| 参数 | 说明 |
| --- | --- |
| `--force` |  |
| `--profile` | (default: simple) |
| `--data-root` | (default: Database) |

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
| `--output, --to` |  |
| `--no-limit` |  |

#### `strategy`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `list` | List available strategy presets. |
| `groups` | Show strategy distribution by group. |
| `describe` | Describe a strategy preset. |
| `explain` | Explain why a symbol matches a strategy. |
| `run` | Run a strategy and emit a report. |
| `compare` | Compare strategy candidates. |
| `consensus` | Find strategy consensus candidates. |
| `backtest` | Run a rolling T+1 signal backtest on historical dates. |
| `backtest-compare` | Compare backtests across strategies. |
| `tune` | Scan strategy parameter combinations. |
| `analyze-forward-returns` | Analyze forward returns after strategy hits. |
| `analyze-risk-tags` | Analyze forward returns by risk tags. |
| `backtest-consensus` | Backtest consensus hits across multiple strategies. |
| `batch` | Run TOML-driven backtest experiments. |
| `reports` | Manage saved strategy reports. |

##### `strategy list`

| 参数 | 说明 |
| --- | --- |
| `--json` |  |

##### `strategy groups`

| 参数 | 说明 |
| --- | --- |
| `--json` |  |

##### `strategy describe`

| 参数 | 说明 |
| --- | --- |
| `strategy` |  |
| `--json` |  |

##### `strategy explain`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `strategy` |  |
| `symbol` |  |
| `--as-of` | (default: latest) |
| `--json` |  |
| `--output, --to` |  |
| `--market` |  |
| `--limit` | (default: 20) |
| `--min-score` | (default: 60.0) |
| `--min-amount-ma20` | (default: 50000000.0) |
| `--candidate-type` |  |
| `--include-excluded` |  |
| `--show-excluded-limit` | (default: 20) |

##### `strategy run`

| 参数 | 说明 |
| --- | --- |

##### 子命令

| 命令 | 功能 |
| --- | --- |
| `low-vol-breakout` | Generate a low-volatility breakout observation pool. |
| `ma-pullback` | Generate a moving-average pullback observation pool. |
| `mean-reversion` | Generate an oversold rebound observation pool. |
| `multi-factor` | Generate a configurable multi-factor observation pool. |
| `pairs-arb` | Generate a pairs-trading long/short signal set. |
| `relative-strength` | Generate a relative-strength observation pool. |
| `smart-money` | Generate a smart-money observation pool. |
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
| `--output, --to` |  |

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
| `--output, --to` |  |

###### `strategy run mean-reversion`

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
| `--output, --to` |  |
| `--rsi-threshold` | (default: 25.0) |

###### `strategy run multi-factor`

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
| `--output, --to` |  |
| `--weight-mom` | (default: 0.4) |
| `--weight-vol` | (default: -0.3) |
| `--weight-liq` | (default: 0.3) |
| `--weight-rs` | (default: 0.2) |
| `--weight-trend` | (default: 0.1) |

###### `strategy run pairs-arb`

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
| `--output, --to` |  |
| `--symbols` | Comma-separated pair pool symbols. |
| `--lookback` | (default: 20) |
| `--zscore-threshold` | (default: 2.0) |
| `--max-pairs` | (default: 10) |

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
| `--output, --to` |  |

###### `strategy run smart-money`

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
| `--output, --to` |  |

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
| `--output, --to` |  |

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
| `--output, --to` |  |

##### `strategy compare`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--as-of` | (default: latest) |
| `--strategies` | Comma-separated strategy names. Defaults to all registered strategies. |
| `--format` | (default: table) |
| `--json` |  |
| `--output, --to` |  |

##### `strategy consensus`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--as-of` | (default: latest) |
| `--strategies` | Comma-separated strategy names. Defaults to all registered strategies. |
| `--min-hit` | (default: 2) |
| `--format` | (default: table) |
| `--json` |  |
| `--output, --to` |  |

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
| `--walk-forward` |  |
| `--train-years` | (default: 3) |
| `--test-years` | (default: 1) |
| `--monte-carlo` |  |
| `--iterations` | (default: 1000) |
| `--seed` |  |
| `--stress-test` |  |
| `--stress-period` | (default: all) |
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

##### `strategy batch`

| 参数 | 说明 |
| --- | --- |
| `-c, --config` | Path to the TOML config file. |
| `--batch` | Expand [batch_search] into a grid search. |

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
| `--config` |  |
| `--json` |  |

###### `strategy reports show`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `strategy_name` |  |
| `--as-of` | (default: latest) |
| `--run-id` |  |
| `--json` |  |

#### `portfolio`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `build` | Build a target portfolio. |
| `risk` | Inspect a saved portfolio report. |
| `rebalance-plan` | Create a rebalance plan. |
| `backtest` | Backtest a portfolio strategy. |
| `report` | Manage saved portfolio reports. |

##### `portfolio build`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from` | (default: consensus) |
| `--strategy` |  |
| `--top` | (default: 20) |
| `--weighting` | (default: equal) |
| `--max-weight` | (default: 0.1) |
| `--min-weight` |  |
| `--max-risk-score` |  |
| `--exclude-risk-tags` |  |
| `--market` |  |
| `--as-of` | (default: latest) |
| `--json` |  |
| `--output, --to` |  |
| `--save` |  |

##### `portfolio risk`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--portfolio` | (default: latest) |
| `--path` |  |
| `--json` |  |

##### `portfolio rebalance-plan`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from` | (default: consensus) |
| `--strategy` |  |
| `--top` | (default: 20) |
| `--weighting` | (default: equal) |
| `--max-weight` | (default: 0.1) |
| `--min-weight` |  |
| `--max-risk-score` |  |
| `--exclude-risk-tags` |  |
| `--market` |  |
| `--as-of` | (default: latest) |
| `--json` |  |
| `--output, --to` |  |
| `--save` |  |
| `--current` |  |
| `--min-trade-weight` |  |
| `--max-turnover` |  |

##### `portfolio backtest`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from` | (default: consensus) |
| `--strategy` |  |
| `--top` | (default: 20) |
| `--weighting` | (default: equal) |
| `--max-weight` | (default: 0.1) |
| `--min-weight` |  |
| `--max-risk-score` |  |
| `--exclude-risk-tags` |  |
| `--market` |  |
| `--as-of` | (default: latest) |
| `--json` |  |
| `--output, --to` |  |
| `--save` |  |
| `--from-date` |  |
| `--to-date` |  |
| `--rebalance-days` | (default: 5) |
| `--fee-bps` |  |
| `--slippage-bps` |  |

##### `portfolio report`

| 参数 | 说明 |
| --- | --- |

##### 子命令

| 命令 | 功能 |
| --- | --- |
| `list` | List saved portfolio reports. |
| `latest` | Show the latest portfolio report. |
| `show` | Show a saved portfolio report by path. |

###### `portfolio report list`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

###### `portfolio report latest`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

###### `portfolio report show`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `path` |  |
| `--json` |  |

#### `daily`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `run` | Run the daily research workflow. |
| `status` | Show the latest daily status. |
| `report` | Show a saved daily report. |

##### `daily run`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--as-of` | (default: latest) |
| `--json` |  |
| `--output, --to` |  |
| `--strategies` |  |
| `--strategy-limit` |  |
| `--min-score` |  |
| `--min-hit` |  |
| `--portfolio-top` |  |
| `--portfolio-weighting` |  |
| `--current-holdings` |  |
| `--skip-strategies` |  |
| `--skip-portfolio` |  |
| `--skip-rebalance` |  |
| `--skip-report` |  |
| `--build` |  |

##### `daily status`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

##### `daily report`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--as-of` | (default: latest) |
| `--format` | (default: markdown) |
| `--output` |  |

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

#### `run`

| 参数 | 说明 |
| --- | --- |
| `config` |  |
| `--dry-run` |  |
| `--json` |  |
| `--output` |  |
| `--set` | (default: []) |

#### `ui`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--host` | (default: 127.0.0.1) |
| `--port` | (default: 8501) |
| `--no-browser` |  |

#### `help-summary`

| 参数 | 说明 |
| --- | --- |
| `--output` | Output markdown path, or - for stdout. (default: docs/cli_help_summary.md) |
