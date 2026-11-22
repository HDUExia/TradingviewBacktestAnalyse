# 回放交易复盘

面板读取 TradingView 的回放交易记录，按单笔交易展示统计数据和行情。

## 启动

```bash
cd TradingviewBacktestAnalyse
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

浏览器打开 `http://localhost:8501`。

## 页面内容

1. **汇总指标**：总交易数、胜率、盈亏比、总盈亏、最大回撤、夏普、平均持仓时间。
2. **图表**：权益曲线、盈亏分布、时段胜率、MAE/MFE 散点。
3. **交易详情**：方向、进出场价与信号、MFE/MAE、持仓时长，并加载该时间窗口的
   **5 / 15 / 60 分钟** K 线，进出场点用三角形标注。
4. **复盘评论**：每笔交易可添加文字和图片，保存在本地 `data/`。
5. **数据**：上传回放交易 CSV、上传 1 分钟行情，或从 TradingView 获取行情。

## 数据说明

行情数据以 CSV 形式存放在 `data/csv_intraday/<周期>/<品种>.csv`：

```
data/csv_intraday/
├── 5min/MES.csv
├── 15min/MES.csv
└── 60min/MES.csv
```

行情文件生成方式：

- 上传 1 分钟行情 → `scripts/prepare_mes_intraday.py` 重采样为 5/15/60 分钟；
- 或通过 QuantData 从 TradingView 拉取（`scripts/fetch_tv_data.py`，历史区间走回放模式）。

## 价格不匹配

如果交易价格与历史 K 线不一致，通常与数据源、连续合约设置或时区有关。页面会显示
黄色提示，但仍会按交易时间加载对应的 K 线。
