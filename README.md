# TradingviewBacktestAnalyse

把 TradingView 导出的**回放交易记录**解析成单笔交易，并用 Streamlit 做交互式复盘的面板。

## 功能

- **汇总指标卡**：总交易数、胜率、盈亏比、总盈亏、最大回撤、夏普、平均持仓时间
- **可视化图表**：权益曲线、盈亏分布、时段胜率（亚盘/欧盘/美盘）、MAE/MFE 散点
- **单笔交易详情**：方向、进场/出场价与信号、MFE/MAE、持仓时长，并同步加载该时间窗口的 **5 / 15 / 60 分钟** K 线
- K 线使用 **TradingView Lightweight Charts** 渲染，进场/出场点用三角形标注，持仓区间用半透明底色标出

## 目录结构

```
├── app.py                          # 复盘面板（Streamlit 入口）
├── chart_lwc.py                    # Lightweight Charts K 线渲染
├── scripts/
│   ├── parse_replay_trades.py      # 解析回放交易 CSV → 单笔交易
│   ├── prepare_mes_intraday_qlib.py# 1 分钟 CSV → 5/15/60 分钟 CSV + Qlib
│   ├── verify_mes_5min.py          # 校验 Qlib 分钟数据覆盖交易时段
│   └── test_app_logic.py           # 不启动服务，测试面板核心逻辑
└── docs/
    └── replay_analyzer.md          # 使用说明
```

## 快速开始

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

准备数据（面板依赖 `data/replay_trades_parsed.csv` 和 Qlib 分钟数据）：

```bash
# 解析 TradingView 回放交易 CSV
python scripts/parse_replay_trades.py --input "回放交易_xxx.csv"

# 用 1 分钟行情重采样生成 5/15/60 分钟 CSV + Qlib
python scripts/prepare_mes_intraday_qlib.py --input "@MES#C_1min_xxx.csv" --symbol MES
```

启动：

```bash
streamlit run app.py
```

浏览器打开 `http://localhost:8501`（或终端提示的端口）。详细说明见 [docs/replay_analyzer.md](docs/replay_analyzer.md)。

## 数据说明

- 面板通过 **Qlib** 加载 K 线，`data/qlib_data/` 为脚本生成的二进制，默认不纳入版本库。
- 回放交易 CSV 与 1 分钟行情 CSV 属于你的本地/个人数据，请自行准备，不要提交到仓库。

## 免责声明

期货为保证金交易，杠杆会放大盈亏。本工具仅用于个人复盘与学习，不构成投资建议。
