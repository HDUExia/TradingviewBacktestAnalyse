# TradingviewBacktestAnalyse

TradingView 回放交易记录的本地复盘面板。程序读取交易记录和行情 CSV，提供交易统计、K 线图和评论功能，数据保存在项目目录的 `data/` 下。

## 功能

- 统计交易数、胜率、盈亏比、总盈亏、最大回撤、夏普比率和平均持仓时间。
- 绘制权益曲线、盈亏分布、时段胜率和 MAE/MFE 散点图。
- 查看单笔交易的进出场信息，并在 5、15、60 分钟 K 线上标记进出场位置。
- 为交易添加文字和图片评论，评论保存在本地。
- 在页面中导入 TradingView 回放交易 CSV、1 分钟行情 CSV，或从 TradingView 获取行情。

## 环境

- Python 3.9 或更高版本。
- 依赖见 `requirements.txt`。

## 安装与启动

```bash
git clone --recurse-submodules git@github.com:HDUExia/TradingviewBacktestAnalyse.git
cd TradingviewBacktestAnalyse
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
bash scripts/run_demo.sh
streamlit run app.py
```

打开 `http://localhost:8501`。`run_demo.sh` 会在 `data/` 中生成示例交易和 5、15、60 分钟行情。

## 导入自己的数据

启动面板后进入「数据」页。

### 回放交易

选择「TV 数据导入」，上传 TradingView 导出的回放交易 CSV。文件需要包含以下列：

```text
日期和时间、类型、交易编号、信号、价格 USD、大小（数量）、净损益 USD、回报 %、
手续费 USD、有利波动 USD、有利波动 %、不利波动 USD、不利波动 %、持续时间（K线）、
累计损益 USD
```

解析结果写入 `data/replay_trades_parsed.csv`。示例文件是 `sample_data/sample_trades.csv`。

也可以选择「TBA 数据导入」，恢复之前导出的 Markdown 报告。报告中的交易数据和评论会写回 `data/`，行情需要另外准备。

### 1 分钟行情

手动导入时上传包含 `DateTime, Open, High, Low, Close, Volume` 列的 CSV。程序会生成：

```text
data/csv_intraday/5min/MES.csv
data/csv_intraday/15min/MES.csv
data/csv_intraday/60min/MES.csv
```

也可以选择自动拉取，填写 TradingView 品种和日期范围。命令行用法如下：

```bash
python3 scripts/fetch_tv_data.py --symbol MES1! --timeframe 5m \
  --start 2026-10-01 --end 2026-10-02
```

自动拉取依赖 TradingView Desktop、Node.js 和 QuantData 的 TradingView provider。详细配置见 [QuantData 文档](https://github.com/HDUExia/QuantData/blob/master/docs/tradingview-mcp.md)。

## 命令行脚本

```text
scripts/run_demo.sh                 初始化示例数据
scripts/generate_sample_data.py     生成示例行情和交易记录
scripts/parse_replay_trades.py      解析回放交易 CSV
scripts/prepare_mes_intraday.py     生成 5、15、60 分钟行情
scripts/fetch_tv_data.py            从 TradingView 获取行情
```

## 目录

```text
app.py                              Streamlit 入口
chart_data.py                       TradingView 数据读取与 CSV 存储
chart_lwc.py                        Lightweight Charts 图表
indicators.py                       技术指标
markdown_io.py                      Markdown 报告导入导出
sample_data/                        示例数据
vendor/quantdata/                   QuantData 子模块
docs/                               使用与开发说明
```

## 常见问题

- 依赖安装失败：升级 pip，或使用 Python 3.9/3.10 重新创建虚拟环境。
- K 线为空：在「数据」页导入或拉取行情；也可以先运行 `bash scripts/run_demo.sh`。
- 交易价格与 K 线不一致：检查数据源、连续合约设置和时区。程序仍会显示对应时间段的 K 线。

## 许可证

[Apache License 2.0](LICENSE)。作者和项目地址见 [NOTICE](NOTICE)。

期货交易使用保证金，杠杆会放大盈亏。仅供个人复盘和学习，不构成投资建议。
