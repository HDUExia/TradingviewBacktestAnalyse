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

import base64
import io
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
SETTINGS_JSON = ROOT / "data" / "settings.json"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import parse_replay_trades  # noqa: E402
import prepare_mes_intraday as prep  # noqa: E402
from chart_data import fetch_and_store, symbol_name  # noqa: E402
import indicators  # noqa: E402
import markdown_io  # noqa: E402

st.set_page_config(page_title="MES 回放交易分析", layout="wide", initial_sidebar_state="expanded")

_rich_comment = components.declare_component(
    "rich_comment",
    path=str(ROOT / "components" / "rich_comment"),
)


_CSS = """
<style>
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1500px; }
.stButton > button {
  width: 100%;
  justify-content: center;
  border-radius: 6px;
  border: 1px solid #30363d;
  background: #1f2430;
  color: #e6e6e6;
  font-weight: 500;
  padding: 0.25rem 0.6rem;
  min-height: 0;
  transition: background .15s, box-shadow .15s;
}
.stButton > button:hover { background: #2a303c; box-shadow: 0 1px 2px rgba(0,0,0,.4); }
.stButton > button[kind="primary"] { background: #4c8bf5; color: #fff; border: none; }
.stButton > button[kind="primary"]:hover { background: #3a79e0; }
[data-testid="stColorPicker"] input { display: none !important; }
[data-testid="stColorPicker"] { min-width: 0; padding: 0; }
[data-testid="stVerticalBlockBorderWrapper"] {
  background: #161b26; border-radius: 12px; border: 1px solid #262d3a;
}
[data-testid="stExpander"] { border-radius: 8px; border: 1px solid #262d3a; background: #161b26; }
[data-testid="stMetric"] {
  background: #161b26; border-radius: 10px; border: 1px solid #262d3a; padding: 12px 14px;
}
h1, h2, h3 { letter-spacing: -0.01em; }
</style>
"""


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
def load_klines(freq: str, start_dt: str | None = None, end_dt: str | None = None) -> pd.DataFrame:
    """读取 data/csv_intraday/<freq>/ 下的行情 CSV，可选按时间窗口过滤。"""
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
    if start_dt is not None:
        df = df[df["datetime"] >= start_dt]
    if end_dt is not None:
        df = df[df["datetime"] <= end_dt]
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


def add_comment(trade_id: int, segments: list[dict]) -> None:
    comments = load_comments()
    comments.append(
        {
            "id": uuid.uuid4().hex,
            "trade_id": trade_id,
            "segments": segments,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    COMMENTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    COMMENTS_JSON.write_text(json.dumps(comments, ensure_ascii=False, indent=2), encoding="utf-8")


def load_settings() -> dict:
    if not SETTINGS_JSON.exists():
        return {}
    try:
        return json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings() -> None:
    SETTINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "ind_instances": st.session_state.get("ind_instances", []),
        "timezone": st.session_state.get("timezone", "UTC"),
        "chart_height": st.session_state.get("chart_height", 560),
    }
    SETTINGS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _process_comment_segments(segments: list[dict], trade_id: int) -> list[dict]:
    """把编辑器返回的 base64 图片落盘、替换为本地路径，并合并相邻文本段。"""
    out = []
    for seg in segments:
        if seg.get("type") == "image":
            src = seg.get("src", "")
            if src.startswith("data:"):
                meta, b64 = src.split(",", 1)
                ext = meta.split(";")[0].split("/")[-1] or "png"
                if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
                    ext = "png"
                UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
                dest = UPLOADS_DIR / f"c{trade_id}_{uuid.uuid4().hex}.{ext}"
                dest.write_bytes(base64.b64decode(b64))
                out.append({"type": "image", "path": str(dest)})
            else:
                out.append({"type": "image", "path": src})
        else:
            out.append({"type": "text", "text": seg.get("text", "")})

    merged = []
    for seg in out:
        if merged and merged[-1]["type"] == "text" and seg["type"] == "text":
            merged[-1]["text"] += seg["text"]
        else:
            merged.append(seg)
    return merged


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
    st.caption("先导入交易数据，再准备行情数据，即可开始复盘。")

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

    st.divider()

    # ── 交易数据 ──
    st.subheader("📄 交易数据")
    trade_mode = st.selectbox(
        "导入方式",
        ["TV 数据导入", "TBA 数据导入"],
        key="trade_mode",
        help="TV 数据导入：上传 TradingView 回放交易 CSV；TBA 数据导入：导入之前导出的 Markdown 报告。",
    )

    if trade_mode == "TV 数据导入":
        st.caption("上传 TradingView 导出的回放交易 CSV，自动解析成单笔交易。")
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
    else:
        st.caption("导入之前导出的 TBA Markdown 报告，反解析成「原始交易数据 + 评论」（K 线数据需单独准备）。")
        md_file = st.file_uploader("选择 .md 文件", type=["md", "markdown"], key="md_upload")
        if md_file is not None and st.button("导入报告", key="btn_md_import"):
            try:
                csv_text, comments = markdown_io.import_markdown(md_file.getvalue().decode("utf-8"), ROOT)
                if not csv_text:
                    st.error("未在文档中找到原始交易数据（缺少 TBA_TRADES 标记）。")
                else:
                    TRADES_CSV.parent.mkdir(parents=True, exist_ok=True)
                    TRADES_CSV.write_text(csv_text, encoding="utf-8")
                    COMMENTS_JSON.parent.mkdir(parents=True, exist_ok=True)
                    COMMENTS_JSON.write_text(json.dumps(comments, ensure_ascii=False, indent=2), encoding="utf-8")
                    st.cache_data.clear()
                    st.session_state.pop("trades_parse_msg", None)
                    n_trades = len(pd.read_csv(io.StringIO(csv_text)))
                    st.success(f"导入成功：{n_trades} 笔交易，{len(comments)} 条评论。")
            except Exception as exc:
                st.error(f"导入失败：{exc}")

    st.divider()

    # ── 行情数据 ──
    st.subheader("📈 行情数据")
    kline_mode = st.selectbox(
        "获取方式",
        ["自动拉取", "手动导入"],
        key="kline_mode",
        help="自动拉取：通过 TradingView MCP 按交易区间自动拉取；手动导入：上传本地 1 分钟行情 CSV。",
    )

    if kline_mode == "自动拉取":
        st.caption("根据交易记录自动判定「进场最早 ~ 出场最晚」的区间（前后各留 1 天），通过 MCP 拉取 5/15/60 分钟行情。")
        symbol = st.text_input("TradingView 品种", value="MES1!", key="auto_symbol")
        rng = trades_date_range(TRADES_CSV)
        if rng is None:
            st.warning("还没有交易数据，请先在上方导入交易数据。")
        else:
            start, end = rng
            st.info(f"自动判定的拉取区间：**{start} ~ {end}**（{(end - start).days} 天）")
        if st.button("🚀 开始拉取", type="primary", width="stretch", disabled=(rng is None)):
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
    else:
        st.caption("上传本地 1 分钟行情 CSV，重采样为 5/15/60 分钟。")
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


# ───────────────────────────────────────────────
# 侧边栏
# ───────────────────────────────────────────────
def _trade_table_sidebar(trades: pd.DataFrame | None):
    """左侧交易列表：点击按钮跳到对应交易详情。"""
    if trades is None or trades.empty:
        st.sidebar.caption("暂无交易")
        return
    st.sidebar.markdown("### 交易列表")

    current = int(st.session_state.get("selected_trade_id", trades.iloc[0]["trade_id"]))
    for _, row in trades.iterrows():
        tid = int(row["trade_id"])
        icon = "✅" if row["pnl_usd"] > 0 else "❌"
        direction_cn = "多" if row["direction"] == "long" else "空"
        sign = "+" if row["pnl_usd"] > 0 else ""
        label = f"{icon} #{tid} {direction_cn} {sign}${row['pnl_usd']:.2f}"
        btn_type = "primary" if tid == current else "secondary"
        if st.sidebar.button(label, key=f"trade_btn_{tid}", width="stretch", type=btn_type):
            st.session_state.selected_trade_id = tid
            st.session_state.page = "detail"
            st.rerun()


def _settings_ui():
    st.session_state.chart_height = st.slider(
        "图表高度", 300, 900, st.session_state.get("chart_height", 560), key="setting_height"
    )
    tz_options = {
        "UTC": "UTC",
        "America/New_York": "美东 ET",
        "Asia/Shanghai": "北京时间 CST",
    }
    st.session_state.timezone = st.selectbox(
        "时间轴时区",
        list(tz_options),
        index=list(tz_options).index(st.session_state.get("timezone", "UTC")),
        format_func=lambda t: tz_options[t],
        key="setting_tz",
    )


def _indicators_ui():
    st.session_state.setdefault("ind_instances", [])
    instances = st.session_state.ind_instances

    c1, c2 = st.columns([5, 2], vertical_alignment="center")
    with c1:
        new_type = st.selectbox(
            "指标类型",
            list(indicators.INDICATORS),
            format_func=lambda t: indicators.INDICATORS[t]["label"],
            label_visibility="collapsed",
            key="ind_new_type",
        )
    with c2:
        if st.button("添加", width="stretch", key="ind_add_btn"):
            used = {inst.get("color") for inst in instances}
            instances.append({
                "id": uuid.uuid4().hex,
                "type": new_type,
                "params": dict(indicators.INDICATORS[new_type]["params"]),
                "color": indicators.next_color(used),
            })
            st.rerun()

    if not instances:
        st.caption("尚未添加指标。")

    for inst in instances:
        entry = indicators.INDICATORS.get(inst["type"])
        if not entry:
            continue
        with st.container(border=True):
            ch, ccol, cd = st.columns([4, 1, 2], vertical_alignment="center")
            ch.markdown(f"**{entry['label']}**")
            with ccol:
                inst["color"] = st.color_picker(
                    "颜色",
                    value=inst.get("color", "#3b82f6"),
                    key=f"indcolor_{inst['id']}",
                    label_visibility="collapsed",
                )
            if cd.button("删除", key=f"ind_del_{inst['id']}", width="stretch"):
                st.session_state.ind_instances = [x for x in instances if x["id"] != inst["id"]]
                st.rerun()
            params = {}
            for pname, pval in inst["params"].items():
                if pname in ("length", "fast", "slow", "signal"):
                    params[pname] = int(st.number_input(pname, value=int(pval), min_value=1, step=1, key=f"indparam_{inst['id']}_{pname}"))
                else:
                    params[pname] = st.number_input(pname, value=float(pval), min_value=0.1, step=0.1, key=f"indparam_{inst['id']}_{pname}")
            inst["params"] = params


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
    st.dataframe(display_df, width="stretch")

    st.divider()
    st.subheader("📦 导出 Markdown 报告")
    st.caption("报告包含原始交易数据 + 评论（K 线数据不包含，需单独保留）。")
    report = markdown_io.export_markdown(TRADES_CSV, load_comments(), ROOT)
    st.download_button(
        "下载 report.md",
        data=report,
        file_name="tba_report.md",
        mime="text/markdown",
        width="stretch",
    )


# ───────────────────────────────────────────────
# 交易详情页
# ───────────────────────────────────────────────
def detail_page(trades: pd.DataFrame):
    ids = trades["trade_id"].tolist()
    cur = int(st.session_state.get("selected_trade_id", ids[0]))
    if cur not in ids:
        cur = int(ids[0])
    idx = ids.index(cur)

    selected_id = int(st.session_state.selected_trade_id)
    trade = trades[trades["trade_id"] == selected_id].iloc[0]

    header_cols = st.columns([5, 1, 1])
    header_cols[0].header(f"交易 #{selected_id} 详情")
    with header_cols[1]:
        if st.button("◀ 上一笔", width="stretch", disabled=(idx == 0)):
            st.session_state.selected_trade_id = int(ids[idx - 1])
            st.rerun()
    with header_cols[2]:
        if st.button("下一笔 ▶", width="stretch", disabled=(idx >= len(ids) - 1)):
            st.session_state.selected_trade_id = int(ids[idx + 1])
            st.rerun()

    # 加载全量 K 线（拖动即可查看更多，无需设置前后根数）
    df_5m = load_klines("5min")
    if df_5m.empty:
        st.warning("⚠️ 该品种没有本地 K 线数据。")
        st.markdown("到「🛠 数据」→「🚀 一键分析」或用 QuantData 从 TradingView 拉取（历史区间走回放模式）：")
        st.code(
            f"python3 scripts/fetch_tv_data.py --symbol MES1! --timeframe 5m "
            f"--start {trade['entry_time'].date()} --end {trade['exit_time'].date()}"
        )
        st.markdown(
            "或者用本地 1 分钟行情生成："
            "`python3 scripts/prepare_mes_intraday.py --input <1分钟行情.csv> --symbol MES`"
        )
        return

    # 数据匹配警告
    entry_bar = df_5m.iloc[(df_5m["datetime"] - trade["entry_time"]).abs().argsort()[:1]]
    exit_bar = df_5m.iloc[(df_5m["datetime"] - trade["exit_time"]).abs().argsort()[:1]]
    entry_in_range = entry_bar["low"].values[0] <= trade["entry_price"] <= entry_bar["high"].values[0]
    exit_in_range = exit_bar["low"].values[0] <= trade["exit_price"] <= exit_bar["high"].values[0]
    if not (entry_in_range and exit_in_range):
        st.warning("⚠️ 交易价格与历史 K 线不完全匹配，标注位置可能与真实成交价有偏差。")

    # K 线图
    st.subheader("K 线图")
    st.caption("拖动图表查看 K 线：向左拖看出场后，向右拖看进场前；滚轮缩放。")
    df_15m = load_klines("15min")
    df_60m = load_klines("60min")

    chart_h = int(st.session_state.chart_height * 0.75)
    tz = st.session_state.get("timezone", "UTC")
    ind_instances = st.session_state.get("ind_instances", [])

    for freq_df, label in [(df_5m, "5 分钟图"), (df_15m, "15 分钟图"), (df_60m, "60 分钟图")]:
        if freq_df.empty:
            st.caption(f"{label}：暂无数据")
            continue
        overlays, panes = indicators.compute_indicators(freq_df, ind_instances) if ind_instances else ([], [])
        html = render_chart(freq_df, trade, label, chart_h, tz, overlays, panes)
        components.html(html, height=chart_h + 120 * len(panes), scrolling=False)

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
            if "segments" in c:
                for seg in c["segments"]:
                    if seg.get("type") == "image":
                        p = Path(seg.get("path", ""))
                        if p.exists():
                            st.image(str(p), width=460)
                    else:
                        st.markdown(seg.get("text", ""))
            else:
                st.write(c.get("text", ""))
                img_path = c.get("image_path")
                if img_path and Path(img_path).exists():
                    st.image(str(img_path), width=460)

    # 富文本评论编辑器（支持粘贴图片、图文混排）
    raw = _rich_comment(key=f"rich_comment_{selected_id}", default=None)
    last_key = f"last_rich_comment_{selected_id}"
    if raw and st.session_state.get(last_key) != raw:
        st.session_state[last_key] = raw
        try:
            segs = json.loads(raw)
            processed = _process_comment_segments(segs, int(selected_id))
            if processed:
                add_comment(int(selected_id), processed)
        except Exception as exc:
            st.error(f"发布评论失败：{exc}")
        st.rerun()


# ───────────────────────────────────────────────
# 主入口
# ───────────────────────────────────────────────
def main():
    # session state 默认值
    settings = load_settings()
    if "page" not in st.session_state:
        st.session_state.page = "summary"
    if "selected_trade_id" not in st.session_state:
        st.session_state.selected_trade_id = 1
    if "chart_height" not in st.session_state:
        st.session_state.chart_height = settings.get("chart_height", 560)
    if "timezone" not in st.session_state:
        st.session_state.timezone = settings.get("timezone", "UTC")
    if "ind_instances" not in st.session_state:
        st.session_state.ind_instances = settings.get("ind_instances", [])

    # 注入主题 CSS；非交易页隐藏侧边栏
    st.markdown(_CSS, unsafe_allow_html=True)
    if st.session_state.page != "detail":
        st.markdown("<style>[data-testid='stSidebar'] { display: none; }</style>", unsafe_allow_html=True)

    # 顶部应用栏
    bar = st.columns([4, 1, 1, 1, 1, 1], vertical_alignment="center")
    with bar[0]:
        st.markdown("### 📈 复盘分析")
    for i, (page, label) in enumerate([("summary", "总结"), ("detail", "交易"), ("data", "数据")]):
        with bar[1 + i]:
            if st.button(label, width="stretch", type="primary" if st.session_state.page == page else "secondary"):
                st.session_state.page = page
                st.rerun()
    with bar[4]:
        with st.popover("设置", width="stretch"):
            _settings_ui()
    with bar[5]:
        with st.popover("指标", width="stretch"):
            _indicators_ui()
    st.divider()

    trades = load_trades() if TRADES_CSV.exists() else None
    if st.session_state.page == "detail":
        _trade_table_sidebar(trades)

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

    save_settings()


if __name__ == "__main__":
    main()
