from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Any

from ..config import AppConfig, BuildConfig, FactorConfig, PathsConfig


@dataclass(frozen=True)
class StrategyParams:
    limit: int | None = None
    min_score: float | None = None
    min_amount_ma20: float | None = None
    market: str | None = None
    candidate_type: str | None = None
    include_excluded: bool = False
    show_excluded_limit: int | None = None
    explain_symbol: str | None = None
    as_of: date | None = None
    factors: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "limit": self.limit,
            "min_score": self.min_score,
            "min_amount_ma20": self.min_amount_ma20,
            "market": self.market,
            "candidate_type": self.candidate_type,
            "include_excluded": self.include_excluded,
            "show_excluded_limit": self.show_excluded_limit,
            "explain_symbol": self.explain_symbol,
            "as_of": self.as_of.isoformat() if self.as_of else None,
        }
        if self.factors:
            payload["factors"] = self.factors
        return payload


@dataclass(frozen=True)
class BatchSearchConfig:
    enabled: bool = False
    parameters: dict[str, list[Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BatchSearchConfig":
        if not data:
            return cls()
        enabled = bool(data.get("enabled", False))
        parameters: dict[str, list[Any]] = {}
        for key, value in data.items():
            if key == "enabled":
                continue
            if isinstance(value, list):
                parameters[key] = list(value)
            else:
                parameters[key] = [value]
        return cls(enabled=enabled, parameters=parameters)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"enabled": self.enabled}
        payload.update(self.parameters)
        return payload


@dataclass(frozen=True)
class BacktestConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    factors: FactorConfig = field(default_factory=FactorConfig)
    strategy_name: str = "trend-strength"
    engine: "BacktestParams" | None = None
    strategy: StrategyParams = field(default_factory=StrategyParams)
    batch_search: BatchSearchConfig = field(default_factory=BatchSearchConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BacktestConfig":
        paths = _build_paths_config(data.get("paths") or {})
        build = _build_build_config(data.get("build") or {})
        factors = _build_factor_config(data.get("factors") or {})
        strategy_section = data.get("strategy") or {}
        strategy_name = str(
            data.get("strategy_name")
            or (strategy_section.get("name") if isinstance(strategy_section, dict) else None)
            or data.get("name")
            or "trend-strength"
        )
        engine = _build_backtest_params(data)
        strategy = _build_strategy_config(data)
        batch_search = BatchSearchConfig.from_dict(data.get("batch_search"))
        return cls(
            paths=paths,
            build=build,
            factors=factors,
            strategy_name=strategy_name,
            engine=engine,
            strategy=strategy,
            batch_search=batch_search,
        )

    def to_app_config(self) -> AppConfig:
        return AppConfig(paths=self.paths, build=self.build, factors=self.factors)

    def to_backtest_params(self) -> "BacktestParams":
        if self.engine is None:
            raise ValueError("backtest.engine section is required")
        top = self.strategy.limit if self.strategy.limit is not None else self.engine.top
        market = self.strategy.market if self.strategy.market is not None else self.engine.market
        candidate_type = (
            self.strategy.candidate_type if self.strategy.candidate_type is not None else self.engine.candidate_type
        )
        min_score = self.strategy.min_score if self.strategy.min_score is not None else self.engine.min_score
        min_amount_ma20 = (
            self.strategy.min_amount_ma20 if self.strategy.min_amount_ma20 is not None else self.engine.min_amount_ma20
        )
        return BacktestParams(
            from_date=self.engine.from_date,
            to_date=self.engine.to_date,
            top=top,
            hold_days=self.engine.hold_days,
            fee_rate=self.engine.fee_rate,
            slippage=self.engine.slippage,
            market=market,
            candidate_type=candidate_type,
            min_score=min_score,
            min_amount_ma20=min_amount_ma20,
            portfolio=self.engine.portfolio,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "paths": {
                "tdx_vipdoc": self.paths.tdx_vipdoc.as_posix(),
                "tdx_export": self.paths.tdx_export.as_posix(),
                "data_root": self.paths.data_root.as_posix(),
                "plugin_dir": self.paths.plugin_dir.as_posix(),
            },
            "build": {
                "markets": list(self.build.markets),
                "universe": self.build.universe,
                "compression": self.build.compression,
                "batch_rows": self.build.batch_rows,
                "duckdb_memory_limit": self.build.duckdb_memory_limit,
                "overwrite_staging": self.build.overwrite_staging,
            },
            "factors": {
                "windows": list(self.factors.windows),
            },
            "strategy_name": self.strategy_name,
            "strategy": self.strategy.to_dict(),
            "batch_search": self.batch_search.to_dict(),
        }
        if self.engine is not None:
            payload["engine"] = self.engine.to_dict()
        return payload


@dataclass(frozen=True)
class PortfolioParams:
    initial_cash: float = 1_000_000.0
    max_positions: int = 5
    stop_loss_pct: float | None = 0.08
    margin_rate: float = 0.5


@dataclass
class Position:
    symbol: str
    shares: int
    buy_price: float
    buy_date: date
    direction: str = "LONG"
    market: str | None = None
    display_symbol: str | None = None
    score: float | None = None
    candidate_type: str | None = None
    signal_date: date | None = None
    margin_locked: float = 0.0


@dataclass(frozen=True)
class BacktestParams:
    from_date: date
    to_date: date
    top: int = 20
    hold_days: int = 5
    fee_rate: float = 0.0
    slippage: float = 0.0
    market: str | None = None
    candidate_type: str | None = None
    min_score: float | None = None
    min_amount_ma20: float | None = None
    portfolio: PortfolioParams | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
            "top": self.top,
            "hold_days": self.hold_days,
            "fee_rate": self.fee_rate,
            "slippage": self.slippage,
            "market": self.market,
            "candidate_type": self.candidate_type,
            "min_score": self.min_score,
            "min_amount_ma20": self.min_amount_ma20,
            "portfolio": asdict(self.portfolio) if self.portfolio is not None else None,
        }


@dataclass(frozen=True)
class BacktestTrade:
    signal_date: str
    buy_date: str | None
    sell_date: str | None
    market: str
    symbol: str
    display_symbol: str
    score: float | None
    candidate_type: str | None
    buy_price: float | None
    sell_price: float | None
    gross_return: float | None
    net_return: float | None
    direction: str = "LONG"
    shares: int | None = None
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestPeriod:
    signal_date: str
    buy_date: str | None
    sell_date: str | None
    trade_count: int
    empty: bool
    period_return: float
    equity: float
    skipped_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestReport:
    schema_version: str
    app_version: str
    strategy_name: str
    params: dict[str, Any]
    start_date: str
    end_date: str
    trade_count: int
    period_count: int
    empty_period_count: int
    total_return: float
    annual_return: float
    max_drawdown: float
    win_rate: float
    avg_period_return: float
    best_period_return: float
    worst_period_return: float
    turnover: float
    equity_curve: list[dict[str, Any]]
    periods: list[dict[str, Any]]
    trades: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _build_paths_config(data: dict[str, Any]) -> PathsConfig:
    return PathsConfig(
        tdx_vipdoc=_coerce_path(data.get("tdx_vipdoc", PathsConfig().tdx_vipdoc)),
        tdx_export=_coerce_path(data.get("tdx_export", PathsConfig().tdx_export)),
        data_root=_coerce_path(data.get("data_root", PathsConfig().data_root)),
        plugin_dir=_coerce_path(data.get("plugin_dir", PathsConfig().plugin_dir)).expanduser(),
    )


def _build_build_config(data: dict[str, Any]) -> BuildConfig:
    defaults = BuildConfig()
    return BuildConfig(
        markets=tuple(data.get("markets", defaults.markets)),
        universe=str(data.get("universe", defaults.universe)),
        compression=str(data.get("compression", defaults.compression)),
        batch_rows=int(data.get("batch_rows", defaults.batch_rows)),
        duckdb_memory_limit=str(data.get("duckdb_memory_limit", defaults.duckdb_memory_limit)),
        overwrite_staging=bool(data.get("overwrite_staging", defaults.overwrite_staging)),
    )


def _build_factor_config(data: dict[str, Any]) -> FactorConfig:
    defaults = FactorConfig()
    windows = data.get("windows", defaults.windows)
    return FactorConfig(windows=tuple(int(item) for item in windows))


def _build_strategy_config(data: dict[str, Any]) -> StrategyParams:
    strategy_data = dict(data.get("strategy") or {})
    for key in ("limit", "min_score", "min_amount_ma20", "market", "candidate_type", "include_excluded", "show_excluded_limit", "explain_symbol", "as_of", "factors"):
        if key not in strategy_data and key in data:
            strategy_data[key] = data[key]
    return StrategyParams(
        limit=_coerce_optional_int(strategy_data.get("limit")),
        min_score=_coerce_optional_float(strategy_data.get("min_score")),
        min_amount_ma20=_coerce_optional_float(strategy_data.get("min_amount_ma20")),
        market=str(strategy_data["market"]) if strategy_data.get("market") is not None else None,
        candidate_type=str(strategy_data["candidate_type"]) if strategy_data.get("candidate_type") is not None else None,
        include_excluded=bool(strategy_data.get("include_excluded", False)),
        show_excluded_limit=_coerce_optional_int(strategy_data.get("show_excluded_limit")),
        explain_symbol=str(strategy_data["explain_symbol"]) if strategy_data.get("explain_symbol") is not None else None,
        as_of=_coerce_date(strategy_data.get("as_of")),
        factors=dict(strategy_data.get("factors", {})),
    )


def _build_backtest_params(data: dict[str, Any]) -> BacktestParams | None:
    engine_data = dict(data.get("engine") or data.get("backtest") or {})
    for key in ("from_date", "to_date", "top", "hold_days", "fee_rate", "slippage", "market", "candidate_type", "min_score", "min_amount_ma20", "portfolio"):
        if key not in engine_data and key in data:
            engine_data[key] = data[key]
    if not engine_data:
        return None
    portfolio_data = engine_data.get("portfolio")
    portfolio = _build_portfolio_config(portfolio_data) if isinstance(portfolio_data, dict) else portfolio_data
    from_date = _coerce_date(engine_data.get("from_date"))
    to_date = _coerce_date(engine_data.get("to_date"))
    if from_date is None or to_date is None:
        raise ValueError("backtest.engine.from_date and backtest.engine.to_date are required")
    defaults = BacktestParams(from_date=from_date, to_date=to_date)
    return BacktestParams(
        from_date=from_date,
        to_date=to_date,
        top=int(engine_data.get("top", defaults.top)),
        hold_days=int(engine_data.get("hold_days", defaults.hold_days)),
        fee_rate=float(engine_data.get("fee_rate", defaults.fee_rate)),
        slippage=float(engine_data.get("slippage", defaults.slippage)),
        market=str(engine_data["market"]) if engine_data.get("market") is not None else None,
        candidate_type=str(engine_data["candidate_type"]) if engine_data.get("candidate_type") is not None else None,
        min_score=_coerce_optional_float(engine_data.get("min_score")),
        min_amount_ma20=_coerce_optional_float(engine_data.get("min_amount_ma20")),
        portfolio=portfolio,
    )


def _build_portfolio_config(data: dict[str, Any] | None) -> PortfolioParams:
    defaults = PortfolioParams()
    payload = data or {}
    stop_loss_pct = payload.get("stop_loss_pct", defaults.stop_loss_pct)
    return PortfolioParams(
        initial_cash=float(payload.get("initial_cash", defaults.initial_cash)),
        max_positions=int(payload.get("max_positions", defaults.max_positions)),
        stop_loss_pct=_coerce_optional_float(stop_loss_pct),
        margin_rate=float(payload.get("margin_rate", defaults.margin_rate)),
    )


def _coerce_path(value: Any) -> Path:
    if isinstance(value, Path):
        return value
    return Path(str(value))


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
