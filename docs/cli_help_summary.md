# tdx-stocks CLI 摘要

## 支持命令

| 命令 | 功能 |
| --- | --- |
| `init-config` | Write a default TOML config. |
| `sync` | Synchronize export-derived data and rebuild. |
| `data` | Data pipeline commands. |
| `audit` | Audit and diagnostics commands. |
| `query` | Read-only inspection and query commands. |
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
| `init-config` | Write a default TOML config. |
| `sync` | Synchronize export-derived data and rebuild. |
| `data` | Data pipeline commands. |
| `audit` | Audit and diagnostics commands. |
| `query` | Read-only inspection and query commands. |
| `help-summary` | Generate a markdown summary of the CLI. |

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

#### `help-summary`

| 参数 | 说明 |
| --- | --- |
| `--output` | Output markdown path, or - for stdout. (default: docs/cli_help_summary.md) |
