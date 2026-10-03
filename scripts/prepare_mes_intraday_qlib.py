"""
读取 1 分钟 CSV，重采样为 5m/15m/60m，并转成 Qlib 二进制格式。

用法示例：
    python scripts/prepare_mes_intraday_qlib.py --input "@MES#C_1min_20260611.csv" --symbol MES
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "@MES#C_1min_20260611.csv"
DEFAULT_SYMBOL = "MES"
DEFAULT_CSV_DIR = ROOT / "data" / "csv_intraday"
DEFAULT_QLIB_BASE = ROOT / "data" / "qlib_data"
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
    df.to_csv(out, index=False)
    print(f"  {freq}: {len(df)} rows -> {out}")
    print(f"      range: {df['date'].min()} ~ {df['date'].max()}")


def convert_to_qlib(df: pd.DataFrame, freq: str, symbol: str, qlib_base: Path):
    qlib_dir = qlib_base / f"futures_{freq}"
    qlib_dir.mkdir(parents=True, exist_ok=True)

    # Calendar
    calendar = df["date"].dt.strftime("%Y-%m-%d %H:%M:%S").sort_values().unique()
    cal_path = qlib_dir / "calendars" / f"{freq}.txt"
    cal_path.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(cal_path, calendar, fmt="%s")

    # Instruments
    inst_path = qlib_dir / "instruments" / "all.txt"
    inst_path.parent.mkdir(parents=True, exist_ok=True)
    start = df["date"].min().strftime("%Y-%m-%d %H:%M:%S")
    end = df["date"].max().strftime("%Y-%m-%d %H:%M:%S")
    inst_path.write_text(f"{symbol}\t{start}\t{end}\n", encoding="utf-8")

    # Features
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


def main():
    parser = argparse.ArgumentParser(description="1 分钟 CSV → 5/15/60 分钟 CSV + Qlib")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="1 分钟 CSV 路径")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Qlib symbol / 文件名前缀")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR, help="CSV 输出目录")
    parser.add_argument("--qlib-dir", type=Path, default=DEFAULT_QLIB_BASE, help="Qlib 数据根目录")
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
        convert_to_qlib(df_freq, freq, args.symbol, args.qlib_dir)

    print("\nDone. Qlib multi-frequency data ready.")


if __name__ == "__main__":
    main()
