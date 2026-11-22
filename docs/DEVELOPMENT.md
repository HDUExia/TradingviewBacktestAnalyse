# TradingviewBacktestAnalyse 开发说明

## 运行

```bash
git clone --recurse-submodules git@github.com:HDUExia/TradingviewBacktestAnalyse.git
cd TradingviewBacktestAnalyse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
bash scripts/run_demo.sh
streamlit run app.py
```

程序是本地 Streamlit 应用，没有数据库和后端服务。运行时生成的文件都放在 `data/`，该目录不会提交到仓库。

## 代码结构

```text
app.py                       页面、状态和本地文件操作
chart_lwc.py                 Lightweight Charts 图表
chart_data.py                TradingView 数据获取和 CSV 存储
indicators.py                技术指标计算
markdown_io.py               Markdown 报告导入导出
scripts/
  generate_sample_data.py    生成示例行情和交易记录
  parse_replay_trades.py     解析 TradingView 回放交易
  prepare_mes_intraday.py   生成 5、15、60 分钟行情
  fetch_tv_data.py           从 TradingView 获取行情
  run_demo.sh                初始化示例数据
sample_data/                 示例 CSV
vendor/quantdata/            QuantData 子模块
data/                        运行时数据，不提交
```

## 数据

交易记录经过 `scripts/parse_replay_trades.py` 处理后写入 `data/replay_trades_parsed.csv`。行情 CSV 按周期存放在 `data/csv_intraday/<周期>/`，格式为：

```text
date,symbol,open,high,low,close,volume
```

`date` 按无时区的 UTC 时间保存。1 分钟行情通过 `scripts/prepare_mes_intraday.py` 重采样；从 TradingView 获取的 5 分钟行情会另外生成 15 分钟和 60 分钟文件。`chart_data.fill_session_gaps()` 只补交易时段内不超过两小时的缺口，周末和节假日的长缺口保留。

Markdown 报告包含交易 CSV 和评论，不包含 K 线数据。评论使用文字段和图片段保存，图片文件仍在 `data/uploads/`。

## 页面

`main()` 负责初始化状态、加载设置和切换页面：

- 「总结」显示交易统计、权益曲线、盈亏分布、时段胜率和 MAE/MFE 散点图。
- 「交易」显示当前交易的多周期 K 线、进出场信息和评论。
- 「数据」导入交易 CSV、导入 1 分钟行情，或通过 TradingView 获取行情。
- 「设置」保存图表高度和显示时区；「指标」管理当前图表使用的指标。

本地设置保存在 `data/settings.json`。交易评论保存在 `data/comments.json`，图片存放在 `data/uploads/`。

## 图表和指标

`chart_lwc.render_chart()` 接收完整行情数据，生成嵌入 Streamlit 的 HTML。图表按交易位置初始定位，支持拖动、滚轮缩放和价格轴复位；副图与主图共用时间轴。

`indicators.py` 中每个指标由一个计算函数和 `INDICATORS` 注册项组成。计算结果分为主图线和副图线，在渲染时生成，因此修改参数后不需要重新准备行情。

新增指标时，实现一个返回 series 的函数，再在 `INDICATORS` 中填写名称、默认参数和计算函数。

## 修改代码

页面样式集中在 `app.py` 的 `_CSS` 和 `.streamlit/config.toml`。如果修改了数据格式、页面行为或导入导出格式，也同步更新 `README.md` 和本文件。

评论输入目前使用原生 Streamlit 表单。自定义组件在 Streamlit 1.50 下会反复重渲染，暂不使用。

Python 3.9 需要保留各脚本中的 `from __future__ import annotations`，否则 `X | None` 类型注解无法解析。

## 已知限制

- 指标组合不能保存为预设。
- 副图指标的悬停提示不显示完整参数。
- TradingView 历史回放偶尔会出现单日缺口。
- 行情量较大且同时启用多个指标时，嵌入页面会变大。
