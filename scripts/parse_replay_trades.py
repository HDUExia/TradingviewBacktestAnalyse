"""
解析 TradingView 回放交易 CSV，把进场/出场记录聚合成单笔交易。
输出：data/replay_trades_parsed.csv
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "回放交易_CME_MINI_MES1!_2026-08-23_57da9.csv"
OUTPUT = ROOT / "data" / "replay_trades_parsed.csv"


def parse(input_path: Path = INPUT, output_path: Path = OUTPUT) -> int:
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    df["datetime"] = pd.to_datetime(df["日期和时间"])

    # 映射类型为英文/统一格式
    type_map = {
        "多头进场": "long_entry",
        "多头出场": "long_exit",
        "空头进场": "short_entry",
        "空头出场": "short_exit",
    }
    df["action"] = df["类型"].map(type_map)

    trades = []
    for tid, g in df.groupby("交易编号"):
        g = g.sort_values("datetime")
        entry = g[g["action"].str.endswith("_entry")].iloc[0]
        exit_ = g[g["action"].str.endswith("_exit")].iloc[0]

        direction = "long" if entry["action"].startswith("long") else "short"

        trades.append({
            "trade_id": tid,
            "direction": direction,
            "entry_time": entry["datetime"],
            "exit_time": exit_["datetime"],
            "entry_signal": entry["信号"],
            "exit_signal": exit_["信号"],
            "entry_price": entry["价格 USD"],
            "exit_price": exit_["价格 USD"],
            "size": entry["大小（数量）"],
            "pnl_usd": exit_["净损益 USD"],
            "return_pct": exit_["回报 %"],
            "fees_usd": exit_["手续费 USD"],
            "mfe_usd": exit_["有利波动 USD"],      # Max Favorable Excursion
            "mfe_pct": exit_["有利波动 %"],
            "mae_usd": exit_["不利波动 USD"],      # Max Adverse Excursion
            "mae_pct": exit_["不利波动 %"],
            "duration_bars": exit_["持续时间（K线）"],
            "duration_minutes": exit_["持续时间（K线）"] * 5,
            "cumulative_pnl": exit_["累计损益 USD"],
        })

    trades_df = pd.DataFrame(trades).sort_values("entry_time").reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trades_df.to_csv(output_path, index=False)
    print(f"Parsed {len(trades_df)} trades -> {output_path}")
    print(trades_df[["trade_id", "direction", "entry_time", "exit_time", "pnl_usd", "return_pct", "duration_bars"]].head())
    return len(trades_df)


def main() -> None:
    parser = argparse.ArgumentParser(description="解析 TradingView 回放交易 CSV")
    parser.add_argument("--input", type=Path, default=INPUT, help="回放交易 CSV 路径")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="输出单笔交易 CSV 路径")
    args = parser.parse_args()
    parse(args.input, args.output)


if __name__ == "__main__":
    main()
