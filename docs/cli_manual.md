# tdx-stocks 命令行手册

> 维护目标：覆盖当前稳定 CLI 表面。  
> 当前顶层命令：`init`、`doctor`、`sync`、`run`、`report`、`query`、`status`、`ui`、`help`。

## 1. 概览

`tdx-stocks` 是本地 TDX `.day` 数据到版本化 Parquet 数据集的命令行工具。

典型流程：

```text
init -> sync -> run daily -> report -> status -> ui
```

`help` 提供静态主题帮助。  
`query` 提供只读查询和因子浏览。  
`run` 支持内置预设：

```text
daily, signal, portfolio, rebalance, backtest, grid
```

## 2. 常用命令

### `init`

初始化当前目录的研究工作区。

```bash
tdx-stocks init --data-root ./Database
tdx-stocks init --profile portfolio --data-root ./Database
```

### `doctor`

检查路径、配置和依赖。

```bash
tdx-stocks doctor --config tdx_stocks.toml
```

### `sync`

同步本地导出源并重建最新数据。

```bash
tdx-stocks sync --config tdx_stocks.toml
tdx-stocks sync --config tdx_stocks.toml --dry-run
```

### `run`

运行内置预设或自定义 TOML 配置。

```bash
tdx-stocks run daily --explain
tdx-stocks run backtest
tdx-stocks run experiments/backtest.toml
```

### `report`

输出最新日报。

```bash
tdx-stocks report --config tdx_stocks.toml
tdx-stocks report --format json
```

### `status`

查看工作区、最新数据集和报告状态。

```bash
tdx-stocks status
tdx-stocks status --json
```

### `ui`

启动只读 Web UI。

```bash
tdx-stocks ui --config tdx_stocks.toml
```

### `help`

输出静态帮助主题。

```bash
tdx-stocks help
tdx-stocks help query
tdx-stocks help run
```

## 3. 查询命令

### `query stock`

查看单只股票的合并行情。

```bash
tdx-stocks query stock 600519.SH --limit 20
tdx-stocks query stock 600519.SH --no-limit
```

### `query table`

查看指定表的筛选结果。

```bash
tdx-stocks query table raw_daily --symbol 600000 --limit 20
```

### `query tables`

查看最新表摘要。

```bash
tdx-stocks query tables
```

### `query schema`

查看表结构。

```bash
tdx-stocks query schema raw_daily
```

### `query sql`

执行只读 SQL。

```bash
tdx-stocks query sql --unsafe-sql "select * from last_n_days('600519.SH', 10)"
```

### `query export`

导出筛选结果到 CSV。

```bash
tdx-stocks query export factors --symbol 600000 --to ../Database/exports/factors_600000.csv
```

### `query factor list`

查看因子目录。

```bash
tdx-stocks query factor list
```

### `query factor describe`

查看单个因子定义。

```bash
tdx-stocks query factor describe rs_score
```

### `query factor schema`

查看因子相关表的字段。

```bash
tdx-stocks query factor schema
```

### `query factor rank`

按指定日期做横截面排名。

```bash
tdx-stocks query factor rank rs_score --as-of latest --limit 20
```

## 4. 说明

- `sync` 是推荐的一键入口。
- 旧入口不再作为顶层 CLI 命令提供，`query stock` 与 `query factor ...` 是新的查询入口。
- `run` 可以直接使用预设名，不必手写 `.toml` 路径。
