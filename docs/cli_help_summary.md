# tdx-stocks CLI 摘要

TDX Stocks - local stock research workflow

## 支持命令

| 命令 | 功能 |
| --- | --- |
| `data` | Data pipeline commands. |
| `doctor` | Diagnose setup issues. |
| `examples` | Show common command examples. |
| `init` | Initialize a new research workspace. |
| `report` | Show the latest daily report. |
| `run` | Run a TOML experiment config. |
| `status` | Show project status. |
| `ui` | Launch the read-only Web UI. |

## Advanced commands

| 命令 | 功能 |
| --- | --- |
| `audit` | Commands for environment checks and adjustment verification. |
| `daily` |  |
| `factors` | Commands for factor catalog, schema inspection, and cross-sectional ranking. |
| `help-summary` |  |
| `portfolio` |  |
| `query` | Commands that inspect the latest versioned dataset. |
| `strategy` | Commands that generate read-only observation pools from the latest dataset. |
| `sync` |  |

## 兼容别名

| 命令 | 替代 |
| --- | --- |
| `init-config` | `init` |

## 命令参数

### 子命令

| 命令 | 功能 |
| --- | --- |
| `data` | Data pipeline commands. |
| `init` | Initialize a new research workspace. |
| `run` | Run a TOML experiment config. |
| `ui` | Launch the read-only Web UI. |
| `examples` | Show common command examples. |
| `doctor` | Diagnose setup issues. |
| `status` | Show project status. |
| `report` | Show the latest daily report. |

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
| `--minimal` |  |
| `--profile` | (default: simple) |
| `--data-root` | (default: Database) |

#### `run`

| 参数 | 说明 |
| --- | --- |
| `config` |  |
| `--dry-run` |  |
| `--explain` |  |
| `--json` |  |
| `--output` |  |

#### `ui`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--host` | (default: 127.0.0.1) |
| `--port` | (default: 8501) |
| `--no-browser` |  |

#### `examples`

| 参数 | 说明 |
| --- | --- |
| `topic` |  |

#### `doctor`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |

#### `status`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--json` |  |

#### `report`

| 参数 | 说明 |
| --- | --- |
| `--config` |  |
| `--as-of` | (default: latest) |
| `--format` | (default: markdown) |
| `--output` |  |
