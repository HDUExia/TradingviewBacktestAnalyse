"""生成一份示例 MES 1 分钟行情 + 示例回放交易，用于开箱即用地体验复盘面板。

生成文件（提交到仓库，别人 clone 下来即可用）：
- sample_data/sample_1min.csv   1 分钟 K 线
- sample_data/sample_trades.csv 回放交易记录
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "sample_data"
MULTIPLIER = 5.0  # MES 每点 5 美元


def generate_bars() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    price = 5500.0
    for day_offset in range(4):
        day = datetime(2024, 6, 24) + timedelta(days=day_offset)
        t = day.replace(hour=9, minute=30)
        end = day.replace(hour=16, minute=0)
        while t <= end:
            price = max(5000.0, price + rng.normal(0, 0.8))
            open_ = price
            close = price + rng.normal(0, 0.6)
            high = max(open_, close) + abs(rng.normal(0, 0.4))
            low = min(open_, close) - abs(rng.normal(0, 0.4))
            volume = int(rng.integers(50, 500))
            rows.append(
                (
                    t.strftime("%Y-%m-%d %H:%M"),
                    "@MES#C",
                    round(open_, 2),
                    round(high, 2),
                    round(low, 2),
                    round(close, 2),
                    volume,
                    0,
                )
            )
            price = close
            t += timedelta(minutes=1)

    return pd.DataFrame(
        rows,
        columns=["DateTime", "Symbol", "Open", "High", "Low", "Close", "Volume", "Trades"],
    )


def _close_at(bars: pd.DataFrame, dt: str) -> float:
    row = bars[bars["DateTime"] == dt]
    return float(row["Close"].iloc[0])


def generate_trades(bars: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("多头进场", "多头出场", "long", "2024-06-24 10:00", "2024-06-24 13:30", "回踩均线做多", "到达目标位止盈"),
        ("空头进场", "空头出场", "short", "2024-06-25 10:00", "2024-06-25 12:00", "跌破前低做空", "到达目标位止盈"),
        ("多头进场", "多头出场", "long", "2024-06-26 10:00", "2024-06-26 14:00", "突破做多", "止损离场"),
        ("空头进场", "空头出场", "short", "2024-06-27 10:00", "2024-06-27 15:00", "反弹做空", "止损离场"),
    ]

    rows = []
    cumulative = 0.0
    for trade_id, (entry_type, exit_type, direction, entry_t, exit_t, entry_sig, exit_sig) in enumerate(specs, start=1):
        entry_dt = datetime.strptime(entry_t, "%Y-%m-%d %H:%M")
        exit_dt = datetime.strptime(exit_t, "%Y-%m-%d %H:%M")
        entry = _close_at(bars, entry_t)
        exit_ = _close_at(bars, exit_t)
        sign = 1 if direction == "long" else -1
        pnl = round((exit_ - entry) * sign * MULTIPLIER, 2)
        ret = round(pnl / (entry * MULTIPLIER) * 100, 4)
        cumulative = round(cumulative + pnl, 2)

        window = bars[(bars["DateTime"] >= entry_t) & (bars["DateTime"] <= exit_t)]
        if direction == "long":
            mfe = (window["High"].max() - entry) * MULTIPLIER
            mae = (window["Low"].min() - entry) * MULTIPLIER
        else:
            mfe = (entry - window["Low"].min()) * MULTIPLIER
            mae = (entry - window["High"].max()) * MULTIPLIER
        mfe = round(max(mfe, 0.0), 2)
        mae = round(min(mae, 0.0), 2)
        duration_bars = int((exit_dt - entry_dt).total_seconds() // 300)

        rows.append(
            [entry_t, entry_type, trade_id, entry_sig, round(entry, 2), 1, "", "", "", "", "", "", "", "", ""]
        )
        rows.append(
            [
                exit_t,
                exit_type,
                trade_id,
                exit_sig,
                round(exit_, 2),
                1,
                pnl,
                ret,
                0.0,
                mfe,
                round(mfe / (entry * MULTIPLIER) * 100, 4),
                mae,
                round(mae / (entry * MULTIPLIER) * 100, 4),
                duration_bars,
                cumulative,
            ]
        )

    return pd.DataFrame(
        rows,
        columns=[
            "日期和时间",
            "类型",
            "交易编号",
            "信号",
            "价格 USD",
            "大小（数量）",
            "净损益 USD",
            "回报 %",
            "手续费 USD",
            "有利波动 USD",
            "有利波动 %",
            "不利波动 USD",
            "不利波动 %",
            "持续时间（K线）",
            "累计损益 USD",
        ],
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bars = generate_bars()
    bars.to_csv(OUT_DIR / "sample_1min.csv", index=False)
    print(f"1 分钟行情 -> {OUT_DIR / 'sample_1min.csv'} ({len(bars)} 根)")

    trades = generate_trades(bars)
    trades.to_csv(OUT_DIR / "sample_trades.csv", index=False, encoding="utf-8-sig")
    print(f"示例交易   -> {OUT_DIR / 'sample_trades.csv'} ({len(trades)} 条记录)")


if __name__ == "__main__":
    main()
