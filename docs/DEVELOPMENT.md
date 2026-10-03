# TradingviewBacktestAnalyse 开发文档（给 AI 接力用）

## 0. 文档同步规则（最高优先级，必须遵守）

本文档（以及 `README.md`、`docs/` 下其它文档）是项目事实的权威来源。

任何**功能改动或设计改动**，只要和现有文档描述不一致，必须：

1. **改动时主动声明差异**：在提交说明 / 回复里明确写出「我改动了 X，与文档的 Y 节
   描述不一致」，让相关方知情，不能默默改掉。
2. **确认后立即同步文档**：改动被确认后，必须同步更新本文档及所有受影响的文档，
   保证文档与代码一致。

**禁止「代码改了、文档没改」的漂移。** 如果发现文档与代码不一致，以最新确认后的
状态为准，并尽快补齐落后的一侧。

## 1. 项目是什么

一个把 TradingView「回放交易记录」可视化复盘的面板。用户上传回放交易 CSV 和
行情数据（或通过 QuantData 从 TradingView 拉取），面板按交易展示 K 线、指标、
盈亏统计，并支持评论（图文混排）。

- 技术栈：**Streamlit**（UI）+ **Lightweight Charts**（K 线，纯 JS 嵌入）+ pandas/plotly。
- 无数据库、无后端，本地单机运行，数据全部落在 `data/` 目录（已 gitignore）。
- **已彻底移除 Qlib**：行情直接用普通 CSV 读取，不再有 Qlib 二进制/依赖。

## 2. 快速启动

```bash
git clone --recurse-submodules git@github.com:HDUExia/TradingviewBacktestAnalyse.git
cd TradingviewBacktestAnalyse
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
bash scripts/run_demo.sh      # 生成示例数据
streamlit run app.py
```

依赖只有 `numpy / pandas / plotly / streamlit`。Python 3.9+ 即可。

## 3. 目录结构

```
app.py                       # Streamlit 主入口（所有页面/状态 + 顶部应用栏 + 主题 CSS）
chart_lwc.py                 # Lightweight Charts 渲染（K 线+指标+副图+交互）
chart_data.py                # 与 QuantData 的桥接 + CSV 读写 + 缺口填充
indicators.py                # 指标插件库（注册表 + 计算）
markdown_io.py               # Markdown 报告导入导出（原始交易数据 + 评论）
scripts/
  generate_sample_data.py    # 生成示例行情/交易
  parse_replay_trades.py     # 回放交易 CSV -> data/replay_trades_parsed.csv
  prepare_mes_intraday.py    # 1分钟 CSV -> 5/15/60 分钟 CSV
  fetch_tv_data.py           # 通过 QD 从 TradingView 拉取 K 线
  run_demo.sh                # 一键初始化示例数据
sample_data/                 # 提交到仓库的示例数据
vendor/quantdata/            # QuantData 子项目（git submodule）
data/                        # 运行期数据（gitignore，不提交）
```

## 4. 数据流与存储

### 数据来源（三条路，最终都落成 CSV）

1. **回放交易**：`回放交易 CSV` → `parse_replay_trades.py` → `data/replay_trades_parsed.csv`
2. **1 分钟行情**：`1min CSV` → `prepare_mes_intraday.py` → `data/csv_intraday/{5min,15min,60min}/<SYMBOL>.csv`
3. **TradingView 拉取**：`chart_data.fetch_and_store()` 调 QD 的 TradingView provider → 合并进 `data/csv_intraday/`，并本地重采样出 15/60 分钟

### 行情 CSV 格式

`date,symbol,open,high,low,close,volume`，`date` 为**无时区的 UTC 时间**。

### 其它本地数据（都在 `data/`，gitignore）

- `replay_trades_parsed.csv`：解析后的单笔交易
- `comments.json`：评论（segments 结构，文字段 + 图片段）
- `uploads/`：评论里粘贴的图片
- `settings.json`：UI 设置（指标实例、时区、图表高度），跨刷新持久化

### Markdown 导入导出

- 导出：`markdown_io.export_markdown(trades_csv, comments, root)`，在总结页提供下载。
- 导入：`markdown_io.import_markdown(text, root)`，在数据页「回放交易」提供 `.md` 上传。
- Markdown 只包含**原始交易数据 + 评论**；K 线数据不放进 Markdown（体积大，由 CSV/TV 重新生成）。
- 格式：交易数据用带 `<!-- TBA_TRADES_BEGIN/END -->` 标记的 ```csv 代码块；评论用
  `<!-- TBA_COMMENT_BEGIN {...} -->` 包裹，图片以 `![图片](相对路径)` 引用。

## 5. 关键组件

### app.py（UI）

- 布局：顶部应用栏 = 标题 + 导航按钮（总结/交易/数据）+ 「⚙️ 设置」「📊 指标」两个
  `st.popover`；左侧侧边栏 = 交易列表按钮（`_trade_table_sidebar`，一行一个按钮，
  当前选中的交易高亮，**仅在交易页显示**，其它页面通过 CSS 隐藏侧边栏）。
- `main()`：注入主题 CSS、加载/保存设置（`data/settings.json`）、路由到各页面
- `_settings_ui()` / `_indicators_ui()`：设置和指标管理的弹出内容（放在 popover 里）
- `summary_page()`：汇总指标 + 权益曲线/盈亏分布/时段胜率/MAE-MFE
- `detail_page()`：顶部「选择交易」下拉 + 上一笔/下一笔，加载全量 K 线 → 传指标 → 渲染三周期图 + 评论
- `data_page()`：两个下拉框分组——「交易数据」= TV 数据导入 / TBA Markdown 导入；
  「行情数据」= 自动拉取（TradingView MCP，自动判定区间）/ 手动导入（1 分钟 CSV）
- 评论：`load_comments` / `add_comment` / `_process_comment_segments`（base64 图片落盘）

### 主题 / 样式

- `.streamlit/config.toml`：**深色主题**（背景 `#0e1117`、文字 `#e6e6e6`、主色 `#4c8bf5`），
  与 K 线图/汇总图的深色 `#131722` 保持一致。
- `app.py` 顶部 `_CSS`：隐藏 Streamlit 默认 header/footer/菜单和侧边栏，圆角按钮/卡片/metric、Material 风格按钮。
- 修改 UI 样式只改 `_CSS` 或 `config.toml`，不要散落各处。

### chart_lwc.py（图表渲染）

`render_chart(df, trade, title, height, tz, overlays, panes)` 返回一段 HTML 字符串，
用 `components.html()` 嵌入。要点：
- K 线 + 成交量 + 进出场 marker（多单绿箭头在下方、空单红箭头在上方）
- 加载**全量数据**，`initialFit()` 居中到这笔交易（前后各 60 根），拖动平移、滚轮缩放
- 时间轴按 `tz`（UTC/美东/北京）显示，`tickMarkFormatter` 做时区格式化
- `overlays`（价格型 MA/EMA/BOLL 在价格轴，成交量均线在成交量轴）+ `panes`（RSI/MACD/ATR 副图，时间轴与主图同步）
- 悬停指标线显示 tooltip（名称+参数+数值）
- 双击右侧价格轴恢复默认缩放

### chart_data.py（QD 桥接）

- `fetch_tradingview_bars()`：调 QD 的 `TradingViewProvider`，返回面板格式 DataFrame
- `fetch_and_store()`：拉取 → 合并去重 → `fill_session_gaps()` → 写 CSV
- `fill_session_gaps()`：只填 2 小时以内的小缺口（CME 每日维护停盘），周末/节假日大缺口不填
- `symbol_name()`：`MES1!` → `MES`

### indicators.py（指标插件）

- 每个指标 = 一个函数 + `INDICATORS` 注册表里一行
- 新增指标：写 `def xxx(df, ...) -> list[series]`，再在 `INDICATORS` 登记 label/params
- `compute_indicators(df, instances)`：instances 是 `[{type, params, color}]`，返回 `(overlays, panes)`
- 指标在**渲染时**按需计算（不是数据准备阶段固化）

### 评论输入

- 用原生 `st.form` + `st.text_area` + `st.file_uploader(accept_multiple_files=True)`。
- 评论结构仍是 segments（文字段 + 图片段），图片按上传顺序追加在文字后。
- 历史说明：曾尝试用 `components.declare_component` 自定义组件支持 Ctrl+V 粘贴图片与
  图文混排，但 Streamlit 1.50 下 iframe 反复重渲染导致输入框闪烁、无法输入（Python 侧
  已确认无 rerun 死循环，问题在前端 iframe 生命周期）。暂时回退到原生表单；若要重做
  粘贴图片，需在有浏览器环境下按 Streamlit 组件 v2 方案调试。

## 6. 关键设计决策

- **不用 Qlib**：行情直接用 CSV，简单、依赖少、可读。
- **全量加载 + 拖动**：不用「前后 K 线数」滑块，加载全部数据让用户自由拖动查看。
- **时区统一按 UTC 存储**，显示时区可配置（避免历史 bug）。
- **指标渲染时计算**：改参数立即生效，不用重新拉数据。
- **指标插件化**：新增指标不改主流程。
- **成交量指标归成交量轴**，价格型指标归价格轴，避免值域差异压扁 K 线。

## 7. 注意事项 / 坑

1. **Python 3.9 兼容**：`X | None` 类型注解需要 `from __future__ import annotations`，否则 3.9 会报错。
2. **Streamlit session_state 刷新即丢**：指标/时区/图表高度要跨刷新持久化，走 `data/settings.json`（`load_settings` / `save_settings`），在 `main()` 开头加载、结尾保存。
3. **自定义组件**：`declare_component` 的 `path` 必须是绝对路径，且目录里有 `index.html`。组件与 Python 通过 `setComponentValue` 回传，注意用 `last_...` session_state 去重，避免重复处理。
4. **全量数据 + 多指标会撑大 HTML**（几千根 K 线 + 全部指标可到几 MB）。数据量大时要考虑抽稀/分页。
5. **时区假设**：行情 CSV 的 `date` 一律按 UTC 解释。若用户自己的 1 分钟 CSV 是别的时区，会整体偏移，需要「导入时区」选项。
6. **子模块**：`vendor/quantdata` 是 QD 的子模块，克隆要 `--recurse-submodules`；改 QD 后要在 TBA 里 `git add vendor/quantdata` 提交指针。
7. **`data/` 全部 gitignore**：不要把用户数据/图片/设置提交上去。
8. **删除文件用 apply_patch 或移到废纸篓**，不要 `rm -rf`（环境有安全拦截）。

## 8. 如何扩展

- **加指标**：`indicators.py` 写函数 + 登记 `INDICATORS`。
- **加图表类型/交互**：改 `chart_lwc.py`（纯 HTML/JS，注意 f-string 的 `{{ }}` 转义）。
- **加数据源**：在 QD 里加 provider，TBA 侧走 `chart_data.fetch_and_store`。
- **加页面**：`app.py` 写 `xxx_page()`，在 `main()` 加导航按钮和路由。

## 9. 已知问题 / 待办

- 指标暂无「保存常用组合」功能。
- 悬停 tooltip 只对主图指标生效（副图靠顶部标题识别）。
- 历史数据回放分页偶尔有单日缺口（QD 侧）。
