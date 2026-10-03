"""指标插件库。

每个指标是一个函数：接收行情 DataFrame 和参数，返回一个或多个 series。
新增指标只需写一个函数，并在 ``INDICATORS`` 注册表里登记即可。

series 结构：
    key   唯一键
    name  显示名
    pane  "main" 或子图名
    kind  "line" | "histogram"
    values 与 df 行对齐的数值列表（含 None）
    color  颜色
    width  线宽
    style  solid | dashed | dotted
    colors 可选，histogram 逐点颜色
"""
import pandas as pd


def _series(key, name, values, pane="main", kind="line", color="#3b82f6", width=2, style="solid", colors=None):
    out = {
        "key": key,
        "name": name,
        "pane": pane,
        "kind": kind,
        "values": [None if pd.isna(v) else float(v) for v in values],
        "color": color,
        "width": width,
        "style": style,
    }
    if colors is not None:
        out["colors"] = colors
    return out


def sma(df, length=20, source="close", color="#f59e0b"):
    v = df[source].rolling(length).mean()
    return [_series(f"sma{length}", f"MA{length}", v, color=color)]


def ema(df, length=20, source="close", color="#3b82f6"):
    v = df[source].ewm(span=length, adjust=False).mean()
    return [_series(f"ema{length}", f"EMA{length}", v, color=color)]


def boll(df, length=20, mult=2.0, source="close"):
    mid = df[source].rolling(length).mean()
    std = df[source].rolling(length).std()
    return [
        _series("boll_upper", "BOLL上轨", mid + mult * std, color="#a78bfa"),
        _series("boll_mid", "BOLL中轨", mid, color="#e5e7eb", width=1),
        _series("boll_lower", "BOLL下轨", mid - mult * std, color="#a78bfa"),
    ]


def rsi(df, length=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    v = 100 - 100 / (1 + gain / loss.replace(0, 1e-12))
    v = v.where(delta.notna())
    return [_series("rsi", f"RSI{length}", v, pane="rsi", color="#a78bfa")]


def macd(df, fast=12, slow=26, signal=9):
    ef = df["close"].ewm(span=fast, adjust=False).mean()
    es = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ef - es
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    colors = ["#26a69a" if h >= 0 else "#ef5350" for h in hist]
    return [
        _series("macd", "MACD", macd_line, pane="macd", color="#3b82f6"),
        _series("macd_signal", "Signal", signal_line, pane="macd", color="#f59e0b"),
        _series("macd_hist", "Hist", hist, pane="macd", kind="histogram", color="#34d399", colors=colors),
    ]


def atr(df, length=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    v = tr.ewm(alpha=1 / length, adjust=False).mean()
    return [_series("atr", f"ATR{length}", v, pane="atr", color="#f97316")]


def volume_ma(df, length=20):
    v = df["volume"].rolling(length).mean()
    return [_series("vol_ma", f"VOL MA{length}", v, pane="main", color="#f59e0b", width=1)]


INDICATORS = {
    "sma": {"label": "均线 MA", "compute": sma, "params": {"length": 20}},
    "ema": {"label": "指数均线 EMA", "compute": ema, "params": {"length": 20}},
    "boll": {"label": "布林带 BOLL", "compute": boll, "params": {"length": 20, "mult": 2.0}},
    "rsi": {"label": "RSI", "compute": rsi, "params": {"length": 14}},
    "macd": {"label": "MACD", "compute": macd, "params": {"fast": 12, "slow": 26, "signal": 9}},
    "atr": {"label": "ATR", "compute": atr, "params": {"length": 14}},
    "vol_ma": {"label": "成交量均线", "compute": volume_ma, "params": {"length": 20}},
}


def compute_indicators(df, enabled):
    """enabled: {indicator_id: params}. 返回 (overlays, panes)。"""
    overlays = []
    pane_map = {}
    for iid, params in enabled.items():
        entry = INDICATORS.get(iid)
        if not entry:
            continue
        merged = {**entry["params"], **(params or {})}
        for s in entry["compute"](df, **merged):
            if s["pane"] == "main":
                overlays.append(s)
            else:
                pane_map.setdefault(s["pane"], []).append(s)

    panes = [
        {"key": k, "name": " · ".join(x["name"] for x in v), "series": v}
        for k, v in pane_map.items()
    ]
    return overlays, panes
