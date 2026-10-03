"""Markdown 报告导入导出：序列化「原始交易数据 + 评论」，用于持久化与 AI 分析。

约定：
- K 线数据不放进 Markdown（体积大，且可由本地 CSV / TradingView 重新生成）。
- 原始交易数据以带标记的 ```csv 代码块嵌入。
- 评论以 `<!-- TBA_COMMENT_BEGIN {...} -->` ... `<!-- TBA_COMMENT_END -->` 包裹，
  图片用 `![图片](相对路径)` 引用（相对仓库根目录）。
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

_TRADES_BEGIN = "<!-- TBA_TRADES_BEGIN -->"
_TRADES_END = "<!-- TBA_TRADES_END -->"
_COMMENT_BEGIN_RE = re.compile(r"<!-- TBA_COMMENT_BEGIN (\{.*?\}) -->")
_COMMENT_END = "<!-- TBA_COMMENT_END -->"
_IMAGE_RE = re.compile(r"^!\[.*?\]\((.*?)\)\s*$")


def _rel_path(abs_path, root: Path) -> str:
    try:
        return str(Path(abs_path).resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        return str(abs_path)


def _abs_path(rel, root: Path) -> str:
    p = Path(rel)
    return str(p) if p.is_absolute() else str((root / p).resolve())


def _comment_segments(c: dict) -> list[dict]:
    if "segments" in c:
        return c["segments"]
    segs = []
    if c.get("text"):
        segs.append({"type": "text", "text": c["text"]})
    if c.get("image_path"):
        segs.append({"type": "image", "path": c["image_path"]})
    return segs


def export_markdown(trades_csv: Path, comments: list[dict], root: Path) -> str:
    df = pd.read_csv(trades_csv)
    out = [
        "# TradingviewBacktestAnalyse 复盘报告",
        "",
        f"> 导出时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 原始交易数据",
        "",
        "| # | 方向 | 进场时间 | 出场时间 | 盈亏(USD) | 回报(%) |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        d = "多" if str(r["direction"]).lower() == "long" else "空"
        out.append(
            f"| {int(r['trade_id'])} | {d} | {r['entry_time']} | {r['exit_time']} "
            f"| {float(r['pnl_usd']):.2f} | {float(r['return_pct']):.2f} |"
        )
    out.append("")

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    out += [
        _TRADES_BEGIN,
        "```csv",
        buf.getvalue().strip(),
        "```",
        _TRADES_END,
        "",
    ]

    if comments:
        out += ["## 交易评论", ""]
        for c in comments:
            tid = c.get("trade_id")
            out.append(f"### 交易 #{tid}" if tid is not None else "### 通用评论")
            out.append("")
            meta = {"id": c.get("id", ""), "trade_id": tid, "created_at": c.get("created_at", "")}
            out.append(f"<!-- TBA_COMMENT_BEGIN {json.dumps(meta, ensure_ascii=False)} -->")
            out.append("")
            for seg in _comment_segments(c):
                if seg.get("type") == "image":
                    out.append(f"![图片]({_rel_path(seg.get('path', ''), root)})")
                else:
                    out.append(seg.get("text", ""))
                out.append("")
            out.append(_COMMENT_END)
            out.append("")

    return "\n".join(out)


def import_markdown(text: str, root: Path) -> tuple[str, list[dict]]:
    csv_text = ""
    m = re.search(
        re.escape(_TRADES_BEGIN) + r"\s*```csv\s*\n(.*?)\n```\s*" + re.escape(_TRADES_END),
        text,
        re.S,
    )
    if m:
        csv_text = m.group(1).strip()

    comments: list[dict] = []
    for m in _COMMENT_BEGIN_RE.finditer(text):
        try:
            meta = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        start = m.end()
        end = text.find(_COMMENT_END, start)
        if end == -1:
            continue

        segments: list[dict] = []
        buf: list[str] = []

        def flush() -> None:
            t = "\n".join(buf).strip()
            if t:
                segments.append({"type": "text", "text": t})
            buf.clear()

        for raw in text[start:end].splitlines():
            line = raw.rstrip()
            img = _IMAGE_RE.match(line.strip())
            if img:
                flush()
                segments.append({"type": "image", "path": _abs_path(img.group(1), root)})
            elif line.strip():
                buf.append(line)
            else:
                flush()
        flush()

        comments.append({
            "id": meta.get("id") or None,
            "trade_id": meta.get("trade_id"),
            "created_at": meta.get("created_at", ""),
            "segments": segments,
        })

    return csv_text, comments
