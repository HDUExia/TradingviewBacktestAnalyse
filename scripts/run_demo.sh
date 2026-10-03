#!/usr/bin/env bash
# 一键初始化示例数据，让你不用自己的行情/交易也能跑起复盘面板。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/3 生成示例行情与示例交易"
python3 scripts/generate_sample_data.py

echo "==> 2/3 解析示例回放交易"
python3 scripts/parse_replay_trades.py \
  --input sample_data/sample_trades.csv \
  --output data/replay_trades_parsed.csv

echo "==> 3/3 生成 5/15/60 分钟 Qlib 数据"
python3 scripts/prepare_mes_intraday_qlib.py \
  --input sample_data/sample_1min.csv \
  --symbol MES

echo
echo "完成！现在运行: streamlit run app.py"
