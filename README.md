# TradingviewBacktestAnalyse

把 TradingView 的**回放交易记录**可视化复盘的面板。仓库自带一份示例数据，
你 clone 下来跑几条命令就能看到效果，不用先准备自己的行情。

## 功能

- **汇总指标卡**：总交易数、胜率、盈亏比、总盈亏、最大回撤、夏普、平均持仓时间
- **图表**：权益曲线、盈亏分布、时段胜率（亚盘/欧盘/美盘）、MAE/MFE 散点
- **单笔交易详情**：方向、进场/出场价与信号、MFE/MAE、持仓时长，并同步加载
  **5 / 15 / 60 分钟** K 线，进场/出场点用三角形标注
- **复盘评论**：每笔交易可以写评论并直接粘贴图片（图文混排、按顺序），保存在本地
- **数据管理页（UI）**：上传回放交易 CSV、上传 1 分钟行情、或从 TradingView
  拉取 K 线，全程不用命令行

## 环境要求

- Python 3.9+（推荐 3.9 ~ 3.12）
- 其余依赖在 `requirements.txt` 里，下面一步装好

## 快速开始（4 条命令）

```bash
# 1) 克隆并进入
git clone --recurse-submodules git@github.com:HDUExia/TradingviewBacktestAnalyse.git
cd TradingviewBacktestAnalyse

# 2) 建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate          # Windows 用: venv\Scripts\activate
pip install -r requirements.txt

# 3) 一键生成示例数据（示例行情 + 4 笔示例交易，并转成行情 CSV）
bash scripts/run_demo.sh

# 4) 启动面板
streamlit run app.py
```

浏览器打开 `http://localhost:8501` 即可看到面板。

> `run_demo.sh` 会生成 `sample_data/` 下的示例数据，并输出到 `data/`（已加入
> `.gitignore`）。想换成自己的数据，看下一节。
> 本仓库以 [QuantData](https://github.com/HDUExia/QuantData) 作为子项目
> （`vendor/quantdata`），用于缺数据时从 TradingView 拉取；克隆时加
> `--recurse-submodules` 会一起拉下来。如果漏了，可补：
> `git submodule update --init --recursive`。

## 用自己的数据

最快的方式是**直接在界面里操作**：启动面板后，点左侧「🛠 数据」页，
可以：

- 上传 TradingView 回放交易 CSV，一键解析；
- 上传 1 分钟行情 CSV，一键生成 5/15/60 分钟 K 线；
- 或填品种/周期/日期，通过 QuantData 从 TradingView 拉取 K 线。

（如果更习惯命令行，也可以用下面的脚本，效果一样。）

需要两个 TradingView 导出的 CSV：

1. **回放交易记录 CSV**，列名需包含：
   `日期和时间、类型、交易编号、信号、价格 USD、大小（数量）、净损益 USD、
   回报 %、手续费 USD、有利波动 USD、有利波动 %、不利波动 USD、不利波动 %、
   持续时间（K线）、累计损益 USD`。
   仓库里的 [`sample_data/sample_trades.csv`](sample_data/sample_trades.csv) 就是标准样例。
2. **1 分钟行情 CSV**，至少包含 `DateTime, Open, High, Low, Close, Volume`。
   见 [`sample_data/sample_1min.csv`](sample_data/sample_1min.csv)。

然后执行：

```bash
# 解析回放交易 → data/replay_trades_parsed.csv
python3 scripts/parse_replay_trades.py --input "你的回放交易.csv"

# 1 分钟行情 → 5/15/60 分钟 CSV
python3 scripts/prepare_mes_intraday.py --input "你的1分钟行情.csv" --symbol MES

streamlit run app.py
```

`--symbol` 默认是 `MES`，按你的品种改即可。

## 从 TradingView 拉取缺失数据（通过 QuantData）

当某笔交易的 K 线数据不在本地时，面板会提示你可以用 QuantData 从 TradingView
拉取。在界面上：进「🛠 数据」→「行情 K 线」→「方式二：从 TradingView 拉取」，
填好品种、周期、日期即可。命令行等价于：

```bash
python3 scripts/fetch_tv_data.py --symbol MES1! --timeframe 5m \
  --start 2026-10-01 --end 2026-10-02
```

它会调用 QuantData 的 `tradingview` provider，把拉到的 K 线合并进
`data/csv_intraday/`，刷新面板即可看到。

> 说明：最近的数据直接走 `ohlcv`；历史 intraday 会自动切到 TradingView 的
> **K 线回放模式**按天分页拉取，所以长区间会慢一些，拉取期间会临时切换图表
> 到回放模式、结束后恢复。
> 拉取的是**完整 ETH 盘**（夜盘 + 日盘，每天约 23 小时）；每天约 1 小时的
> CME 维护停盘会用平价、零成交量的 K 线自动填平，保证 K 线连续。
>
> 另外，拉取需要本机装好 TradingView Desktop、Node.js 和 TradingView MCP 的
> `tv` CLI（默认路径 `~/.claude/tradingview-mcp/src/cli/index.js`，可用
> `TV_CLI_PATH` 覆盖）。详见 QuantData 的
> [docs/tradingview-mcp.md](https://github.com/HDUExia/QuantData/blob/master/docs/tradingview-mcp.md)。

## 目录结构

```
├── app.py                          # 复盘面板（Streamlit 入口）
├── chart_data.py                   # 通过 QuantData 从 TV 拉取的桥接层
├── chart_lwc.py                    # Lightweight Charts K 线渲染
├── sample_data/                    # 示例行情与示例交易（可开箱体验）
├── vendor/quantdata/               # QuantData 子项目（git submodule）
├── scripts/
│   ├── run_demo.sh                 # 一键生成示例数据并初始化
│   ├── generate_sample_data.py     # 生成示例数据
│   ├── parse_replay_trades.py      # 解析回放交易 CSV → 单笔交易
│   ├── prepare_mes_intraday.py     # 1 分钟行情 → 5/15/60 分钟 CSV
│   ├── fetch_tv_data.py            # 通过 QuantData 从 TradingView 拉取 K 线
└── docs/
    └── replay_analyzer.md          # 更详细的使用说明
```

## 常见问题

- **依赖安装失败**：先 `pip install --upgrade pip`，或换 Python 3.9/3.10 重新建虚拟环境。
- **K 线加载为空**：先在「🛠 数据」页上传/拉取对应的行情数据；或先用示例数据确认能跑（`bash scripts/run_demo.sh`）。
- **出现「交易价格与 K 线不完全匹配」黄色警告**：通常是因为数据源或合约连续方式不同，属于提示，不影响查看。

## 许可证

[Apache License 2.0](LICENSE)，作者与项目地址见 [NOTICE](NOTICE)。

## 免责声明

期货为保证金交易，杠杆会放大盈亏。本工具仅用于个人复盘与学习，不构成投资建议。
