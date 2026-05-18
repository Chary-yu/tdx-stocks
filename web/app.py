from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tdx_stocks.config import AppConfig, load_config
from tdx_stocks.strategies.storage import latest_report_dir, strategy_reports_root

from web.components import plot_equity_curve, plot_monthly_heatmap, plot_trade_returns, plot_underwater_drawdown
from web.data_loader import discover_report_files, load_backtest_report


st.set_page_config(page_title="tdx-stocks 量化投研中台", layout="wide", page_icon="📈")


def _resolve_data_root() -> Path:
    env_root = os.environ.get("TDX_STOCKS_DATA_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    config_path = os.environ.get("TDX_STOCKS_CONFIG")
    if config_path:
        return load_config(Path(config_path)).paths.data_root
    return AppConfig().paths.data_root


def _render_kpis(summary: dict[str, object]) -> None:
    cols = st.columns(5)
    cols[0].metric("总收益率", _format_pct(summary.get("total_return")))
    cols[1].metric("年化收益", _format_pct(summary.get("annual_return")))
    cols[2].metric("最大回撤", _format_pct(summary.get("max_drawdown")))
    cols[3].metric("胜率", _format_pct(summary.get("win_rate")))
    cols[4].metric("换手率", _format_pct(summary.get("turnover")))


def _format_pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def _format_number(value: object) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


st.title("tdx-stocks 投研可视化中台")
st.caption("加载已保存的回测报告，查看净值、回撤、交易与月度表现。")

data_root = _resolve_data_root()
reports_root_default = latest_report_dir(data_root)
report_scan_root = strategy_reports_root(data_root)

with st.sidebar:
    st.header("数据源")
    data_root_input = st.text_input("数据根目录", value=data_root.as_posix())
    reports_root_input = st.text_input("报告目录", value=reports_root_default.as_posix())
    upload = st.file_uploader("导入 JSON 报告", type=["json"])
    reports_root = Path(reports_root_input).expanduser()
    report_files = discover_report_files(reports_root)
    if report_files:
        chosen = st.selectbox("选择报告", [path.as_posix() for path in report_files])
    else:
        chosen = None

if upload is not None:
    import json
    from tempfile import NamedTemporaryFile

    raw = upload.getvalue().decode("utf-8")
    with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        handle.write(raw)
        temp_path = Path(handle.name)
    report = load_backtest_report(temp_path)
else:
    if chosen is None:
        st.error(f"未找到报告文件。当前扫描目录: {report_scan_root}")
        st.stop()
    report = load_backtest_report(Path(chosen))

summary = report.get("summary") or {}
params = report.get("params") or {}
equity_df = report.get("equity_df")
periods_df = report.get("periods_df")
trades_df = report.get("trades_df")
candidates_df = report.get("candidates_df")
monthly_df = report.get("monthly_df")

st.subheader("核心指标")
_render_kpis(summary)

tab_equity, tab_trades, tab_periods, tab_params, tab_raw = st.tabs(
    ["净值曲线", "交易流水", "周期明细", "参数", "原始 JSON"]
)

with tab_equity:
    left, right = st.columns([2, 1])
    with left:
        st.plotly_chart(plot_equity_curve(equity_df), use_container_width=True)
        st.plotly_chart(plot_underwater_drawdown(equity_df), use_container_width=True)
        st.plotly_chart(plot_monthly_heatmap(monthly_df), use_container_width=True)
    with right:
        st.subheader("概览")
        st.write(
            {
                "strategy_name": report.get("strategy_name"),
                "schema_version": report.get("schema_version"),
                "source_path": report.get("source_path"),
                "equity_rows": int(len(equity_df)) if equity_df is not None else 0,
                "trade_rows": int(len(trades_df)) if trades_df is not None else 0,
            }
        )
        if candidates_df is not None and not candidates_df.empty:
            st.subheader("候选统计")
            st.dataframe(candidates_df.head(20), use_container_width=True, height=280)

with tab_trades:
    st.plotly_chart(plot_trade_returns(trades_df), use_container_width=True)
    if trades_df is not None and not trades_df.empty:
        view_cols = [col for col in ["market", "symbol", "signal_date", "buy_date", "sell_date", "direction", "gross_return", "net_return", "skipped_reason"] if col in trades_df.columns]
        st.dataframe(trades_df[view_cols], use_container_width=True, height=480)
    else:
        st.info("报告中没有交易明细。")

with tab_periods:
    if periods_df is not None and not periods_df.empty:
        st.dataframe(periods_df, use_container_width=True, height=520)
    else:
        st.info("报告中没有周期明细。")

with tab_params:
    st.json(params)

with tab_raw:
    st.json(report.get("raw") or {})
