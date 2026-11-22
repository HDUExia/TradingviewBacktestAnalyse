#!/usr/bin/env bash
# 初始化示例数据。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/3 生成示例行情与示例交易"
python3 scripts/generate_sample_data.py

echo "==> 2/3 解析示例回放交易"
python3 scripts/parse_replay_trades.py \
  --input sample_data/sample_trades.csv \
  --output data/replay_trades_parsed.csv

echo "==> 3/3 生成 5/15/60 分钟行情数据"
python3 scripts/prepare_mes_intraday.py \
  --input sample_data/sample_1min.csv \
  --symbol MES

echo
echo "完成。运行 streamlit run app.py 启动面板。"
