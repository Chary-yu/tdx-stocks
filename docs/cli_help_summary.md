# tdx-stocks CLI 摘要

## 支持命令

| 命令 | 功能 |
| --- | --- |
| `init-config` | Write a default TOML config. |
| `doctor` | Check paths and dependency imports. |
| `build` | Build a versioned local dataset. |
| `rebuild` | Clear the current database and rebuild from local TDX data. |
| `update-actions` | Refresh cached corporate actions or adjustment factors. |
| `status` | Show latest dataset status. |
| `tables` | Show latest table summaries. |
| `schema` | Show a table schema. |
| `head` | Show rows from a latest table. |
| `stock` | Show merged daily rows and factors for one stock code. |
| `sql` | Run SQL against latest table views. |
| `export` | Export a filtered table query to CSV. |
| `help-summary` | Generate a markdown summary of the CLI. |

## 命令参数

### `init-config`

| 参数 | 说明 |
| --- | --- |
| `--path` | (default: tdx_stocks.toml) |

### `doctor`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |

### `build`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from-date` |  |
| `--to-date` |  |
| `--limit-symbols` |  |
| `--overwrite-staging` |  |

### `rebuild`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--from-date` |  |
| `--to-date` |  |
| `--limit-symbols` |  |
| `--overwrite-staging` |  |

### `update-actions`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--source` | Update source label for the report. (default: local) |
| `--input` | Optional CSV file or directory containing corporate_actions.csv and adjustment_factors.csv. |

### `status`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |

### `tables`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |

### `schema`

| 参数 | 说明 |
| --- | --- |
| `table` |  |
| `--config` |  |

### `head`

| 参数 | 说明 |
| --- | --- |
| `table` |  |
| `--config` |  |
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

### `stock`

| 参数 | 说明 |
| --- | --- |
| `symbol` | Stock code such as 600519.SH or sh600519. |
| `--config` |  |
| `--limit` | (default: 100) |
| `--adjust` | (default: qfq) |
| `--from-date` |  |
| `--to-date` |  |
| `--asc` | (default: True) |
| `--no-limit` |  |
| `--json` |  |

### `sql`

| 参数 | 说明 |
| --- | --- |
| `sql` |  |
| `--config` |  |
| `--limit` | (default: 100) |
| `--json` |  |

### `export`

| 参数 | 说明 |
| --- | --- |
| `table` |  |
| `--config` |  |
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

### `help-summary`

| 参数 | 说明 |
| --- | --- |
| `--output` | Output markdown path, or - for stdout. (default: docs/cli_help_summary.md) |
