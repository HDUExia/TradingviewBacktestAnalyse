"""TBA 与 QuantData(QD) 的桥接层。

提供两个能力：
1. write_qlib：把 OHLCV DataFrame 写成 Qlib 二进制（供复盘面板加载）。
2. fetch_tradingview_bars：通过 QD 的 TradingView provider 从 TV 拉取 K 线。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
QD_SRC = ROOT / "vendor" / "quantdata" / "src"

# TradingView 周期 -> TBA 的周期目录名
TIMEFRAME_TO_FREQ = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "60m": "60min",
    "1h": "60min",
    "1d": "day",
    "D": "day",
}


def write_qlib(df: pd.DataFrame, freq: str, symbol: str, qlib_base: Path) -> None:
    """把 date,symbol,open,high,low,close,volume 写成 Qlib 目录结构。"""
    qlib_dir = qlib_base / f"futures_{freq}"
    qlib_dir.mkdir(parents=True, exist_ok=True)

    calendar = df["date"].dt.strftime("%Y-%m-%d %H:%M:%S").sort_values().unique()
    cal_path = qlib_dir / "calendars" / f"{freq}.txt"
    cal_path.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(cal_path, calendar, fmt="%s")

    inst_path = qlib_dir / "instruments" / "all.txt"
    inst_path.parent.mkdir(parents=True, exist_ok=True)
    start = df["date"].min().strftime("%Y-%m-%d %H:%M:%S")
    end = df["date"].max().strftime("%Y-%m-%d %H:%M:%S")
    inst_path.write_text(f"{symbol}\t{start}\t{end}\n", encoding="utf-8")

    feat_dir = qlib_dir / "features" / symbol.lower()
    feat_dir.mkdir(parents=True, exist_ok=True)
    date_to_idx = {d: i for i, d in enumerate(calendar)}

    fields = ["open", "high", "low", "close", "volume"]
    df_sorted = df.sort_values("date")
    for field in fields:
        aligned = np.full(len(calendar), np.nan, dtype=np.float32)
        for _, row in df_sorted.iterrows():
            idx = date_to_idx[row["date"].strftime("%Y-%m-%d %H:%M:%S")]
            aligned[idx] = float(row[field])

        valid_mask = ~np.isnan(aligned)
        start_idx = int(np.argmax(valid_mask))
        data = aligned[start_idx:]
        bin_path = feat_dir / f"{field}.{freq}.bin"
        with bin_path.open("wb") as fp:
            np.hstack([start_idx, data]).astype("<f").tofile(fp)

    print(f"  Qlib {freq}: {qlib_dir}")


def fetch_tradingview_bars(
    symbol: str,
    timeframe: str,
    start: date,
    end: date,
    count: int = 300,
) -> pd.DataFrame:
    """通过 QD 的 TradingView provider 拉取 K 线，返回面板格式的 DataFrame。

    symbol 使用 TradingView 代码（如 MES1!），返回的 symbol 列会去掉 1!/# 后缀。
    注意：TradingView 只提供最近 ~2 天的 intraday 数据，历史区间会返回空。
    """
    if str(QD_SRC) not in sys.path:
        sys.path.insert(0, str(QD_SRC))

    from quantdata.core.models import FetchRequest
    from quantdata.providers.tradingview import TradingViewProvider

    qlib_symbol = symbol.replace("1!", "").replace("#", "").upper()

    provider = TradingViewProvider()
    request = FetchRequest((symbol,), start, end, timeframe=timeframe, options={"count": count})
    records = list(provider.fetch_bars(request))

    columns = ["date", "symbol", "open", "high", "low", "close", "volume"]
    if not records:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(None)
    df["symbol"] = qlib_symbol
    return df[columns].sort_values("date").reset_index(drop=True)
