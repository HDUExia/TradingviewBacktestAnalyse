"""通过 QuantData(QD) 从 TradingView 拉取 K 线，合并进本地 CSV 并重建 Qlib。

用法示例：
    python3 scripts/fetch_tv_data.py --symbol MES1! --timeframe 5m \
        --start 2026-10-01 --end 2026-10-02

注意：TradingView 只提供最近 ~2 天的 intraday 数据，历史区间拉不到。
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chart_data import TIMEFRAME_TO_FREQ, fetch_tradingview_bars, write_qlib

CSV_DIR = ROOT / "data" / "csv_intraday"
QLIB_BASE = ROOT / "data" / "qlib_data"


def main() -> None:
    parser = argparse.ArgumentParser(description="用 QuantData 从 TradingView 拉取 K 线")
    parser.add_argument("--symbol", required=True, help="TradingView 代码，如 MES1!")
    parser.add_argument("--timeframe", required=True, help="5m / 15m / 60m / 1d")
    parser.add_argument("--start", required=True, type=date.fromisoformat, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=date.fromisoformat, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--count", type=int, default=300, help="拉取根数（最大 300）")
    args = parser.parse_args()

    freq = TIMEFRAME_TO_FREQ.get(args.timeframe, args.timeframe + "min")
    qlib_symbol = args.symbol.replace("1!", "").replace("#", "").upper()

    df = fetch_tradingview_bars(args.symbol, args.timeframe, args.start, args.end, args.count)
    print(f"[OK] 拉取到 {len(df)} 根 {freq} K 线（symbol={qlib_symbol}）")

    if df.empty:
        print("[WARN] 没有拉到数据：TradingView 只提供最近 ~2 天的 intraday 数据。")
        return

    out_dir = CSV_DIR / freq
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{qlib_symbol}.csv"

    if csv_path.exists():
        old = pd.read_csv(csv_path)
        old["date"] = pd.to_datetime(old["date"])
        merged = pd.concat([old, df], ignore_index=True)
    else:
        merged = df
    merged = merged.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    merged.to_csv(csv_path, index=False)
    print(f"[OK] CSV 已合并 -> {csv_path}（共 {len(merged)} 行）")

    write_qlib(merged, freq, qlib_symbol, QLIB_BASE)


if __name__ == "__main__":
    main()
