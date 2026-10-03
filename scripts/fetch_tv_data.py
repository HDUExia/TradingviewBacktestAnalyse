"""通过 QuantData(QD) 从 TradingView 拉取 K 线，合并进本地 CSV。

用法示例：
    python3 scripts/fetch_tv_data.py --symbol MES1! --timeframe 5m \
        --start 2026-10-01 --end 2026-10-02

"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chart_data import fetch_and_store

CSV_DIR = ROOT / "data" / "csv_intraday"


def main() -> None:
    parser = argparse.ArgumentParser(description="用 QuantData 从 TradingView 拉取 K 线")
    parser.add_argument("--symbol", required=True, help="TradingView 代码，如 MES1!")
    parser.add_argument("--timeframe", required=True, help="5m / 15m / 60m / 1d")
    parser.add_argument("--start", required=True, type=date.fromisoformat, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=date.fromisoformat, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--count", type=int, default=300, help="拉取根数（最大 300）")
    args = parser.parse_args()

    n = fetch_and_store(
        args.symbol,
        args.timeframe,
        args.start,
        args.end,
        CSV_DIR,
        args.count,
    )
    print(f"[OK] 拉取到 {n} 根 K 线")
    if n == 0:
        print("[WARN] 没有拉到数据，请确认 TradingView Desktop 已运行、品种和日期正确。")


if __name__ == "__main__":
    main()
