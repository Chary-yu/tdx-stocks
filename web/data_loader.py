from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def load_backtest_report(json_path: Path) -> dict[str, Any]:
    with json_path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)
    return normalize_report(report, source_path=json_path)


def normalize_report(report: dict[str, Any], *, source_path: Path | None = None) -> dict[str, Any]:
    summary = report.get("summary") or {}
    params = report.get("params") or {}
    equity_df = _build_equity_frame(report)
    trades_df = _build_trades_frame(report)
    candidates_df = _build_candidates_frame(report)
    periods_df = _build_periods_frame(report)
    monthly_df = _build_monthly_frame(equity_df)
    return {
        "source_path": str(source_path) if source_path else None,
        "schema_version": report.get("schema_version"),
        "strategy_name": report.get("strategy_name") or summary.get("strategy") or "unknown",
        "summary": summary,
        "params": params,
        "equity_df": equity_df,
        "periods_df": periods_df,
        "trades_df": trades_df,
        "candidates_df": candidates_df,
        "monthly_df": monthly_df,
        "raw": report,
    }


def discover_report_files(reports_root: Path) -> list[Path]:
    if not reports_root.exists():
        return []
    files = [path for path in reports_root.glob("**/*.json") if path.is_file()]
    return sorted(files, key=lambda item: item.as_posix())


def _build_equity_frame(report: dict[str, Any]) -> pd.DataFrame:
    rows = report.get("equity_curve")
    if not rows:
        rows = report.get("periods") or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    date_column = "trade_date" if "trade_date" in df.columns else "signal_date" if "signal_date" in df.columns else None
    if date_column is not None:
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        df = df.sort_values(date_column).set_index(date_column)
    if "equity" in df.columns:
        df["peak"] = df["equity"].cummax()
        df["drawdown"] = (df["equity"] - df["peak"]) / df["peak"].where(df["peak"] != 0, pd.NA)
    if "period_return" in df.columns and "return" not in df.columns:
        df["return"] = df["period_return"]
    return df


def _build_periods_frame(report: dict[str, Any]) -> pd.DataFrame:
    df = pd.DataFrame(report.get("periods") or [])
    if df.empty:
        return df
    for column in ("signal_date", "buy_date", "sell_date"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def _build_trades_frame(report: dict[str, Any]) -> pd.DataFrame:
    df = pd.DataFrame(report.get("trades") or [])
    if df.empty:
        return df
    for column in ("signal_date", "buy_date", "sell_date"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def _build_candidates_frame(report: dict[str, Any]) -> pd.DataFrame:
    candidates = report.get("candidates") or report.get("picks") or []
    df = pd.DataFrame(candidates)
    if df.empty:
        return df
    for column in ("trade_date", "execute_date"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def _build_monthly_frame(df_equity: pd.DataFrame) -> pd.DataFrame:
    if df_equity.empty:
        return pd.DataFrame()
    index = df_equity.index
    if not isinstance(index, pd.DatetimeIndex):
        return pd.DataFrame()
    equity = df_equity["equity"].dropna()
    if equity.empty:
        return pd.DataFrame()
    monthly = equity.resample("M").last().pct_change().fillna(0.0)
    frame = monthly.to_frame(name="monthly_return")
    frame["year"] = frame.index.year
    frame["month"] = frame.index.month
    return frame.reset_index(drop=True)
