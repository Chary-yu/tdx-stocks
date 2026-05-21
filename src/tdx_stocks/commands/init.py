from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from ..config import DEFAULT_DATA_ROOT, default_config_text


@dataclass(frozen=True)
class InitProfileSpec:
    daily_enabled_strategies: tuple[str, ...]
    daily_strategy_limit: int
    daily_strategy_min_score: float
    daily_consensus_min_hit: int
    daily_portfolio_top: int
    daily_portfolio_weighting: str
    daily_portfolio_max_weight: float
    signal_enabled_strategies: tuple[str, ...]
    signal_strategy_limit: int
    signal_strategy_min_score: float
    backtest_strategy_name: str
    backtest_strategy_limit: int
    backtest_strategy_min_score: float
    backtest_min_amount_ma20: int
    backtest_top: int
    backtest_hold_days: int
    backtest_fee_bps: int
    backtest_slippage_bps: int
    portfolio_name: str
    portfolio_top: int
    portfolio_weighting: str
    portfolio_max_weight: float
    portfolio_exclude_risk_tags: tuple[str, ...]
    rebalance_name: str
    rebalance_enabled: bool
    rebalance_min_trade_weight: float
    rebalance_max_turnover: float
    rebalance_current_holdings: str


def register_init_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("init", help="Initialize a new research workspace.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--minimal", action="store_true")
    parser.add_argument("--profile", choices=("simple", "research", "portfolio"), default="simple")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.set_defaults(func=cmd_init)


def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    data_root = args.data_root if args.data_root.is_absolute() else root / args.data_root
    files = _build_files(root, data_root=args.data_root, profile=args.profile, minimal=args.minimal)
    for rel_dir in (
        "vipdoc",
        "export",
        "reports",
        "reports/daily",
        "reports/backtests",
        "reports/portfolios",
        "reports/signals",
        "reports/grid_search",
        "reports/rebalance",
        "experiments",
        "experiments/advanced",
    ):
        (root / rel_dir).mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
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
    print("  2. Run: tdx-stocks sync")
    print("  3. Run: tdx-stocks run daily --explain")
    return 0


def _build_files(root: Path, *, data_root: Path, profile: str, minimal: bool) -> dict[str, str]:
    spec = _profile_spec(profile)
    config = _config_template(data_root=data_root, spec=spec)
    daily = _daily_template(spec)
    signal = _signal_template(spec)
    if minimal:
        return {
            "tdx_stocks.toml": config,
            "experiments/daily.toml": daily,
            "reports/.gitkeep": "",
        }
    return {
        "tdx_stocks.toml": config,
        "experiments/daily.toml": daily,
        "experiments/backtest.toml": _backtest_template(spec),
        "experiments/portfolio.toml": _portfolio_template(spec),
        "experiments/rebalance.toml": _rebalance_template(spec),
        "experiments/advanced/signal.toml": signal,
        "experiments/advanced/grid_search.toml": _grid_search_template(),
        "experiments/advanced/rebalance.toml": _rebalance_template(spec),
        "reports/.gitkeep": "",
        "holdings.csv.example": "market,symbol,weight\nsh,600000,0.2\nsz,000001,0.2\n",
    }


def _profile_spec(profile: str) -> InitProfileSpec:
    if profile == "simple":
        return InitProfileSpec(
            daily_enabled_strategies=("trend-strength", "relative-strength"),
            daily_strategy_limit=30,
            daily_strategy_min_score=65.0,
            daily_consensus_min_hit=1,
            daily_portfolio_top=10,
            daily_portfolio_weighting="equal",
            daily_portfolio_max_weight=0.08,
            signal_enabled_strategies=("trend-strength", "relative-strength"),
            signal_strategy_limit=30,
            signal_strategy_min_score=65.0,
            backtest_strategy_name="trend-strength",
            backtest_strategy_limit=30,
            backtest_strategy_min_score=65.0,
            backtest_min_amount_ma20=30_000_000,
            backtest_top=10,
            backtest_hold_days=3,
            backtest_fee_bps=5,
            backtest_slippage_bps=8,
            portfolio_name="simple-consensus-portfolio",
            portfolio_top=10,
            portfolio_weighting="equal",
            portfolio_max_weight=0.08,
            portfolio_exclude_risk_tags=("high_volatility", "low_liquidity"),
            rebalance_name="simple-rebalance",
            rebalance_enabled=False,
            rebalance_min_trade_weight=0.01,
            rebalance_max_turnover=0.50,
            rebalance_current_holdings="holdings.csv",
        )
    if profile == "portfolio":
        return InitProfileSpec(
            daily_enabled_strategies=("trend-strength", "relative-strength", "low-vol-breakout", "volume-breakout"),
            daily_strategy_limit=80,
            daily_strategy_min_score=58.0,
            daily_consensus_min_hit=2,
            daily_portfolio_top=50,
            daily_portfolio_weighting="equal",
            daily_portfolio_max_weight=0.05,
            signal_enabled_strategies=("trend-strength", "relative-strength", "low-vol-breakout"),
            signal_strategy_limit=60,
            signal_strategy_min_score=58.0,
            backtest_strategy_name="latest-consensus-portfolio",
            backtest_strategy_limit=80,
            backtest_strategy_min_score=58.0,
            backtest_min_amount_ma20=50_000_000,
            backtest_top=50,
            backtest_hold_days=10,
            backtest_fee_bps=2,
            backtest_slippage_bps=4,
            portfolio_name="latest-consensus-portfolio",
            portfolio_top=50,
            portfolio_weighting="equal",
            portfolio_max_weight=0.05,
            portfolio_exclude_risk_tags=("high_volatility", "low_liquidity"),
            rebalance_name="rebalance-from-consensus",
            rebalance_enabled=True,
            rebalance_min_trade_weight=0.005,
            rebalance_max_turnover=0.30,
            rebalance_current_holdings="holdings.csv",
        )
    return InitProfileSpec(
        daily_enabled_strategies=("trend-strength", "relative-strength", "low-vol-breakout", "volume-breakout"),
        daily_strategy_limit=50,
        daily_strategy_min_score=60.0,
        daily_consensus_min_hit=2,
        daily_portfolio_top=20,
        daily_portfolio_weighting="equal",
        daily_portfolio_max_weight=0.10,
        signal_enabled_strategies=("trend-strength", "relative-strength", "low-vol-breakout"),
        signal_strategy_limit=50,
        signal_strategy_min_score=60.0,
        backtest_strategy_name="trend-strength",
        backtest_strategy_limit=50,
        backtest_strategy_min_score=60.0,
        backtest_min_amount_ma20=50_000_000,
        backtest_top=20,
        backtest_hold_days=5,
        backtest_fee_bps=3,
        backtest_slippage_bps=5,
        portfolio_name="latest-consensus-portfolio",
        portfolio_top=20,
        portfolio_weighting="equal",
        portfolio_max_weight=0.10,
        portfolio_exclude_risk_tags=("high_volatility", "low_liquidity"),
        rebalance_name="rebalance-from-consensus",
        rebalance_enabled=False,
        rebalance_min_trade_weight=0.01,
        rebalance_max_turnover=0.50,
        rebalance_current_holdings="holdings.csv",
    )


def _config_template(*, data_root: Path, spec: InitProfileSpec) -> str:
    base = default_config_text(data_root=data_root)
    start = base.index("[daily]")
    return (
        base[:start]
        + _daily_config_block(spec)
    )


def _daily_config_block(spec: InitProfileSpec) -> str:
    return f"""[daily]
enabled_strategies = [{_quoted_list(spec.daily_enabled_strategies)}]
strategy_limit = {spec.daily_strategy_limit}
strategy_min_score = {spec.daily_strategy_min_score}
consensus_min_hit = {spec.daily_consensus_min_hit}
consensus_limit = 50
portfolio_top = {spec.daily_portfolio_top}
portfolio_weighting = "{spec.daily_portfolio_weighting}"
portfolio_max_weight = {spec.daily_portfolio_max_weight:.2f}
exclude_risk_tags = ["high_volatility", "low_liquidity"]
"""


def _daily_template(spec: InitProfileSpec) -> str:
    return f"""[task]
type = "daily"
name = "daily-workflow"

[data]
as_of = "latest"

[strategies]
enabled = [{_quoted_list(spec.daily_enabled_strategies)}]
limit = {spec.daily_strategy_limit}
min_score = {_format_number(spec.daily_strategy_min_score)}

[consensus]
enabled = true
min_hit = {spec.daily_consensus_min_hit}
limit = 50

[portfolio]
enabled = true
source = "consensus"
top = {spec.daily_portfolio_top}
weighting = "{spec.daily_portfolio_weighting}"
max_weight = {spec.daily_portfolio_max_weight:.2f}
exclude_risk_tags = ["high_volatility", "low_liquidity"]

[rebalance]
enabled = {str(spec.rebalance_enabled).lower()}
current_holdings = "holdings.csv"

[output]
save = true
dir = "reports/daily"
formats = ["json", "markdown"]
"""


def _signal_template(spec: InitProfileSpec) -> str:
    return f"""[task]
type = "signal"
name = "today-signal"

[strategies]
enabled = [{_quoted_list(spec.signal_enabled_strategies)}]
limit = {spec.signal_strategy_limit}
min_score = {_format_number(spec.signal_strategy_min_score)}

[consensus]
enabled = true
min_hit = {spec.daily_consensus_min_hit}
limit = 50

[output]
save = true
dir = "reports/signals"
formats = ["json", "table"]
"""


def _backtest_template(spec: InitProfileSpec) -> str:
    return f"""[task]
type = "backtest"
name = "{spec.backtest_strategy_name}"

[strategy]
name = "{spec.backtest_strategy_name}"
limit = {spec.backtest_strategy_limit}
min_score = {_format_number(spec.backtest_strategy_min_score)}
min_amount_ma20 = {spec.backtest_min_amount_ma20}

[backtest]
from_date = "2022-01-01"
to_date = "2024-12-31"
top = {spec.backtest_top}
hold_days = {spec.backtest_hold_days}
fee_bps = {spec.backtest_fee_bps}
slippage_bps = {spec.backtest_slippage_bps}

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


def _portfolio_template(spec: InitProfileSpec) -> str:
    return f"""[task]
type = "portfolio"
name = "{spec.portfolio_name}"

[portfolio]
source = "consensus"
top = {spec.portfolio_top}
weighting = "{spec.portfolio_weighting}"
max_weight = {spec.portfolio_max_weight:.2f}
exclude_risk_tags = [{_quoted_list(spec.portfolio_exclude_risk_tags)}]

[output]
save = true
dir = "reports/portfolios"
formats = ["json", "table"]
"""


def _rebalance_template(spec: InitProfileSpec) -> str:
    return f"""[task]
type = "rebalance"
name = "{spec.rebalance_name}"

[portfolio]
source = "consensus"
top = {spec.portfolio_top}
weighting = "{spec.portfolio_weighting}"
max_weight = {spec.portfolio_max_weight:.2f}

[rebalance]
current_holdings = "../holdings.csv.example"
min_trade_weight = {spec.rebalance_min_trade_weight:.3f}
max_turnover = {spec.rebalance_max_turnover:.2f}
enabled = {str(spec.rebalance_enabled).lower()}

[output]
save = true
dir = "reports/rebalance"
formats = ["json", "csv"]
"""


def _quoted_list(values: tuple[str, ...]) -> str:
    return ", ".join(f'"{value}"' for value in values)


def _format_number(value: float, *, digits: int = 1) -> str:
    if float(value).is_integer() and digits == 1:
        return str(int(value))
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")
