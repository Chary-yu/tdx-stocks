from __future__ import annotations

import argparse
from pathlib import Path

from ..config import DEFAULT_DATA_ROOT, write_default_config


def register_init_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("init", help="Initialize a new research workspace.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--profile", choices=("simple", "research", "portfolio"), default="simple")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.set_defaults(func=cmd_init)


def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    files = _build_files(root, data_root=args.data_root, profile=args.profile)
    for rel_path, content in files.items():
        path = root / rel_path
        if path.exists() and not args.force:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (root / "reports").mkdir(parents=True, exist_ok=True)
    print("Project initialized.")
    print("")
    print("Next steps:")
    print("  1. Edit tdx_stocks.toml")
    print("  2. Run: tdx-stocks data sync")
    print("  3. Run: tdx-stocks run experiments/daily.toml")
    return 0


def _build_files(root: Path, *, data_root: Path, profile: str) -> dict[str, str]:
    config = _config_template(data_root=data_root)
    daily = _daily_template()
    signal = _signal_template()
    if profile == "simple":
        config = config.replace(
            'enabled_strategies = ["trend-strength", "relative-strength", "low-vol-breakout", "volume-breakout"]',
            'enabled_strategies = ["trend-strength", "relative-strength"]',
        )
        daily = daily.replace(
            'enabled = ["trend-strength", "relative-strength", "low-vol-breakout", "volume-breakout"]',
            'enabled = ["trend-strength", "relative-strength"]',
        )
        signal = signal.replace(
            'enabled = ["trend-strength", "relative-strength", "low-vol-breakout"]',
            'enabled = ["trend-strength", "relative-strength"]',
        )
    elif profile == "portfolio":
        config = config.replace('portfolio_top = 20', 'portfolio_top = 50')
    return {
        "tdx_stocks.toml": config,
        "experiments/daily.toml": daily,
        "experiments/signal.toml": signal,
        "experiments/backtest.toml": _backtest_template(),
        "experiments/grid_search.toml": _grid_search_template(),
        "experiments/portfolio.toml": _portfolio_template(),
        "experiments/rebalance.toml": _rebalance_template(),
        "reports/.gitkeep": "",
        "holdings.csv.example": "market,symbol,weight\nsh,600000,0.2\nsz,000001,0.2\n",
    }


def _config_template(*, data_root: Path) -> str:
    return f"""[paths]
tdx_vipdoc = ""
tdx_export = ""
data_root = "{data_root.as_posix()}"
plugin_dir = "~/.tdx-stocks/plugins"

[build]
markets = ["sh", "sz"]
universe = "ashare"
compression = "zstd"
batch_rows = 200000
duckdb_memory_limit = "8GB"
overwrite_staging = false

[factors]
windows = [5, 10, 20, 60]

[daily]
enabled_strategies = ["trend-strength", "relative-strength", "low-vol-breakout", "volume-breakout"]
strategy_limit = 50
strategy_min_score = 60.0
consensus_min_hit = 2
consensus_limit = 50
portfolio_top = 20
portfolio_weighting = "equal"
exclude_risk_tags = ["high_volatility", "low_liquidity"]
"""


def _daily_template() -> str:
    return """[task]
type = "daily"
name = "daily-workflow"

[data]
as_of = "latest"

[strategies]
enabled = ["trend-strength", "relative-strength", "low-vol-breakout", "volume-breakout"]
limit = 50
min_score = 60

[consensus]
enabled = true
min_hit = 2
limit = 50

[portfolio]
enabled = true
source = "consensus"
top = 20
weighting = "equal"
max_weight = 0.10
exclude_risk_tags = ["high_volatility", "low_liquidity"]

[rebalance]
enabled = false
current_holdings = "holdings.csv"

[output]
save = true
dir = "reports/daily"
formats = ["json", "markdown"]
"""


def _signal_template() -> str:
    return """[task]
type = "signal"
name = "today-signal"

[strategies]
enabled = ["trend-strength", "relative-strength", "low-vol-breakout"]
limit = 50
min_score = 60

[consensus]
enabled = true
min_hit = 2
limit = 50

[output]
save = true
dir = "reports/signals"
formats = ["json", "table"]
"""


def _backtest_template() -> str:
    return """[task]
type = "backtest"
name = "trend-strength-backtest"

[strategy]
name = "trend-strength"
limit = 50
min_score = 60
min_amount_ma20 = 50000000

[backtest]
from_date = "2022-01-01"
to_date = "2024-12-31"
top = 20
hold_days = 5
fee_bps = 3
slippage_bps = 5

[output]
save = true
dir = "reports/backtests"
formats = ["json", "table"]
"""


def _grid_search_template() -> str:
    return """[task]
type = "grid_search"
name = "trend-strength-grid"

[strategy]
name = "trend-strength"
min_amount_ma20 = 50000000

[backtest]
from_date = "2022-01-01"
to_date = "2024-12-31"

[grid]
"strategy.min_score" = [55, 60, 65]
"backtest.top" = [10, 20, 30]
"backtest.hold_days" = [5, 10, 20]

[output]
save = true
dir = "reports/grid_search"
formats = ["json", "csv"]
"""


def _portfolio_template() -> str:
    return """[task]
type = "portfolio"
name = "latest-consensus-portfolio"

[portfolio]
source = "consensus"
top = 20
weighting = "equal"
max_weight = 0.10
exclude_risk_tags = ["high_volatility", "low_liquidity"]

[output]
save = true
dir = "reports/portfolios"
formats = ["json", "table"]
"""


def _rebalance_template() -> str:
    return """[task]
type = "rebalance"
name = "rebalance-from-consensus"

[portfolio]
source = "consensus"
top = 20
weighting = "equal"
max_weight = 0.10

[rebalance]
current_holdings = "holdings.csv"
min_trade_weight = 0.01
max_turnover = 0.50

[output]
save = true
dir = "reports/rebalance"
formats = ["json", "csv"]
"""
