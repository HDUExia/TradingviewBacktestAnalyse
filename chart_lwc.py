"""使用 TradingView Lightweight Charts 渲染 K 线图与指标，通过 streamlit 嵌入。"""
from __future__ import annotations

import json
from datetime import timezone

import pandas as pd

TZ_LABELS = {
    "UTC": "UTC",
    "America/New_York": "美东 ET",
    "Asia/Shanghai": "北京时间 CST",
}

_LINE_STYLES = {"solid": "Solid", "dashed": "Dashed", "dotted": "Dotted"}


def render_chart(
    df: pd.DataFrame,
    trade: pd.Series,
    title: str,
    height: int = 560,
    tz: str = "UTC",
    overlays: list[dict] | None = None,
    panes: list[dict] | None = None,
) -> str:
    """生成包含 Lightweight Charts 的 HTML。df 传入全量数据，图表自动居中到这笔交易。"""
    overlays = overlays or []
    panes = panes or []
    df = df.copy().sort_values("datetime").reset_index(drop=True)

    def to_js_time(dt) -> int:
        dt = pd.to_datetime(dt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())

    candles_js = [
        {
            "time": to_js_time(r["datetime"]),
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
        }
        for _, r in df.iterrows()
    ]

    volumes_js = [
        {
            "time": to_js_time(r["datetime"]),
            "value": float(r["volume"]),
            "color": "#26a69a" if r["close"] >= r["open"] else "#ef5350",
        }
        for _, r in df.iterrows()
    ]

    entry_ts = to_js_time(trade["entry_time"])
    exit_ts = to_js_time(trade["exit_time"])
    direction = trade["direction"]
    if direction == "long":
        entry_color, entry_shape, entry_pos = "#22c55e", "arrowUp", "belowBar"
        exit_color, exit_shape, exit_pos = "#ef4444", "arrowDown", "aboveBar"
    else:
        entry_color, entry_shape, entry_pos = "#ef4444", "arrowDown", "aboveBar"
        exit_color, exit_shape, exit_pos = "#22c55e", "arrowUp", "belowBar"

    markers_js = [
        {
            "time": entry_ts,
            "position": entry_pos,
            "color": entry_color,
            "shape": entry_shape,
            "text": f"进场 {trade['entry_price']:.2f}",
            "size": 2,
        },
        {
            "time": exit_ts,
            "position": exit_pos,
            "color": exit_color,
            "shape": exit_shape,
            "text": f"出场 {trade['exit_price']:.2f}",
            "size": 2,
        },
    ]

    def _points(values, colors=None):
        pts = []
        for i, (dt, v) in enumerate(zip(df["datetime"], values)):
            if v is None:
                continue
            p = {"time": to_js_time(dt), "value": float(v)}
            if colors is not None:
                p["color"] = colors[i]
            pts.append(p)
        return pts

    overlays_js = [
        {
            "name": s["name"],
            "label": s.get("label", s["name"]),
            "color": s["color"],
            "width": s["width"],
            "style": s["style"],
            "scale": s.get("scale", "price"),
            "points": _points(s["values"]),
        }
        for s in overlays
    ]

    panes_js = [
        {
            "key": p["key"],
            "name": p["name"],
            "series": [
                {
                    "name": s["name"],
                    "label": s.get("label", s["name"]),
                    "kind": s["kind"],
                    "color": s["color"],
                    "width": s["width"],
                    "style": s["style"],
                    "points": _points(s["values"], s.get("colors")),
                }
                for s in p["series"]
            ],
        }
        for p in panes
    ]

    pane_divs = "".join(
        f'<div id="pane-{p["key"]}" style="width:100%;height:120px;position:relative;border-top:1px solid #1e222d;">'
        f'<span style="position:absolute;top:4px;left:8px;font-size:11px;color:#8a8f98;z-index:5;">{p["name"]}</span></div>'
        for p in panes
    )

    tz_label = TZ_LABELS.get(tz, tz)

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    body {{ margin: 0; padding: 0; background: #131722; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    #container {{ width: 100%; height: {height}px; position: relative; }}
    #title {{ position: absolute; top: 6px; left: 10px; font-size: 13px; color: #d1d4dc; z-index: 10; background: rgba(19, 23, 34, 0.85); padding: 3px 8px; border-radius: 4px; pointer-events: none; border: 1px solid #2a2e39; }}
    #legend {{ position: absolute; top: 6px; right: 60px; font-size: 12px; color: #d1d4dc; z-index: 10; background: rgba(19, 23, 34, 0.85); padding: 3px 8px; border-radius: 4px; pointer-events: none; border: 1px solid #2a2e39; font-variant-numeric: tabular-nums; }}
    #tooltip {{ position: absolute; display: none; z-index: 20; background: rgba(19, 23, 34, 0.96); color: #d1d4dc; padding: 4px 8px; border-radius: 4px; font-size: 12px; pointer-events: none; border: 1px solid #2a2e39; white-space: nowrap; }}
  </style>
</head>
<body>
  <div id="container">
    <div id="title">{title} · 时区 {tz_label}</div>
    <div id="legend">O — H — L — C — | Vol —</div>
    <div id="tooltip"></div>
  </div>
  {pane_divs}
  <script>
    const container = document.getElementById('container');
    const legend = document.getElementById('legend');
    const tooltip = document.getElementById('tooltip');
    const TZ = {json.dumps(tz)};
    const ENTRY_TS = {entry_ts};
    const EXIT_TS = {exit_ts};
    const LINE_STYLES = {{ solid: LightweightCharts.LineStyle.Solid, dashed: LightweightCharts.LineStyle.Dashed, dotted: LightweightCharts.LineStyle.Dotted }};

    function fmtTZ(seconds) {{
      const d = new Date(seconds * 1000);
      return new Intl.DateTimeFormat('en-GB', {{
        timeZone: TZ,
        month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false,
      }}).format(d);
    }}

    function baseTimeScale() {{
      return {{
        borderColor: '#2a2e39',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time) => fmtTZ(time),
      }};
    }}

    const chart = LightweightCharts.createChart(container, {{
      width: container.clientWidth,
      height: {height},
      layout: {{
        background: {{ type: 'solid', color: '#131722' }},
        textColor: '#d1d4dc',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }},
      localization: {{ locale: 'en-GB' }},
      grid: {{ vertLines: {{ color: '#1e222d' }}, horzLines: {{ color: '#1e222d' }} }},
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
        ...baseTimeScale(),
        rightOffset: 12,
        barSpacing: 8,
        fixLeftEdge: false,
        fixRightEdge: false,
      }},
      handleScroll: {{ vertTouchDrag: false, horzTouchDrag: false, mouseWheel: false, pressedMouseMove: false }},
      handleScale: {{ axisPressedMouseMove: {{ time: false, price: false }}, mouseWheel: false, pinch: false }},
    }});

    const series = chart.addCandlestickSeries({{
      upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
      wickUpColor: '#26a69a', wickDownColor: '#ef5350', priceScaleId: 'right',
    }});
    const candles = {json.dumps(candles_js)};
    series.setData(candles);
    series.setMarkers({json.dumps(markers_js)});

    const volSeries = chart.addHistogramSeries({{ priceScaleId: '', priceFormat: {{ type: 'volume' }} }});
    volSeries.setData({json.dumps(volumes_js)});
    volSeries.priceScale().applyOptions({{ scaleMargins: {{ top: 0.82, bottom: 0 }}, alignLabels: false }});

    const overlays = {json.dumps(overlays_js)};
    const overlayInfo = [];
    overlays.forEach((o) => {{
      const line = chart.addLineSeries({{
        color: o.color, lineWidth: o.width,
        lineStyle: LINE_STYLES[o.style] || LightweightCharts.LineStyle.Solid,
        priceLineVisible: false, lastValueVisible: o.scale === 'price',
        priceScaleId: o.scale === 'volume' ? '' : 'right',
      }});
      line.setData(o.points);
      overlayInfo.push({{ series: line, label: o.label }});
    }});

    function updateTooltip(param) {{
      if (!param || !param.time || !param.point) {{
        tooltip.style.display = 'none';
        return;
      }}
      let best = null, bestDist = 40;
      for (const info of overlayInfo) {{
        const data = param.seriesData.get(info.series);
        if (!data || data.value === undefined) continue;
        const y = info.series.priceToCoordinate(data.value);
        if (y === null) continue;
        const dist = Math.abs(y - param.point.y);
        if (dist < bestDist) {{ bestDist = dist; best = info; }}
      }}
      if (best) {{
        const data = param.seriesData.get(best.series);
        const c = best.series.options().color;
        tooltip.style.display = 'block';
        tooltip.style.left = Math.min(param.point.x + 14, container.clientWidth - 190) + 'px';
        tooltip.style.top = (param.point.y - 32) + 'px';
        tooltip.innerHTML = `<span style="color:${{c}}">●</span> ${{best.label}} <b>${{data.value.toFixed(2)}}</b>`;
      }} else {{
        tooltip.style.display = 'none';
      }}
    }}

    chart.subscribeCrosshairMove((param) => {{
      updateTooltip(param);
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
        legend.innerHTML = `<span style="color:${{color}}">O ${{o}} H ${{h}} L ${{l}} C ${{c}}</span> | Vol ${{v}} | ${{fmtTZ(param.time)}}`;
      }}
    }});

    // ==================== 副图 ====================
    const panes = {json.dumps(panes_js)};
    const subCharts = [];
    panes.forEach((p) => {{
      const el = document.getElementById('pane-' + p.key);
      if (!el) return;
      const ch = LightweightCharts.createChart(el, {{
        width: el.clientWidth,
        height: 120,
        layout: {{ background: {{ type: 'solid', color: '#131722' }}, textColor: '#d1d4dc', fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }},
        grid: {{ vertLines: {{ color: '#1e222d' }}, horzLines: {{ color: '#1e222d' }} }},
        rightPriceScale: {{ borderColor: '#2a2e39', scaleMargins: {{ top: 0.15, bottom: 0.15 }} }},
        leftPriceScale: {{ visible: false }},
        timeScale: baseTimeScale(),
        handleScroll: {{ vertTouchDrag: false, horzTouchDrag: false, mouseWheel: false, pressedMouseMove: false }},
        handleScale: {{ axisPressedMouseMove: {{ time: false, price: false }}, mouseWheel: false, pinch: false }},
      }});
      p.series.forEach((s) => {{
        if (s.kind === 'histogram') {{
          const hist = ch.addHistogramSeries({{ priceScaleId: 'right', base: 0, priceFormat: {{ type: 'price' }} }});
          hist.setData(s.points);
        }} else {{
          const line = ch.addLineSeries({{
            color: s.color, lineWidth: s.width,
            lineStyle: LINE_STYLES[s.style] || LightweightCharts.LineStyle.Solid,
            priceLineVisible: false, lastValueVisible: true,
          }});
          line.setData(s.points);
        }}
      }});
      subCharts.push(ch);
    }});

    if (subCharts.length) {{
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {{
        if (!range) return;
        subCharts.forEach((ch) => ch.timeScale().setVisibleLogicalRange(range));
      }});
    }}

    // ==================== 拖动平移 ====================
    let isDragging = false;
    let startX = 0, startY = 0, lastX = 0, lastY = 0;
    let dragMode = null;
    const DRAG_THRESHOLD = 6;
    const PRICE_SCALE_WIDTH = 58;

    function isPriceScaleArea(x) {{ return x > container.clientWidth - PRICE_SCALE_WIDTH; }}

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
        if (isPriceScaleArea(startX)) dragMode = 'price';
        else dragMode = Math.abs(totalDy) > Math.abs(totalDx) ? 'price' : 'time';
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
      if (isPriceScaleArea(localX)) {{
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

    container.addEventListener('dblclick', (e) => {{
      const rect = container.getBoundingClientRect();
      const localX = e.clientX - rect.left;
      if (isPriceScaleArea(localX)) {{
        chart.priceScale('right').applyOptions({{ autoScale: true, scaleMargins: {{ top: 0.08, bottom: 0.18 }} }});
      }}
    }});

    const resizeObserver = new ResizeObserver(() => {{
      chart.applyOptions({{ width: container.clientWidth }});
      subCharts.forEach((ch) => {{
        const el = document.getElementById('pane-' + panes[subCharts.indexOf(ch)].key);
        if (el) ch.applyOptions({{ width: el.clientWidth }});
      }});
    }});
    resizeObserver.observe(container);

    function findIndex(ts) {{
      for (let i = 0; i < candles.length; i++) if (candles[i].time >= ts) return i;
      return candles.length - 1;
    }}

    function initialFit() {{
      if (candles.length > 1) {{
        const entryIdx = findIndex(ENTRY_TS);
        const exitIdx = findIndex(EXIT_TS);
        const pad = 60;
        const from = Math.max(0, entryIdx - pad);
        const to = Math.min(candles.length - 1, exitIdx + pad);
        chart.timeScale().setVisibleLogicalRange({{ from, to }});
      }}
      chart.priceScale('right').applyOptions({{ autoScale: true }});
    }}

    initialFit();
    setTimeout(initialFit, 200);
    setTimeout(initialFit, 500);
  </script>
</body>
</html>
"""
    return html
