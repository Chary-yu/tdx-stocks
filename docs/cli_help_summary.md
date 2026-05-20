# tdx-stocks CLI 摘要

TDX Stocks - local stock research workflow

## 支持命令

| 命令 | 功能 |
| --- | --- |
| `doctor` | Diagnose setup issues. |
| `help` | Show built-in guidance topics. |
| `init` | Initialize a new research workspace. |
| `query` | Read-only inspection and query commands. |
| `report` | Show the latest daily report. |
| `run` | Run a preset name or TOML experiment config. |
| `status` | Show project status. |
| `sync` | Synchronize local caches and the latest dataset. |
| `ui` | Launch the read-only Web UI. |

## 命令参数

### 子命令

| 命令 | 功能 |
| --- | --- |
| `init` | Initialize a new research workspace. |
| `doctor` | Diagnose setup issues. |
| `sync` | Synchronize local caches and the latest dataset. |
| `run` | Run a preset name or TOML experiment config. |
| `report` | Show the latest daily report. |
| `query` | Read-only inspection and query commands. |
| `status` | Show project status. |
| `ui` | Launch the read-only Web UI. |
| `help` | Show built-in guidance topics. |

#### `init`

| 参数 | 说明 |
| --- | --- |
| `--force` |  |
| `--minimal` |  |
| `--profile` | (default: simple) |
| `--data-root` | (default: Database) |

#### `doctor`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |

#### `sync`

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

#### `run`

| 参数 | 说明 |
| --- | --- |
| `config` | Preset name or path to a TOML experiment config. |
| `--dry-run` |  |
| `--explain` |  |
| `--json` |  |
| `--output` |  |

#### `report`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--as-of` | (default: latest) |
| `--format` | (default: markdown) |
| `--output` |  |

#### `query`

| 参数 | 说明 |
| --- | --- |

#### 子命令

| 命令 | 功能 |
| --- | --- |
| `stock` | Show merged daily rows and factors for one stock code. |
| `table` | Show rows from a latest table. |
| `tables` | Show latest table summaries. |
| `schema` | Show a table schema. |
| `sql` | Run SQL against latest table views. |
| `export` | Export a filtered table query to CSV. |
| `factor` | Factor catalog, schema inspection, and ranking commands. |

##### `query stock`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
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
| `--config` |  |
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
| `--unsafe-sql` | Allow arbitrary SQL. Disabled by default because DuckDB can expose file and function access. |
| `--json` |  |

##### `query export`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
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

##### `query factor`

| 参数 | 说明 |
| --- | --- |

##### 子命令

| 命令 | 功能 |
| --- | --- |
| `list` | List available factors. |
| `describe` | Describe one factor. |
| `schema` | Show factor table schema. |
| `rank` | Rank one factor on a chosen date. |

###### `query factor list`

| 参数 | 说明 |
| --- | --- |
| `--json` |  |

###### `query factor describe`

| 参数 | 说明 |
| --- | --- |
| `factor` |  |
| `--json` |  |

###### `query factor schema`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

###### `query factor rank`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `factor` |  |
| `--as-of` | (default: latest) |
| `--limit` | (default: 50) |
| `--market` |  |
| `--json` |  |

#### `status`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

#### `ui`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--host` | (default: 127.0.0.1) |
| `--port` | (default: 8501) |
| `--no-browser` |  |

#### `help`

| 参数 | 说明 |
| --- | --- |
| `topic` |  |
