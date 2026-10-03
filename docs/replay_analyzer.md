# 回放交易复盘面板说明

把 TradingView 的**回放交易记录**解析成单笔交易，用 Streamlit 做交互式复盘。

## 启动

```bash
cd TradingviewBacktestAnalyse
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

浏览器打开 `http://localhost:8501`。

## 功能

1. **汇总指标**：总交易数、胜率、盈亏比、总盈亏、最大回撤、夏普、平均持仓时间。
2. **图表**：权益曲线、盈亏分布、时段胜率、MAE/MFE 散点。
3. **交易详情**：方向、进出场价与信号、MFE/MAE、持仓时长，并加载该时间窗口的
   **5 / 15 / 60 分钟** K 线，进出场点用三角形标注。
4. **复盘评论**：每笔交易可写评论并贴图，保存在本地 `data/`。
5. **数据管理（UI）**：上传回放交易 CSV、上传 1 分钟行情，或从 TradingView 拉取。

## 数据说明

行情数据以 CSV 形式存放在 `data/csv_intraday/<周期>/<品种>.csv`：

```
data/csv_intraday/
├── 5min/MES.csv
├── 15min/MES.csv
└── 60min/MES.csv
```

生成方式：

- 上传 1 分钟行情 → `scripts/prepare_mes_intraday.py` 重采样为 5/15/60 分钟；
- 或通过 QuantData 从 TradingView 拉取（`scripts/fetch_tv_data.py`，历史区间走回放模式）。

## 价格不匹配

如果交易记录的价格与历史 K 线不完全一致，可能原因：数据来源不同、合约连续调整
方式不同、时区/夏令时处理差异。面板检测到不匹配时会弹出黄色警告，但仍会按时间
渲染 K 线上下文。
