"""
使用 TradingView Lightweight Charts 渲染接近原生 TV 体验的 K 线图。
通过 streamlit.components.v1.html 嵌入。
"""
import json
import pandas as pd


def render_chart(
    df: pd.DataFrame,
    trade: pd.Series,
    title: str,
    height: int = 560,
) -> str:
    """生成包含 Lightweight Charts 的 HTML 字符串。"""

    df = df.copy().sort_values("datetime").reset_index(drop=True)
    df["time_str"] = df["datetime"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    candles = df[["time_str", "open", "high", "low", "close"]].rename(
        columns={"time_str": "time"}
    ).to_dict("records")

    volumes = []
    for _, row in df.iterrows():
        color = "#26a69a" if row["close"] >= row["open"] else "#ef5350"
        volumes.append({
            "time": row["time_str"],
            "value": float(row["volume"]),
            "color": color,
        })

    entry_time = trade["entry_time"].strftime("%Y-%m-%dT%H:%M:%S")
    exit_time = trade["exit_time"].strftime("%Y-%m-%dT%H:%M:%S")
    direction = trade["direction"]

    if direction == "long":
        entry_color, entry_shape, entry_pos = "#22c55e", "arrowUp", "aboveBar"
        exit_color, exit_shape, exit_pos = "#ef4444", "arrowDown", "belowBar"
    else:
        entry_color, entry_shape, entry_pos = "#ef4444", "arrowDown", "belowBar"
        exit_color, exit_shape, exit_pos = "#22c55e", "arrowUp", "aboveBar"

    markers = [
        {
            "time": entry_time,
            "position": entry_pos,
            "color": entry_color,
            "shape": entry_shape,
            "text": f"进场 {trade['entry_price']:.2f}",
            "size": 2,
        },
        {
            "time": exit_time,
            "position": exit_pos,
            "color": exit_color,
            "shape": exit_shape,
            "text": f"出场 {trade['exit_price']:.2f}",
            "size": 2,
        },
    ]

    # 把 Python 的 datetime 字符串转成 JS 时间戳（毫秒），Lightweight Charts 更稳定
    def to_js_time(dt_str):
        dt = pd.to_datetime(dt_str)
        return int(dt.timestamp())

    candles_js = [
        {
            "time": to_js_time(c["time"]),
            "open": c["open"],
            "high": c["high"],
            "low": c["low"],
            "close": c["close"],
        }
        for c in candles
    ]
    volumes_js = [
        {"time": to_js_time(v["time"]), "value": v["value"], "color": v["color"]}
        for v in volumes
    ]
    markers_js = [
        {**m, "time": to_js_time(m["time"])}
        for m in markers
    ]

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    body {{ margin: 0; padding: 0; overflow: hidden; background: #131722; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    #container {{ width: 100%; height: {height}px; position: relative; }}
    #title {{ position: absolute; top: 6px; left: 10px; font-size: 13px; color: #d1d4dc; z-index: 10; background: rgba(19, 23, 34, 0.85); padding: 3px 8px; border-radius: 4px; pointer-events: none; border: 1px solid #2a2e39; }}
    #legend {{ position: absolute; top: 6px; right: 60px; font-size: 12px; color: #d1d4dc; z-index: 10; background: rgba(19, 23, 34, 0.85); padding: 3px 8px; border-radius: 4px; pointer-events: none; border: 1px solid #2a2e39; font-variant-numeric: tabular-nums; }}
  </style>
</head>
<body>
  <div id="container">
    <div id="title">{title}</div>
    <div id="legend">O — H — L — C — | Vol —</div>
  </div>
  <script>
    const container = document.getElementById('container');
    const legend = document.getElementById('legend');

    const chart = LightweightCharts.createChart(container, {{
      width: container.clientWidth,
      height: {height},
      layout: {{
        background: {{ type: 'solid', color: '#131722' }},
        textColor: '#d1d4dc',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }},
      grid: {{
        vertLines: {{ color: '#1e222d' }},
        horzLines: {{ color: '#1e222d' }},
      }},
      crosshair: {{
        mode: LightweightCharts.CrosshairMode.Magnet,
        vertLine: {{ color: '#758696', width: 1, style: 2, labelBackgroundColor: '#758696' }},
        horzLine: {{ color: '#758696', width: 1, style: 2, labelBackgroundColor: '#758696' }},
      }},
      rightPriceScale: {{
        borderColor: '#2a2e39',
        scaleMargins: {{ top: 0.08, bottom: 0.18 }},
        alignLabels: true,
        autoScale: true,
        borderVisible: true,
      }},
      leftPriceScale: {{ visible: false }},
      timeScale: {{
        borderColor: '#2a2e39',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12,
        barSpacing: 8,
        fixLeftEdge: false,
        fixRightEdge: false,
      }},
      handleScroll: {{
        vertTouchDrag: false,
        horzTouchDrag: false,
        mouseWheel: false,
        pressedMouseMove: false,
      }},
      handleScale: {{
        axisPressedMouseMove: {{ time: false, price: false }},
        mouseWheel: false,
        pinch: false,
      }},
    }});

    const series = chart.addCandlestickSeries({{
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      priceScaleId: 'right',
    }});

    const candles = {json.dumps(candles_js)};
    series.setData(candles);
    series.setMarkers({json.dumps(markers_js)});

    const volSeries = chart.addHistogramSeries({{
      priceScaleId: '',
      priceFormat: {{ type: 'volume' }},
    }});
    const volumes = {json.dumps(volumes_js)};
    volSeries.setData(volumes);
    volSeries.priceScale().applyOptions({{
      scaleMargins: {{ top: 0.82, bottom: 0 }},
      alignLabels: false,
    }});

    chart.subscribeCrosshairMove((param) => {{
      if (!param.time || !param.point) {{
        legend.innerHTML = 'O — H — L — C — | Vol —';
        return;
      }}
      const data = param.seriesData.get(series);
      const volData = param.seriesData.get(volSeries);
      if (data) {{
        const o = data.open.toFixed(2);
        const h = data.high.toFixed(2);
        const l = data.low.toFixed(2);
        const c = data.close.toFixed(2);
        const v = volData ? Math.round(volData.value).toLocaleString() : '-';
        const color = data.close >= data.open ? '#26a69a' : '#ef5350';
        legend.innerHTML = `<span style="color:${{color}}">O ${{o}} &nbsp;H ${{h}} &nbsp;L ${{l}} &nbsp;C ${{c}}</span> &nbsp;| &nbsp;Vol ${{v}}`;
      }}
    }});

    // ==================== 自定义交互 ====================

    let isDragging = false;
    let startX = 0, startY = 0, lastX = 0, lastY = 0;
    let dragMode = null;
    const DRAG_THRESHOLD = 6;
    const PRICE_SCALE_WIDTH = 58;

    function isPriceScaleArea(x) {{
      return x > container.clientWidth - PRICE_SCALE_WIDTH;
    }}

    container.addEventListener('mousedown', (e) => {{
      if (e.button !== 0) return;
      isDragging = true;
      startX = lastX = e.clientX;
      startY = lastY = e.clientY;
      dragMode = null;
      container.style.cursor = 'grabbing';
    }});

    window.addEventListener('mousemove', (e) => {{
      if (!isDragging) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      const totalDx = e.clientX - startX;
      const totalDy = e.clientY - startY;

      if (dragMode === null && (Math.abs(totalDx) > DRAG_THRESHOLD || Math.abs(totalDy) > DRAG_THRESHOLD)) {{
        if (isPriceScaleArea(startX)) {{
          dragMode = 'price';
        }} else {{
          dragMode = Math.abs(totalDy) > Math.abs(totalDx) ? 'price' : 'time';
        }}
      }}

      lastX = e.clientX;
      lastY = e.clientY;

      if (dragMode === 'price') {{
        const panSpeed = 0.0022;
        const ps = chart.priceScale('right');
        const opts = ps.options();
        let top = opts.scaleMargins.top;
        let bottom = opts.scaleMargins.bottom;
        const shift = dy * panSpeed;
        top = Math.max(0.01, Math.min(0.98 - bottom, top - shift));
        bottom = Math.max(0.01, Math.min(0.98 - top, bottom + shift));
        ps.applyOptions({{ autoScale: false, scaleMargins: {{ top, bottom }} }});
      }} else if (dragMode === 'time') {{
        chart.timeScale().scrollToPosition(chart.timeScale().scrollPosition() - dx / 3, false);
      }}
    }});

    window.addEventListener('mouseup', () => {{
      isDragging = false;
      dragMode = null;
      container.style.cursor = 'default';
    }});

    container.addEventListener('wheel', (e) => {{
      e.preventDefault();
      const rect = container.getBoundingClientRect();
      const localX = e.clientX - rect.left;
      const isPriceArea = isPriceScaleArea(localX);

      if (isPriceArea) {{
        const zoomSpeed = 0.12;
        const factor = e.deltaY > 0 ? (1 + zoomSpeed) : (1 - zoomSpeed);
        const ps = chart.priceScale('right');
        const opts = ps.options();
        let top = opts.scaleMargins.top;
        let bottom = opts.scaleMargins.bottom;
        const range = 1 - top - bottom;
        const newRange = Math.max(0.03, Math.min(0.94, range * factor));
        const extra = 1 - newRange - top - bottom;
        top = Math.max(0.01, top + extra / 2);
        bottom = Math.max(0.01, bottom + extra / 2);
        ps.applyOptions({{ autoScale: false, scaleMargins: {{ top, bottom }} }});
      }} else {{
        const zoomSpeed = 0.15;
        const factor = e.deltaY > 0 ? (1 + zoomSpeed) : (1 - zoomSpeed);
        const ts = chart.timeScale();
        const logicalRange = ts.getVisibleLogicalRange();
        if (logicalRange) {{
          const center = (logicalRange.from + logicalRange.to) / 2;
          const half = (logicalRange.to - logicalRange.from) / 2 * factor;
          ts.setVisibleLogicalRange({{ from: center - half, to: center + half }});
        }}
      }}
    }}, {{ passive: false }});

    // 自适应窗口大小
    const resizeObserver = new ResizeObserver(() => {{
      chart.applyOptions({{ width: container.clientWidth }});
    }});
    resizeObserver.observe(container);

    // 初始显示全部数据，用 setVisibleLogicalRange 确保不会出现单根 K 线
    function initialFit() {{
      if (candles.length > 1) {{
        chart.timeScale().setVisibleLogicalRange({{ from: 0, to: candles.length - 1 }});
      }}
      chart.priceScale('right').applyOptions({{ autoScale: true }});
    }}

    // 立即执行 + 延迟再执行一次，防止 Streamlit tab 初始宽度为 0
    initialFit();
    setTimeout(initialFit, 200);
    setTimeout(initialFit, 500);
  </script>
</body>
</html>
"""
    return html
