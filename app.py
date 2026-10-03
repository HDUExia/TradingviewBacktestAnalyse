"""
MES 回放交易分析面板 v3

- 左侧边栏：导航（总结 / 交易 / 数据管理）、交易列表、设置齿轮
- 总结页：统计数据、权益曲线、盈亏分布
- 交易详情页：K 线图 + 交易数据
- 数据管理页：上传回放交易 CSV、上传 1 分钟行情、或从 TradingView 拉取

运行方式：
    streamlit run app.py
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from chart_lwc import render_chart

ROOT = Path(__file__).resolve().parent
TRADES_CSV = ROOT / "data" / "replay_trades_parsed.csv"
CSV_DIR = ROOT / "data" / "csv_intraday"
COMMENTS_JSON = ROOT / "data" / "comments.json"
UPLOADS_DIR = ROOT / "data" / "uploads"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import parse_replay_trades  # noqa: E402
import prepare_mes_intraday as prep  # noqa: E402
from chart_data import fetch_and_store, symbol_name  # noqa: E402

st.set_page_config(page_title="MES 回放交易分析", layout="wide", initial_sidebar_state="expanded")


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
    """读取 data/csv_intraday/<freq>/ 下的行情 CSV，按时间窗口过滤。"""
    columns = ["symbol", "datetime", "open", "high", "low", "close", "volume"]
    freq_dir = CSV_DIR / freq
    if not freq_dir.exists():
        return pd.DataFrame(columns=columns)

    frames = []
    for csv_path in sorted(freq_dir.glob("*.csv")):
        part = pd.read_csv(csv_path)
        if "date" not in part.columns:
            continue
        part["datetime"] = pd.to_datetime(part["date"])
        frames.append(part)
    if not frames:
        return pd.DataFrame(columns=columns)

    df = pd.concat(frames, ignore_index=True)
    df = df[["symbol", "datetime", "open", "high", "low", "close", "volume"]]
    df = df[(df["datetime"] >= start_dt) & (df["datetime"] <= end_dt)]
    return df.sort_values("datetime").reset_index(drop=True)


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


def save_upload(uploaded, name: str) -> Path:
    """把 Streamlit 上传的文件保存到 data/ 目录，返回路径。"""
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    path = ROOT / "data" / name
    path.write_bytes(uploaded.getvalue())
    return path


def load_comments() -> list[dict]:
    if not COMMENTS_JSON.exists():
        return []
    try:
        return json.loads(COMMENTS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def add_comment(trade_id: int, text: str, image_path: str | None = None) -> None:
    comments = load_comments()
    comments.append(
        {
            "id": uuid.uuid4().hex,
            "trade_id": trade_id,
            "text": text,
            "image_path": image_path,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    COMMENTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    COMMENTS_JSON.write_text(json.dumps(comments, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_intraday(input_path: Path, symbol: str, csv_dir: Path) -> None:
    """1 分钟 CSV → 5/15/60 分钟 CSV。"""
    df_1m = prep.load_1min(input_path, symbol)
    for freq, rule in prep.FREQS.items():
        df_freq = prep.resample(df_1m, rule, symbol)
        prep.write_csv(df_freq, freq, symbol, csv_dir)


def trades_date_range(trades_csv: Path) -> tuple[date, date] | None:
    """从交易记录里自动判定需要拉取的日期区间（进出场前后各留 1 天余量）。"""
    if not trades_csv.exists():
        return None
    df = pd.read_csv(trades_csv)
    if df.empty:
        return None
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    start = (df["entry_time"].min() - pd.Timedelta(days=1)).date()
    end = (df["exit_time"].max() + pd.Timedelta(days=1)).date()
    return start, end


def auto_fetch_klines(symbol: str, start: date, end: date) -> int:
    """拉取 5 分钟数据，再本地重采样出 15/60 分钟 CSV，返回 5 分钟根数。"""
    n = fetch_and_store(symbol, "5m", start, end, CSV_DIR)
    if n == 0:
        return 0

    name = symbol_name(symbol)
    csv5 = CSV_DIR / "5min" / f"{name}.csv"
    df5 = pd.read_csv(csv5)
    df5["date"] = pd.to_datetime(df5["date"])
    df5 = df5.set_index("date").sort_index()

    for freq, rule in [("15min", "15min"), ("60min", "60min")]:
        df_freq = prep.resample(df5, rule, name)
        prep.write_csv(df_freq, freq, name, CSV_DIR)
    return n


# ───────────────────────────────────────────────
# 数据管理页
# ───────────────────────────────────────────────
def _on_trades_upload() -> None:
    """上传回放交易 CSV 后自动解析并持久化。"""
    up = st.session_state.get("trades_upload")
    if up is None:
        return
    path = save_upload(up, "uploaded_trades.csv")
    try:
        n = parse_replay_trades.parse(path, TRADES_CSV)
        st.cache_data.clear()
        st.session_state["trades_parse_msg"] = ("success", f"已解析 {n} 笔交易并保存（刷新后仍在）。")
    except Exception as exc:
        st.session_state["trades_parse_msg"] = ("error", f"解析失败：{exc}")


def data_page():
    st.header("🛠 数据管理")
    st.caption("上传交易记录后，可一键自动分析并拉取对应区间的行情。")

    # 当前数据状态
    s1, s2 = st.columns(2)
    if TRADES_CSV.exists():
        try:
            s1.success(f"交易记录：已加载 {len(load_trades())} 笔")
        except Exception:
            s1.warning("交易记录：文件存在但读取失败")
    else:
        s1.warning("交易记录：无")
    if (CSV_DIR / "5min").exists():
        s2.success("行情数据：已有 5/15/60 分钟")
    else:
        s2.warning("行情数据：无")

    tab_trades, tab_klines, tab_auto = st.tabs(["📄 回放交易", "📈 行情 K 线", "🚀 一键分析"])

    with tab_trades:
        st.subheader("上传 TradingView 回放交易 CSV（自动解析）")
        st.caption(
            "列名需包含 `日期和时间、类型、交易编号、信号、价格 USD、大小（数量）、"
            "净损益 USD、回报 %、手续费 USD、有利波动 USD、有利波动 %、不利波动 USD、"
            "不利波动 %、持续时间（K线）、累计损益 USD`。可参考 `sample_data/sample_trades.csv`。"
        )
        st.file_uploader("选择 CSV 文件", type=["csv"], key="trades_upload", on_change=_on_trades_upload)
        msg = st.session_state.get("trades_parse_msg")
        if msg:
            kind, text = msg
            (st.success if kind == "success" else st.error)(text)
        st.caption("解析后会保存到 `data/replay_trades_parsed.csv`，刷新页面不会丢失。")

    with tab_klines:
        st.subheader("方式一：上传 1 分钟行情 CSV")
        st.caption(
            "列名需包含 `DateTime, Open, High, Low, Close, Volume`。"
            "可参考 `sample_data/sample_1min.csv`。"
        )
        up1 = st.file_uploader("选择 1 分钟 CSV", type=["csv"], key="kline_upload")
        if up1 is not None and st.button("生成 5/15/60 分钟数据", key="btn_prep"):
            path = save_upload(up1, "uploaded_1min.csv")
            try:
                prepare_intraday(path, "MES", CSV_DIR)
                st.cache_data.clear()
                st.success("已生成 5/15/60 分钟行情数据，去「交易」页查看。")
            except Exception as exc:
                st.error(f"生成失败：{exc}")

        st.divider()
        st.subheader("方式二：从 TradingView 拉取（通过 QuantData）")
        st.caption("需要本机运行 TradingView Desktop + TradingView MCP（tv CLI）。历史 intraday 走回放模式，长区间会慢一些。")
        with st.form("tv_fetch_form"):
            c1, c2 = st.columns(2)
            symbol = c1.text_input("TradingView 品种", value="MES1!")
            timeframe = c2.selectbox("周期", ["5m", "15m", "60m", "1d"])
            c3, c4 = st.columns(2)
            start = c3.date_input("开始日期", value=date.today() - timedelta(days=7))
            end = c4.date_input("结束日期", value=date.today())
            submitted = st.form_submit_button("拉取并生成行情")
        if submitted:
            with st.spinner("正在从 TradingView 拉取…"):
                try:
                    n = fetch_and_store(symbol, timeframe, start, end, CSV_DIR)
                    st.cache_data.clear()
                    if n:
                        st.success(f"已拉取 {n} 根 {timeframe} K 线并生成行情数据。")
                    else:
                        st.warning("没拉到数据：历史 intraday 可能不在可用范围。")
                except Exception as exc:
                    st.error(f"拉取失败：{exc}")

    with tab_auto:
        st.subheader("自动分析交易记录并拉取行情")
        st.caption(
            "软件会读取交易记录，自动判定「进场最早 ~ 出场最晚」的时间区间"
            "（前后各留 1 天），然后通过 MCP 拉取对应的 5/15/60 分钟行情。"
        )

        symbol = st.text_input("TradingView 品种", value="MES1!", key="auto_symbol")

        rng = trades_date_range(TRADES_CSV)
        if rng is None:
            st.warning("还没有交易数据，请先在「📄 回放交易」上传。")
        else:
            start, end = rng
            st.info(f"自动判定的拉取区间：**{start} ~ {end}**（{(end - start).days} 天）")

        if st.button("🚀 开始分析并拉取", type="primary", use_container_width=True, disabled=(rng is None)):
            start, end = rng
            with st.spinner(f"正在拉取 {symbol} {start} ~ {end} 的 5 分钟数据（历史区间走回放模式，可能较慢）…"):
                try:
                    n = auto_fetch_klines(symbol, start, end)
                    st.cache_data.clear()
                    if n:
                        st.success(f"完成：拉取 {n} 根 5 分钟 K 线，并已生成 15/60 分钟数据。去「📈 交易」页查看。")
                    else:
                        st.error("拉取失败：没拿到数据，请确认 TradingView Desktop 已运行、品种正确。")
                except Exception as exc:
                    st.error(f"拉取失败：{exc}")


# ───────────────────────────────────────────────
# 侧边栏
# ───────────────────────────────────────────────
def sidebar(trades: pd.DataFrame | None):
    st.sidebar.title("📈 MES 复盘")

    # 页面导航
    st.sidebar.markdown("### 页面")
    nav_cols = st.sidebar.columns(3)
    if nav_cols[0].button("📊 总结", use_container_width=True, type=("primary" if st.session_state.page == "summary" else "secondary")):
        st.session_state.page = "summary"
        st.rerun()
    if nav_cols[1].button("📈 交易", use_container_width=True, type=("primary" if st.session_state.page == "detail" else "secondary")):
        st.session_state.page = "detail"
        st.rerun()
    if nav_cols[2].button("🛠 数据", use_container_width=True, type=("primary" if st.session_state.page == "data" else "secondary")):
        st.session_state.page = "data"
        st.rerun()

    st.sidebar.divider()

    # 交易列表（仅在交易页显示完整列表，总结页可隐藏）
    if st.session_state.page == "detail" and trades is not None and not trades.empty:
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
            "`python3 scripts/prepare_mes_intraday.py --input <1分钟行情.csv> --symbol MES`"
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

    # 复盘评论
    st.divider()
    st.subheader("📝 复盘评论")

    trade_comments = [c for c in load_comments() if c.get("trade_id") == selected_id]
    if not trade_comments:
        st.caption("还没有评论，写下你的复盘心得吧。")
    for c in reversed(trade_comments):
        with st.container(border=True):
            st.markdown(f"*{c.get('created_at', '')}*")
            st.write(c.get("text", ""))
            img_path = c.get("image_path")
            if img_path and Path(img_path).exists():
                st.image(str(img_path), width=440)

    with st.form("comment_form"):
        text = st.text_area("写评论…", key="comment_text", placeholder="例如：这里进场偏早，应该等二次确认…")
        img_file = st.file_uploader("贴图（可选）", type=["png", "jpg", "jpeg", "gif", "webp"], key="comment_img")
        submitted = st.form_submit_button("发布评论")
    if submitted:
        if not text.strip():
            st.warning("评论内容不能为空。")
        else:
            image_path = None
            if img_file is not None:
                UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
                ext = Path(img_file.name).suffix or ".png"
                dest = UPLOADS_DIR / f"trade{selected_id}_{uuid.uuid4().hex}{ext}"
                dest.write_bytes(img_file.getvalue())
                image_path = str(dest)
            add_comment(int(selected_id), text.strip(), image_path)
            st.rerun()


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

    trades = load_trades() if TRADES_CSV.exists() else None
    sidebar(trades)

    if st.session_state.page == "data":
        data_page()
    elif st.session_state.page == "detail":
        if trades is None or trades.empty:
            st.info("还没有交易数据，请先在「🛠 数据」页上传回放交易 CSV。")
            data_page()
        else:
            detail_page(trades)
    else:
        if trades is None or trades.empty:
            st.info("还没有交易数据，请先在「🛠 数据」页上传回放交易 CSV。")
            data_page()
        else:
            summary_page(trades)


if __name__ == "__main__":
    main()
