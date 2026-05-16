# tdx-stocks 命令行手册

> 维护目标：覆盖当前系统所有可用命令、参数、默认值和典型用法。  
> 适用仓库：`code/`。

## 1. 作用范围

`tdx-stocks` 是本地 TDX `.day` 数据到版本化 Parquet 数据集的命令行工具。

核心流程：

```text
.day -> raw_daily -> checks -> adj_daily / hfq_daily -> checks -> factors -> checks -> latest.json
```

当前版本特性：

- `update-actions` 用来刷新 `corporate_actions` 和 `adjustment_factors` 缓存。
- `corporate_actions` 和 `adjustment_factors` 都可以来自本地缓存或外部输入文件。
- `update-actions --source export` 可以直接读取 `T0002/export` 的前复权文本，反推 `adjustment_factors`。
- `update-actions --dry-run` 只生成更新报告，不写入缓存。
- `actions-status` 用来查看缓存状态、覆盖区间和最近一次更新报告。
- `adj_daily` 默认是前复权行情，`hfq_daily` 默认是后复权行情；缓存不存在时会退回为 `adj_factor = 1.0` 的保守模式。
- `factors` 已包含动量、波动率、回撤、布林带、RSI、KDJ、ADX、量价等派生指标。
- `build` 和 `rebuild` 的 factors 阶段会在 DuckDB 内部分阶段物化为临时表，再合并导出，便于调试和降低单次查询压力。
- `build` 和 `rebuild` 会把阶段进度打印到 `stderr`。

## 2. 快速开始

```bash
cd /mnt/d/Zcyu/Chary-codex/tdx-stocks/code
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
tdx-stocks init-config --path tdx_stocks.toml
tdx-stocks doctor --config tdx_stocks.toml
tdx-stocks build --config tdx_stocks.toml --overwrite-staging
```

## 3. 配置文件

默认配置命令：

```bash
tdx-stocks init-config --path tdx_stocks.toml
```

常见配置项：

- `paths.tdx_vipdoc`：通达信 `vipdoc` 根目录
- `paths.tdx_export`：通达信 `T0002/export` 根目录
- `paths.data_root`：本地数据根目录
- `build.markets`：默认 `["sh", "sz"]`
- `build.universe`：默认 `ashare`
- `build.compression`：默认 `zstd`
- `build.batch_rows`：Parquet 写入批次
- `build.duckdb_memory_limit`：DuckDB 内存上限
- `build.overwrite_staging`：是否允许覆盖已有 staging

## 4. 构建类命令

### `build`

构建版本化本地数据集。

```bash
tdx-stocks build --config tdx_stocks.toml --overwrite-staging
```

常用参数：

- `--config <path>`：配置文件路径
- `--from-date YYYY-MM-DD`：只解析起始日期之后的数据
- `--to-date YYYY-MM-DD`：只解析截止日期之前的数据
- `--limit-symbols N`：仅处理前 `N` 个文件/股票样本，适合 smoke test
- `--overwrite-staging`：若 staging 已存在则覆盖

输出：

- 标准输出：build report JSON
- 标准错误：阶段进度信息

### `rebuild`

清空当前 `Database/`，然后重新解析本地数据并重建。

```bash
tdx-stocks rebuild --config tdx_stocks.toml --overwrite-staging
```

### `update-actions`

刷新缓存中的权息数据或复权因子，不会自动进入 `build`。

```bash
tdx-stocks update-actions --config tdx_stocks.toml --source local --input action_inputs/
tdx-stocks update-actions --config tdx_stocks.toml --source file --input corporate_actions.csv
tdx-stocks update-actions --config tdx_stocks.toml --source export
tdx-stocks update-actions --config tdx_stocks.toml --source export --dry-run
tdx-stocks actions-status --config tdx_stocks.toml
```

常用参数：

- `--source`：`local` / `official` / `file` / `export`
- `--input`：可选输入文件或目录
- `--dry-run`：只生成报告，不写缓存

参数与 `build` 相同。

### `doctor`

检查 TDX 路径和依赖。

```bash
tdx-stocks doctor --config tdx_stocks.toml
```

输出：

- `tdx_vipdoc` / `data_root`
- `tdx_export`
- 目录是否存在
- 检测到的 `.day` 文件数与样本
- `duckdb`、`pyarrow` 版本

### `actions-status`

查看缓存里的 `corporate_actions`、`adjustment_factors`，以及最近一次 `update-actions` 报告。

```bash
tdx-stocks actions-status
tdx-stocks actions-status --json
```

输出：

- `corporate_actions` / `adjustment_factors` 是否存在
- parquet 文件数、行数、覆盖股票数、日期范围
- `action_update_report.json` 的最近一次更新摘要

## 5. 查询类命令

所有查询类命令都会读取 `Database/latest.json`，并注册：

- `raw_daily`
- `corporate_actions`
- `adjustment_factors`
- `adj_daily`
- `hfq_daily`
- `factors`

### `status`

查看最新版本状态。

```bash
tdx-stocks status
```

显示：

- `run_id`
- `generated_at`
- `version_dir`
- `data_root`
- `disk_usage`
- 各项检查结果

### `tables`

查看最新表摘要。

```bash
tdx-stocks tables
```

### `schema`

查看某张表的字段定义。

```bash
tdx-stocks schema raw_daily
tdx-stocks schema factors
```

### `head`

查看筛选后的表数据。

```bash
tdx-stocks head raw_daily --symbol 600000 --from-date 2024-01-01 --desc --limit 20
tdx-stocks head factors --columns symbol,trade_date,pct_chg,ret_20,vol_20,rsi_14,adx_14 --limit 30
```

常用参数：

- `table`：`raw_daily` / `adj_daily` / `factors` / `corporate_actions`
- `--columns`：逗号分隔的字段列表
- `--symbol`：股票代码
- `--market`：`sh` / `sz` / `bj`
- `--from-date` / `--to-date`
- `--where`：补充 SQL `WHERE` 表达式
- `--order-by`
- `--desc`
- `--limit`
- `--json`

### `stock`

按股票代码查看一只股票的合并日线信息，包括 `raw_daily`、`adj_daily`、`hfq_daily` 和 `factors`。默认会展示一组精简因子列，例如 `ret_20`、`vol_20`、`rsi_14`、`atr_pct_14`、`adx_14` 以及 `k_9`、`d_9`、`j_9`。

```bash
tdx-stocks stock 600519.SH --limit 20
tdx-stocks stock 600519.SH --from-date 2024-01-01 --to-date 2024-12-31 --limit 50
tdx-stocks stock 600519.SH --no-limit
```

参数：

- `symbol`：支持 `600519.SH` / `sh600519`
- `--limit`：默认 100
- `--no-limit`：输出全量历史
- `--from-date` / `--to-date`
- `--asc`：正序输出，默认是倒序
- `--json`

### `sql`

执行自定义 DuckDB SQL。

```bash
tdx-stocks sql "select symbol, count(*) as row_count, max(trade_date) as last_date from raw_daily group by symbol order by symbol"
tdx-stocks sql "select * from last_n_days('600519.SH', 10)"
tdx-stocks sql "select * from last_n_factors('600519.SH', 10)"
```

参数：

- `sql`：SQL 文本
- `--limit N`：如果 SQL 看起来是 `SELECT` / `WITH` 且没有写 `LIMIT`，自动追加
- `--json`

### `export`

导出筛选后的查询结果到 CSV。

```bash
tdx-stocks export factors --symbol 600000 --from-date 2024-01-01 --to ../Database/exports/factors_600000.csv --limit 1000
```

参数与 `head` 相同，另加：

- `--to <path>`：CSV 输出路径
- `--no-limit`

### `help-summary`

生成 CLI 的摘要版 Markdown 手册。

```bash
tdx-stocks help-summary --output docs/cli_help_summary.md
tdx-stocks help-summary --output -
```

参数：

- `--output`：输出路径，`-` 表示直接打印到标准输出

默认输出：

- `docs/cli_help_summary.md`

## 6. 输出规则

- 命令行表格输出的数值默认最多两位小数。
- `volume`、`amount`、`vol_ma*`、`amount_ma*` 会缩写成 `K` / `M` / `B` / `T`。
- `--json` 输出也会做相同的数值归一化。

## 7. 便捷 SQL 宏

查询会自动注册 DuckDB 宏：

- `last_n_days(symbol, n)`
- `last_n_factors(symbol, n)`
- `tdx_symbol_code(symbol)`
- `tdx_symbol_market(symbol)`

示例：

```bash
tdx-stocks sql "select * from last_n_days('600519.SH', 10)"
```

## 8. 运行建议

- 先执行 `doctor`，确认路径和依赖正确。
- 初次全量构建建议先用 `--limit-symbols 20` 做 smoke test。
- `build` / `rebuild` 出现 `error > 0` 时，`latest.json` 不会更新。
- `rebuild` 会先删除整个 `Database/`，请谨慎使用。

## 9. 维护规则

- 命令、参数或默认值变化时，先更新 `src/tdx_stocks/cli.py`，再同步本手册。
- 新增命令后，需要补一条使用示例和参数说明。
- 如果查询层新增宏，也要在本手册第 7 节补充。
- `tools/generate_cli_help_summary.py` 会从 `src/tdx_stocks/cli.py` 自动生成摘要版手册。
