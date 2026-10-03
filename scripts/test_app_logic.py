"""测试 app.py 中的核心逻辑（不启动 Streamlit 服务器）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import app

# 初始化 Qlib
app.init_qlib()

# 加载交易
trades = app.load_trades()
print(f"Loaded {len(trades)} trades")
print(trades.head(3))

# 计算指标
metrics = app.compute_metrics(trades)
print("\nMetrics:")
for k, v in metrics.items():
    print(f"  {k}: {v}")

# 选第一笔交易测试
trade = trades.iloc[0]
print(f"\nTest trade #{trade['trade_id']}: {trade['entry_time']} -> {trade['exit_time']}")

# 加载 5m 数据
start = (trade["entry_time"] - pd.Timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
end = (trade["exit_time"] + pd.Timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
df_5m = app.load_klines("5min", start, end)
print(f"\n5m bars loaded: {len(df_5m)}")
print(df_5m.head())

# 渲染图表（render_chart 返回嵌入 Lightweight Charts 的 HTML 字符串）
html = app.render_chart(df_5m, trade, "test")
assert isinstance(html, str) and "LightweightCharts" in html
assert "setMarkers" in html and "addCandlestickSeries" in html
print(f"\nChart HTML rendered: {len(html)} chars")
