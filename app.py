"""
MES 回放交易分析面板 v2

UI 结构：
- 左侧边栏：导航（总结 / 交易详情）、交易列表、设置齿轮
- 总结页：统计数据、权益曲线、盈亏分布
- 交易详情页：K 线图 + 交易数据

运行方式：
    cd /Users/exia/git/ExiaQuant
    source venv/bin/activate
    streamlit run app.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as components

import qlib
from qlib.data import D
from qlib.config import C

from chart_lwc import render_chart

ROOT = Path(__file__).resolve().parent
TRADES_CSV = ROOT / "data" / "replay_trades_parsed.csv"
QLIB_BASE = ROOT / "data" / "qlib_data"

st.set_page_config(page_title="MES 回放交易分析", layout="wide", initial_sidebar_state="expanded")


# ───────────────────────────────────────────────
# 初始化
# ───────────────────────────────────────────────
@st.cache_resource
def init_qlib():
    qlib.init(
        provider_uri={
            "5min": str(QLIB_BASE / "futures_5min"),
            "15min": str(QLIB_BASE / "futures_15min"),
            "60min": str(QLIB_BASE / "futures_60min"),
        },
        region="us",
    )
    C.joblib_backend = "threading"
    return True


init_qlib()


# ───────────────────────────────────────────────
# 数据加载
# ───────────────────────────────────────────────
@st.cache_data
def load_trades() -> pd.DataFrame:
    df = pd.read_csv(TRADES_CSV)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["win"] = df["pnl_usd"] > 0
    df["session"] = df["entry_time"].dt.hour.apply(session_of_hour)
    return df


def session_of_hour(h):
    if 0 <= h < 8:
        return "亚盘"
    elif 8 <= h < 16:
        return "欧盘"
    else:
        return "美盘"


@st.cache_data
def load_klines(freq: str, start_dt: str, end_dt: str) -> pd.DataFrame:
    instruments = D.instruments("all")
    fields = ["$open", "$high", "$low", "$close", "$volume"]
    df = D.features(instruments, fields, freq=freq)
    df = df.rename(
        columns={
            "$open": "open",
            "$high": "high",
            "$low": "low",
            "$close": "close",
            "$volume": "volume",
        }
    )
    df = df.reset_index()
    df = df[(df["datetime"] >= start_dt) & (df["datetime"] <= end_dt)]
    return df


# ───────────────────────────────────────────────
# 指标计算
# ───────────────────────────────────────────────
def compute_metrics(trades: pd.DataFrame) -> dict:
    wins = trades[trades["pnl_usd"] > 0]
    losses = trades[trades["pnl_usd"] <= 0]
    win_rate = len(wins) / len(trades) if len(trades) > 0 else 0

    avg_win = wins["pnl_usd"].mean() if len(wins) > 0 else 0
    avg_loss = losses["pnl_usd"].mean() if len(losses) > 0 else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else np.inf

    equity = (1 + trades["return_pct"] / 100).cumprod()
    total_return = equity.iloc[-1] - 1 if len(equity) > 0 else 0
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_dd = drawdown.min()

    mean_ret = trades["return_pct"].mean()
    std_ret = trades["return_pct"].std()
    sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0

    return {
        "total_trades": len(trades),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "total_pnl": trades["pnl_usd"].sum(),
        "max_drawdown_pct": max_dd * 100,
        "sharpe": sharpe,
        "avg_duration_min": trades["duration_minutes"].mean(),
        "consec_wins": max_consecutive(trades["win"].astype(int)),
        "consec_losses": max_consecutive((~trades["win"]).astype(int)),
    }


def max_consecutive(series):
    max_count = count = 0
    for v in series:
        if v == 1:
            count += 1
            max_count = max(max_count, count)
        else:
            count = 0
    return max_count


# ───────────────────────────────────────────────
# 侧边栏
# ───────────────────────────────────────────────
def sidebar(trades: pd.DataFrame):
    st.sidebar.title("📈 MES 复盘")

    # 页面导航
    st.sidebar.markdown("### 页面")
    nav_cols = st.sidebar.columns(2)
    if nav_cols[0].button("📊 总结", use_container_width=True, type=("primary" if st.session_state.page == "summary" else "secondary")):
        st.session_state.page = "summary"
        st.rerun()
    if nav_cols[1].button("📈 交易", use_container_width=True, type=("primary" if st.session_state.page == "detail" else "secondary")):
        st.session_state.page = "detail"
        st.rerun()

    st.sidebar.divider()

    # 交易列表（仅在交易页显示完整列表，总结页可隐藏）
    if st.session_state.page == "detail":
        st.sidebar.markdown("### 交易列表")
        for _, row in trades.iterrows():
            icon = "✅" if row["pnl_usd"] > 0 else "❌"
            label = f"{icon} #{row['trade_id']} {row['direction'].upper()} ${row['pnl_usd']:.2f}"
            if st.sidebar.button(label, key=f"trade_btn_{row['trade_id']}", use_container_width=True):
                st.session_state.selected_trade_id = int(row["trade_id"])
                st.rerun()

    # 齿轮设置
    st.sidebar.divider()
    with st.sidebar.expander("⚙️ 设置", expanded=False):
        st.session_state.chart_height = st.slider("图表高度", 300, 900, 560, key="setting_height")
        st.session_state.bars_before = st.slider("进场前 K 线数", 10, 200, 50, key="setting_before")
        st.session_state.bars_after = st.slider("出场后 K 线数", 10, 200, 50, key="setting_after")


# ───────────────────────────────────────────────
# 总结页
# ───────────────────────────────────────────────
def summary_page(trades: pd.DataFrame):
    st.header("📊 交易总结")

    metrics = compute_metrics(trades)

    # 指标卡
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("总交易数", metrics["total_trades"])
    c2.metric("胜率", f"{metrics['win_rate']*100:.1f}%")
    c3.metric("盈亏比", f"{metrics['profit_factor']:.2f}")
    c4.metric("总盈亏", f"${metrics['total_pnl']:.2f}")
    c5.metric("最大回撤", f"{metrics['max_drawdown_pct']:.2f}%")
    c6.metric("夏普", f"{metrics['sharpe']:.2f}")

    st.divider()

    # 图表区
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("权益曲线")
        equity = (1 + trades["return_pct"] / 100).cumprod()
        fig = go.Figure(go.Scatter(x=trades["exit_time"], y=equity, mode="lines", line=dict(color="#26a69a", width=2), fill="tozeroy", fillcolor="rgba(38, 166, 154, 0.1)"))
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="#131722", plot_bgcolor="#131722", font_color="#d1d4dc", xaxis_gridcolor="#1e222d", yaxis_gridcolor="#1e222d")
        st.plotly_chart(fig, use_container_width=True, key="equity_curve")

    with col_right:
        st.subheader("盈亏分布")
        fig = px.histogram(trades, x="pnl_usd", nbins=20, color="win", color_discrete_map={True: "#26a69a", False: "#ef5350"})
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="#131722", plot_bgcolor="#131722", font_color="#d1d4dc", xaxis_gridcolor="#1e222d", yaxis_gridcolor="#1e222d", showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key="pnl_hist")

    col_left2, col_right2 = st.columns(2)

    with col_left2:
        st.subheader("时段胜率")
        session_stats = trades.groupby("session").agg(win_rate=("win", "mean"), count=("win", "size")).reset_index()
        fig = go.Figure(go.Bar(x=session_stats["session"], y=session_stats["win_rate"]*100, marker_color=["#26a69a" if v >= 0.5 else "#ef5350" for v in session_stats["win_rate"]], text=session_stats["count"], textposition="auto"))
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="#131722", plot_bgcolor="#131722", font_color="#d1d4dc", xaxis_gridcolor="#1e222d", yaxis_gridcolor="#1e222d", yaxis=dict(ticksuffix="%"))
        st.plotly_chart(fig, use_container_width=True, key="session_winrate")

    with col_right2:
        st.subheader("MAE/MFE 散点")
        fig = px.scatter(trades, x="mae_usd", y="mfe_usd", color="win", color_discrete_map={True: "#26a69a", False: "#ef5350"}, hover_data=["trade_id"])
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.add_vline(x=0, line_dash="dash", line_color="gray")
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="#131722", plot_bgcolor="#131722", font_color="#d1d4dc", xaxis_gridcolor="#1e222d", yaxis_gridcolor="#1e222d")
        st.plotly_chart(fig, use_container_width=True, key="mae_mfe")

    st.divider()
    st.subheader("交易明细")
    display_df = trades[["trade_id", "direction", "entry_time", "exit_time", "pnl_usd", "return_pct", "duration_minutes", "mfe_usd", "mae_usd", "session"]].copy()
    display_df["结果"] = display_df["pnl_usd"].apply(lambda x: "✅ 盈" if x > 0 else "❌ 亏")
    st.dataframe(display_df, use_container_width=True)


# ───────────────────────────────────────────────
# 交易详情页
# ───────────────────────────────────────────────
def detail_page(trades: pd.DataFrame):
    selected_id = st.session_state.get("selected_trade_id", trades.iloc[0]["trade_id"])
    trade = trades[trades["trade_id"] == selected_id].iloc[0]

    # 顶部导航
    cols = st.columns([1, 6])
    if cols[0].button("⬅️ 返回总结", use_container_width=True):
        st.session_state.page = "summary"
        st.rerun()
    cols[1].header(f"交易 #{selected_id} 详情")

    # 计算窗口
    df_5m_for_window = load_klines(
        "5min",
        (trade["entry_time"] - pd.Timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S"),
        (trade["exit_time"] + pd.Timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    if df_5m_for_window.empty:
        st.warning("⚠️ 该交易时间窗口没有本地 K 线数据。")
        st.markdown("如果这笔交易发生在**最近 1~2 天**，可以用 QuantData 从 TradingView 拉取：")
        st.code(
            f"python3 scripts/fetch_tv_data.py --symbol MES1! --timeframe 5m "
            f"--start {trade['entry_time'].date()} --end {trade['exit_time'].date()}"
        )
        st.markdown(
            "更早的历史交易请用本地 1 分钟行情生成："
            "`python3 scripts/prepare_mes_intraday_qlib.py --input <1分钟行情.csv> --symbol MES`"
        )
        return

    entry_idx = (df_5m_for_window["datetime"] <= trade["entry_time"]).sum() - 1
    exit_idx = (df_5m_for_window["datetime"] <= trade["exit_time"]).sum() - 1
    start_idx = max(0, entry_idx - st.session_state.bars_before)
    end_idx = min(len(df_5m_for_window) - 1, exit_idx + st.session_state.bars_after)
    window_start = df_5m_for_window.iloc[start_idx]["datetime"]
    window_end = df_5m_for_window.iloc[end_idx]["datetime"]
    start_str = window_start.strftime("%Y-%m-%d %H:%M:%S")
    end_str = window_end.strftime("%Y-%m-%d %H:%M:%S")

    # 数据匹配警告
    entry_bar = df_5m_for_window.iloc[(df_5m_for_window["datetime"] - trade["entry_time"]).abs().argsort()[:1]]
    exit_bar = df_5m_for_window.iloc[(df_5m_for_window["datetime"] - trade["exit_time"]).abs().argsort()[:1]]
    entry_in_range = entry_bar["low"].values[0] <= trade["entry_price"] <= entry_bar["high"].values[0]
    exit_in_range = exit_bar["low"].values[0] <= trade["exit_price"] <= exit_bar["high"].values[0]
    if not (entry_in_range and exit_in_range):
        st.warning("⚠️ 交易价格与历史 K 线不完全匹配，标注位置可能与真实成交价有偏差。")

    # K 线图
    st.subheader("K 线图")
    df_5m = load_klines("5min", start_str, end_str)
    df_15m = load_klines("15min", start_str, end_str)
    df_60m = load_klines("60min", start_str, end_str)

    chart_h = int(st.session_state.chart_height * 0.75)

    html_5m = render_chart(df_5m, trade, "5 分钟图", chart_h)
    components.html(html_5m, height=chart_h, scrolling=False)

    html_15m = render_chart(df_15m, trade, "15 分钟图", chart_h)
    components.html(html_15m, height=chart_h, scrolling=False)

    html_60m = render_chart(df_60m, trade, "60 分钟图", chart_h)
    components.html(html_60m, height=chart_h, scrolling=False)

    st.caption(f"时间窗口：{window_start} ~ {window_end}")

    # 交易数据
    st.divider()
    st.subheader("交易数据")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("方向", trade["direction"].upper())
    c2.metric("进场价", f"{trade['entry_price']:.2f}")
    c3.metric("出场价", f"{trade['exit_price']:.2f}")
    c4.metric("盈亏", f"${trade['pnl_usd']:.2f}")
    c5.metric("回报", f"{trade['return_pct']:.2f}%")

    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("持仓时长", f"{trade['duration_minutes']} 分钟")
    c7.metric("持仓 K 线", f"{trade['duration_bars']} 根")
    c8.metric("最大浮盈", f"${trade['mfe_usd']:.2f}")
    c9.metric("最大浮亏", f"${trade['mae_usd']:.2f}")
    c10.metric("时段", trade["session"])

    st.write(f"**进场信号：** {trade['entry_signal']}")
    st.write(f"**出场信号：** {trade['exit_signal']}")
    st.write(f"**进场时间：** {trade['entry_time']}")
    st.write(f"**出场时间：** {trade['exit_time']}")


# ───────────────────────────────────────────────
# 主入口
# ───────────────────────────────────────────────
def main():
    # session state 默认值
    if "page" not in st.session_state:
        st.session_state.page = "summary"
    if "selected_trade_id" not in st.session_state:
        st.session_state.selected_trade_id = 1
    if "chart_height" not in st.session_state:
        st.session_state.chart_height = 560
    if "bars_before" not in st.session_state:
        st.session_state.bars_before = 50
    if "bars_after" not in st.session_state:
        st.session_state.bars_after = 50

    trades = load_trades()
    sidebar(trades)

    if st.session_state.page == "summary":
        summary_page(trades)
    else:
        detail_page(trades)


if __name__ == "__main__":
    main()
