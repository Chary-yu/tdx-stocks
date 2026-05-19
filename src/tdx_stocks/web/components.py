from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def plot_equity_curve(df_equity: pd.DataFrame):
    fig = go.Figure()
    if not df_equity.empty and "equity" in df_equity.columns:
        fig.add_trace(
            go.Scatter(
                x=df_equity.index,
                y=df_equity["equity"],
                mode="lines",
                name="Equity",
                line={"width": 2, "color": "#60a5fa"},
            )
        )
    fig.update_layout(
        title="资金净值走势",
        template="plotly_dark",
        xaxis_title="日期",
        yaxis_title="净值",
        hovermode="x unified",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    return fig


def plot_underwater_drawdown(df_equity: pd.DataFrame):
    fig = go.Figure()
    if not df_equity.empty and "drawdown" in df_equity.columns:
        fig.add_trace(
            go.Scatter(
                x=df_equity.index,
                y=df_equity["drawdown"],
                mode="lines",
                name="Drawdown",
                line={"width": 1.5, "color": "#f87171"},
                fill="tozeroy",
                fillcolor="rgba(248,113,113,0.25)",
            )
        )
    fig.update_layout(
        title="历史回撤",
        template="plotly_dark",
        xaxis_title="日期",
        yaxis_title="回撤",
        yaxis_tickformat=".2%",
        hovermode="x unified",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    return fig


def plot_monthly_heatmap(df_monthly: pd.DataFrame):
    if df_monthly.empty or not {"year", "month", "monthly_return"}.issubset(df_monthly.columns):
        return go.Figure().update_layout(template="plotly_dark", title="月度收益热力图")
    pivot = df_monthly.pivot(index="year", columns="month", values="monthly_return").sort_index()
    pivot = pivot.reindex(columns=range(1, 13))
    fig = px.imshow(
        pivot,
        color_continuous_scale="RdYlGn",
        aspect="auto",
        labels={"color": "月收益"},
        title="月度收益热力图",
        text_auto=".1%",
    )
    fig.update_layout(template="plotly_dark", margin={"l": 20, "r": 20, "t": 50, "b": 20})
    fig.update_xaxes(title="月份")
    fig.update_yaxes(title="年份")
    return fig


def plot_trade_returns(df_trades: pd.DataFrame):
    fig = go.Figure()
    if not df_trades.empty and "net_return" in df_trades.columns:
        fig.add_trace(
            go.Histogram(
                x=df_trades["net_return"],
                nbinsx=30,
                marker_color="#a78bfa",
                name="Net Return",
            )
        )
    fig.update_layout(
        title="交易收益分布",
        template="plotly_dark",
        xaxis_title="单笔净收益",
        yaxis_title="频次",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    return fig
