"""TBA 与 QuantData(QD) 的桥接层：通过 QD 的 TradingView provider 拉取 K 线。"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

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


def symbol_name(symbol: str) -> str:
    """TradingView 代码（如 MES1!）-> 本地短符号（MES）。"""
    return symbol.replace("1!", "").replace("#", "").upper()


def fetch_tradingview_bars(
    symbol: str,
    timeframe: str,
    start: date,
    end: date,
    count: int = 300,
) -> pd.DataFrame:
    """通过 QD 的 TradingView provider 拉取 K 线，返回面板格式的 DataFrame。"""
    if str(QD_SRC) not in sys.path:
        sys.path.insert(0, str(QD_SRC))

    from quantdata.core.models import FetchRequest
    from quantdata.providers.tradingview import TradingViewProvider

    name = symbol_name(symbol)
    provider = TradingViewProvider()
    request = FetchRequest((symbol,), start, end, timeframe=timeframe, options={"count": count})
    records = list(provider.fetch_bars(request))

    columns = ["date", "symbol", "open", "high", "low", "close", "volume"]
    if not records:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(None)
    df["symbol"] = name
    return df[columns].sort_values("date").reset_index(drop=True)


def fetch_and_store(
    symbol: str,
    timeframe: str,
    start: date,
    end: date,
    csv_dir: Path,
    count: int = 300,
) -> int:
    """从 TradingView 拉取 K 线，合并进本地 CSV，返回新增根数。"""
    freq = TIMEFRAME_TO_FREQ.get(timeframe, timeframe + "min")
    name = symbol_name(symbol)

    df = fetch_tradingview_bars(symbol, timeframe, start, end, count)
    if df.empty:
        return 0

    out_dir = csv_dir / freq
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{name}.csv"
    if csv_path.exists():
        old = pd.read_csv(csv_path)
        old["date"] = pd.to_datetime(old["date"])
        merged = pd.concat([old, df], ignore_index=True)
    else:
        merged = df
    merged = merged.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    merged.to_csv(csv_path, index=False)
    return len(df)
