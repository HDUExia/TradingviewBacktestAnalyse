"""
读取 1 分钟 CSV，重采样为 5m/15m/60m 的 CSV。

用法示例：
    python scripts/prepare_mes_intraday.py --input "@MES#C_1min_20260611.csv" --symbol MES
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chart_data import fill_session_gaps  # noqa: E402

DEFAULT_INPUT = ROOT / "@MES#C_1min_20260611.csv"
DEFAULT_SYMBOL = "MES"
DEFAULT_CSV_DIR = ROOT / "data" / "csv_intraday"
FREQS = {
    "5min": "5min",
    "15min": "15min",
    "60min": "60min",
}


def load_1min(input_path: Path, symbol: str) -> pd.DataFrame:
    print(f"Loading 1min data from {input_path} ...")
    df = pd.read_csv(input_path)
    df = df.rename(columns={
        "DateTime": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df["symbol"] = symbol
    return df[["symbol", "open", "high", "low", "close", "volume"]]


def resample(df: pd.DataFrame, rule: str, symbol: str) -> pd.DataFrame:
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    res = df.resample(rule).agg(agg)
    res = res.dropna(subset=["open", "high", "low", "close"])
    res["symbol"] = symbol
    res = res.reset_index()
    res = res[["date", "symbol", "open", "high", "low", "close", "volume"]]
    return res


def write_csv(df: pd.DataFrame, freq: str, symbol: str, csv_dir: Path):
    out_dir = csv_dir / freq
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{symbol}.csv"
    fill_session_gaps(df).to_csv(out, index=False)
    print(f"  {freq}: {len(df)} rows -> {out}")
    print(f"      range: {df['date'].min()} ~ {df['date'].max()}")


def main():
    parser = argparse.ArgumentParser(description="1 分钟 CSV → 5/15/60 分钟 CSV")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="1 分钟 CSV 路径")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="symbol / 文件名前缀")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR, help="CSV 输出目录")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"[ERROR] Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    df_1m = load_1min(args.input, args.symbol)
    print(f"Loaded {len(df_1m)} 1m bars")

    for freq, rule in FREQS.items():
        print(f"\nProcessing {freq} ...")
        df_freq = resample(df_1m, rule, args.symbol)
        write_csv(df_freq, freq, args.symbol, args.csv_dir)

    print("\nDone. 5/15/60 分钟 CSV ready.")


if __name__ == "__main__":
    main()
