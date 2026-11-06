#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_wishos_cost_report.py —— WishOS 成本读数（C1 · 2026-11-06）
================================================================================
归属 : `docs/V12-WishOS-后续调整规划-v0.1-2026-11-06.md` 批次 **C1**
       「成本读数进巡检」：把「上下文长度 × 调用次数」变成可观测读数。
目的 : 从 DSH 会话转录（`$DSH_HOME/sessions`）里只读汇总 usage 事件，
       按**日**与按**会话**给出 tokens / 调用 / 缓存 / 重试 / 标题等读数，
       供 `w-watchdog` 巡检报告的「成本」节引用。
       不做预算判定、不发告警、不写生产件 —— 只出读数（判断交人）。

── 口径（🔴 必须与读数一起引用；口径不同则数字不可比）──────────────────────────
   数据源 : `$DSH_HOME/sessions/<cwd编码>/<会话目录>/session*.jsonl.zstd`
            DSH 转录为 **zstd 多帧拼接**（每追加一次写一帧）。本机 Node 的
            `zlib.zstdDecompressSync` 只解第一帧且不报错（静默截断）⇒ 一律走
            `$DSH_HOME/bin/dsh_session.py:read_records`（Python `compression.zstd`
            一次解全帧；失败自动按魔数逐帧降级）。本件不另写解压器。
  多转录 : 同一会话目录若同时存在 `session.jsonl.zstd` 与 `session.v4.jsonl.zstd`
            （2026-11-06 实测 3 处；v4 = 旧转录超集）⇒ **只取 v4**，防重复计数。
   窗口 : `[--since, --until)` 半开区间，**本地时区**（本机 Asia/Shanghai）。
            事件时间取记录顶层 `time`（毫秒；兼容 ISO 串）。
   调用 : 一条带 `data.usage` 的事件 = 1 次调用（实测载于 `assistant/message`
            与 `compaction/summary` 两类事件；`assistant/attempt` 不载 usage）。
   tokens : 优先 `totalTokens`；缺失时回退 `input+output+cacheRead+cacheWrite`。
            实测（2026-11-06）：本月窗口内 4,559/4,559 条均有 `totalTokens`，
            且 `totalTokens == input+output+cacheRead+cacheWrite`（0 处不等）。
   缓存命中 : `cacheRead / tokens`（token 权重口径，与规划 §一 一致）。

── 两种口径（⚠️ 2026-11-06 实测发现，见执行记录 C1「与计划偏差」）────────────
    full  （默认）: 扫**全部**会话目录 —— `session-*` 与裸 hex 目录（delegated /
            subagent 会话的实际落盘形态，`dsh_session.py:105-119` 两种都认）。
    plan  （--caliber plan）: 只扫目录名以 `session-` 开头的会话 —— **复现
            2026-11-06 规划基线 1,597,106,763 的口径**（`_tmp\20261106\nov_usage.py`
            的 glob 只匹配 `session-*`，静默漏掉裸 hex 目录）。
   ⇒ 引用旧基线数字时必须同时注明 `--caliber plan`；日常巡检用默认 full。

── 用法 ────────────────────────────────────────────────────────────────────────
    python tools/_wishos_cost_report.py                      # 本月至今（full）
    python tools/_wishos_cost_report.py --days 7             # 近 7 天（含今日）
    python tools/_wishos_cost_report.py --since 2026-11-01 --until 2026-11-07
    python tools/_wishos_cost_report.py --until "2026-11-06T10:12:00" --caliber plan
    python tools/_wishos_cost_report.py --json               # 机器可读
    python tools/_wishos_cost_report.py --expect-total 1597106763 --tolerance 0.01
    python tools/_wishos_cost_report.py --selfcheck          # 合成夹具自证（含⚪真阴性）
    python tools/_wishos_cost_report.py --selfcheck --verbose

── 退出码 ───────────────────────────────────────────────────────────────────────
    0 = 读数成功（且 `--expect-total` 若有则通过）
    2 = 判据不满足（selfcheck 失败 / expect-total 超容差 / 窗口参数非法）
    3 = 会话数据不可读（`$DSH_HOME/sessions` 缺失或全读失败）

只读承诺：**不写** `$DSH_HOME/sessions`、不写 `<workspace>/wishos/brain`、不写任何生产件；
本件唯一的输出是 stdout（`--json` 亦然）。落盘由调用方（巡检报告）决定。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

try:  # 本机坑：默认 GBK 控制台遇非 GBK 字符会崩（承 dsh_session.py:47-50）
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DSH_HOME = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
SESSIONS_DIR = DSH_HOME / "sessions"
SESSION_GLOB = "*/*/session*.jsonl.zstd"

# 事件类型 → 计数键（usage 之外的"次数"类读数）
COUNT_TYPES = {
    "assistant/attempt": "attempts",
    "llm/retry": "retries",
    "llm/retry-started": "retry_started",
    "session/title": "titles",
    "session/title-llm-request": "title_llm_requests",
    "web/deepseek-search-llm-request": "web_searches",
}
COMPACTION_TYPE = "compaction/summary"


# ── 时间 ───────────────────────────────────────────────────────────────────────
def parse_ts(s: str) -> int:
    """'YYYY-MM-DD' / 'YYYY-MM-DDTHH:MM[:SS]' / ISO 带时区 → 本地毫秒时间戳。"""
    s = s.strip().replace(" ", "T", 1) if len(s) > 10 else s.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return int(datetime.strptime(s, fmt).timestamp() * 1000)
        except ValueError:
            continue
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.astimezone()
    return int(d.timestamp() * 1000)


def event_ms(rec: dict) -> int | None:
    """顶层 time → 毫秒。兼容秒级数字与 ISO 串；不可得返回 None（计入 skipped）。"""
    t = rec.get("time")
    if isinstance(t, bool):
        return None
    if isinstance(t, (int, float)):
        return int(t * 1000) if t < 1e11 else int(t)
    if isinstance(t, str):
        try:
            return parse_ts(t)
        except Exception:
            return None
    return None


def day_key(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


# ── usage 解析 ────────────────────────────────────────────────────────────────
def usage_tokens(u: dict) -> dict:
    """一条 usage → {tokens,input,output,cache_read,cache_write}（含 totalTokens 回退）。"""
    it = int(u.get("inputTokens") or 0)
    ot = int(u.get("outputTokens") or 0)
    cr = int(u.get("cacheReadTokens") or 0)
    cw = int(u.get("cacheWriteTokens") or 0)
    tt = u.get("totalTokens")
    tt = int(tt) if tt is not None else it + ot + cr + cw
    return {"tokens": tt, "input": it, "output": ot, "cache_read": cr, "cache_write": cw}


def aggregate(records: list[dict], since_ms: int, until_ms: int) -> dict:
    """把记录列表按窗口聚合（纯函数：selfcheck 直接喂合成记录）。"""
    totals = Counter()
    counters = Counter()
    by_type_tokens = Counter()
    days: dict[str, Counter] = {}
    sessions: dict[str, dict] = {}
    skipped_no_time = 0
    records_seen = 0
    for rec in records:
        records_seen += 1
        ms = event_ms(rec)
        if ms is None:
            skipped_no_time += 1
            continue
        if ms < since_ms or ms >= until_ms:
            continue
        typ = rec.get("type") or "?"
        if typ in COUNT_TYPES:
            counters[COUNT_TYPES[typ]] += 1
        data = rec.get("data") or {}
        u = data.get("usage")
        if not isinstance(u, dict):
            continue
        t = usage_tokens(u)
        for k in ("tokens", "input", "output", "cache_read", "cache_write"):
            totals[k] += t[k]
        totals["calls"] += 1
        by_type_tokens[typ] += t["tokens"]
        if typ == COMPACTION_TYPE:
            counters["compaction_calls"] += 1
            counters["compaction_tokens"] += t["tokens"]
        dk = day_key(ms)
        day = days.setdefault(dk, Counter())
        for k in ("tokens", "cache_read"):
            day[k] += t[k]
        day["calls"] += 1
        sid = sessions.setdefault(rec.get("_sid") or "?", {
            "session": rec.get("_sid") or "?",
            "calls": 0, "tokens": 0, "cache_read": 0, "input": 0, "output": 0,
            "first_ms": ms, "last_ms": ms,
        })
        sid["calls"] += 1
        sid["tokens"] += t["tokens"]
        sid["cache_read"] += t["cache_read"]
        sid["input"] += t["input"]
        sid["output"] += t["output"]
        sid["first_ms"] = min(sid["first_ms"], ms)
        sid["last_ms"] = max(sid["last_ms"], ms)
    tokens = totals["tokens"]
    calls = totals["calls"]
    return {
        "window": {
            "since_ms": since_ms, "until_ms": until_ms,
            "since": _fmt(ms=since_ms), "until": _fmt(ms=until_ms),
        },
        "totals": {
            "tokens": tokens, "calls": calls,
            "avg_tokens_per_call": (tokens / calls) if calls else 0,
            "input": totals["input"], "output": totals["output"],
            "cache_read": totals["cache_read"], "cache_write": totals["cache_write"],
            "cache_hit_rate": (totals["cache_read"] / tokens) if tokens else 0,
        },
        "counters": dict(counters),
        "by_type_tokens": dict(by_type_tokens),
        "days": [{"date": k, **dict(v)} for k, v in sorted(days.items())],
        "sessions": sorted(sessions.values(), key=lambda s: -s["tokens"]),
        "records_seen": records_seen,
        "skipped_no_time": skipped_no_time,
    }


def _fmt(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%dT%H:%M:%S%z")


# ── 渲染 ──────────────────────────────────────────────────────────────────────
def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def concentration(agg: dict) -> dict:
    ss = agg["sessions"]
    top = ss[:2]
    top_tokens = sum(s["tokens"] for s in top)
    total = agg["totals"]["tokens"] or 1
    return {"top2_tokens": top_tokens, "top2_share": top_tokens / total,
            "top5_share": sum(s["tokens"] for s in ss[:5]) / total}


def render_md(agg: dict, caliber: str, top: int = 8, expect: dict | None = None) -> str:
    t = agg["totals"]
    c = agg["counters"]
    w = agg["window"]
    conc = concentration(agg)
    out = []
    out.append(f"**窗口**：`{w['since']}` ~ `{w['until']}`（半开，不含 until；**本地时区**）· "
               f"**口径**：`{caliber}`")
    out.append(f"**数据源**：`{SESSIONS_DIR}` · 会话目录 {agg['session_dirs']} 个"
               f"（读成功 {agg['files_read']} / 跳过 {agg['files_skipped']}"
               f" / 双转录去重 {agg.get('files_dual_skipped', 0)}）· "
               f"记录 {agg['records_seen']:,} 条（无时间戳 {agg['skipped_no_time']}）")
    out.append("")
    out.append("| 读数 | 值 |")
    out.append("|:--|--:|")
    out.append(f"| tokens | **{t['tokens']:,}** |")
    out.append(f"| 调用次数 | {t['calls']:,} |")
    out.append(f"| 平均 tokens / 次 | **{t['avg_tokens_per_call']:,.0f}** |")
    out.append(f"| 缓存命中（token 权重） | **{_pct(t['cache_hit_rate'])}** "
               f"（cacheRead {t['cache_read']:,}） |")
    out.append(f"| input / output | {t['input']:,} / {t['output']:,} |")
    out.append(f"| 有 usage 的会话 | {len(agg['sessions'])} |")
    out.append(f"| 会话集中度 | 前 2 会话 {_pct(conc['top2_share'])} · "
               f"前 5 会话 {_pct(conc['top5_share'])} |")
    out.append(f"| 重试 / attempt | {c.get('retries', 0):,} / {c.get('attempts', 0):,} |")
    out.append(f"| 标题 / 搜索 | {c.get('titles', 0):,} / {c.get('web_searches', 0):,} |")
    if c.get("compaction_calls"):
        out.append(f"| 压缩（compaction） | {c['compaction_calls']:,} 次 · "
                   f"{c['compaction_tokens']:,} tokens |")
    if expect:
        ok = expect["deviation"] <= expect["tolerance"]
        out.append("")
        out.append(f"**基线校验**：期望 {expect['expected']:,} · 实测 {expect['actual']:,} · "
                   f"偏差 {expect['deviation'] * 100:+.4f}% "
                   f"（容差 ±{expect['tolerance'] * 100:.1f}%）⇒ "
                   f"{'✅ PASS' if ok else '🔴 FAIL'}")
    if agg["days"]:
        out.append("")
        out.append("<details><summary>按日</summary>")
        out.append("")
        out.append("| 日期 | tokens | 调用 | 均值 | 缓存命中 |")
        out.append("|:--|--:|--:|--:|--:|")
        for d in agg["days"]:
            avg = d["tokens"] / d["calls"] if d["calls"] else 0
            hit = d["cache_read"] / d["tokens"] if d["tokens"] else 0
            out.append(f"| {d['date']} | {d['tokens']:,} | {d['calls']:,} | "
                       f"{avg:,.0f} | {_pct(hit)} |")
        out.append("")
        out.append("</details>")
    if top and agg["sessions"]:
        out.append("")
        out.append(f"**会话 Top {top}**（按 tokens）")
        out.append("")
        out.append("| # | 会话 | tokens | 调用 | 均值 | 窗口内首末事件 |")
        out.append("|--:|:--|--:|--:|--:|:--|")
        for i, s in enumerate(agg["sessions"][:top], 1):
            avg = s["tokens"] / s["calls"] if s["calls"] else 0
            out.append(f"| {i} | `{s['session']}` | {s['tokens']:,} | {s['calls']:,} | "
                       f"{avg:,.0f} | {_fmt(s['first_ms'])[:16]} → {_fmt(s['last_ms'])[:16]} |")
    return "\n".join(out)


def resolve_window(since: str | None, until: str | None, days: int | None,
                   now: datetime) -> tuple[int, int]:
    """CLI 窗口解析（独立函数 ⇒ selfcheck 可回归「--until 是否真的生效」）。

    优先级：显式 --since/--until > --days > 默认本月 1 日；until 缺省 = now。
    非法：--days<=0 / 解析失败 / until<=since ⇒ ValueError（main 转退码 2）。
    """
    if days is not None:
        if days <= 0:
            raise ValueError("--days 须为正整数")
        base = now - timedelta(days=days - 1)
        since_ms = int(base.replace(hour=0, minute=0, second=0, microsecond=0)
                       .timestamp() * 1000)
    elif since:
        since_ms = parse_ts(since)
    else:
        since_ms = int(now.replace(day=1, hour=0, minute=0, second=0,
                                   microsecond=0).timestamp() * 1000)
    until_ms = parse_ts(until) if until else int(now.timestamp() * 1000)
    if until_ms <= since_ms:
        raise ValueError("窗口非法（until 必须晚于 since）")
    return since_ms, until_ms


# ── 扫描 ──────────────────────────────────────────────────────────────────────
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


def _decompress_frames(data: bytes) -> bytes:
    """解 DSH 会话转录的 zstd 多帧拼接（Python ≥3.14 标准库优先；否则 zstandard；再否则按魔数逐帧）。"""
    try:
        from compression import zstd
        return zstd.decompress(data)
    except Exception:
        pass
    try:
        import zstandard  # optional
        return zstandard.ZstdDecompressor().decompressobj().decompress(data)
    except Exception:
        pass
    try:
        from compression import zstd as _z
    except Exception as e:  # noqa: F841
        raise RuntimeError("需要 Python ≥3.14（compression.zstd）或 pip install zstandard") from e
    offsets, i = [], data.find(ZSTD_MAGIC)
    while i != -1:
        offsets.append(i)
        i = data.find(ZSTD_MAGIC, i + 4)
    parts = []
    for n, start in enumerate(offsets):
        end = offsets[n + 1] if n + 1 < len(offsets) else len(data)
        try:
            parts.append(_z.decompress(data[start:end]))
        except Exception:
            continue
    return b"".join(parts)


def _read_records_builtin(path) -> list[dict]:
    """内置读者：不依赖 $DSH_HOME/bin/dsh_session.py（公共包用）。"""
    text = _decompress_frames(Path(path).read_bytes()).decode("utf-8", "replace")
    out = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def load_reader():
    """优先用 $DSH_HOME/bin/dsh_session.py；缺失时退到内置多帧读者。"""
    bin_dir = DSH_HOME / "bin"
    if str(bin_dir) not in sys.path:
        sys.path.insert(0, str(bin_dir))
    try:
        from dsh_session import read_records  # type: ignore
        return read_records
    except Exception:
        return _read_records_builtin


def dedupe_session_files(files: list[Path]) -> tuple[list[Path], int]:
    """同一会话目录可能有多份转录（`session.jsonl.zstd` + `session.v4.jsonl.zstd`）。

    2026-11-06 实测（独立复核发现，3 个目录）：v4 是旧转录的**超集**
    （034cd3ca: v4 1,810 事件 ⊇ 旧 147；5a442e31: 两者 288 事件全同；ddc4701f: 皆空）。
    ⇒ 一旦同一目录出现多份，**只取 `session.v4.jsonl.zstd`**（缺则取字典序第一），
      否则简单相加会重复计 tokens。返回 (保留文件, 被去重跳过的文件数)。
    """
    by_dir: dict[Path, Path] = {}
    skipped = 0
    for f in files:
        d = f.parent
        cur = by_dir.get(d)
        if cur is None:
            by_dir[d] = f
            continue
        skipped += 1
        prefer = "session.v4.jsonl.zstd"
        if f.name == prefer and cur.name != prefer:
            by_dir[d] = f
    return sorted(by_dir.values()), skipped


def scan(since_ms: int, until_ms: int, caliber: str, max_files: int | None = None) -> dict:
    """扫描会话目录 → aggregate 结果（附扫描透明度计数）。"""
    read_records = load_reader()
    if read_records is None:
        print("🔴 退码 3：无法解压会话转录（需 Python ≥3.14 或 pip install zstandard）", file=sys.stderr)
        raise SystemExit(3)
    if not SESSIONS_DIR.is_dir():
        print(f"🔴 退码 3：会话目录不可读 {SESSIONS_DIR}", file=sys.stderr)
        raise SystemExit(3)

    files = sorted(SESSIONS_DIR.glob(SESSION_GLOB))
    if caliber == "plan":
        files = [f for f in files if f.parent.name.startswith("session-")]
    # 同目录多份转录 ⇒ 去重（v4 优先），防重复计数
    files, dual_skipped = dedupe_session_files(files)
    # 快速排除：最后写入时间早于窗口起点的会话不可能含窗口内事件
    files = [f for f in files if f.stat().st_mtime * 1000 >= since_ms]
    if max_files:
        files = files[:max_files]
    session_dirs = len({f.parent for f in files})
    records: list[dict] = []
    files_read = files_skipped = 0
    for f in files:
        try:
            recs = read_records(f)
        except Exception:
            files_skipped += 1
            continue
        files_read += 1
        sid = f.parent.name
        for r in recs:
            r["_sid"] = sid
        records.extend(recs)
    agg = aggregate(records, since_ms, until_ms)
    agg.update({
        "session_dirs": session_dirs, "files_read": files_read,
        "files_skipped": files_skipped, "files_dual_skipped": dual_skipped,
        "caliber": caliber,
    })
    return agg


# ── 自证 ──────────────────────────────────────────────────────────────────────
def selfcheck(verbose: bool = False) -> int:
    """合成夹具自证。⚪真阴性 = 「正确但不应被计入」的样本必须**不计**。"""
    results: list[tuple[str, bool, str]] = []

    def chk(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, bool(cond), detail))

    base = int(datetime(2026, 11, 1).timestamp() * 1000)
    H = 3_600_000
    since, until = base, base + 24 * H
    mark = lambda h, typ="assistant/message", tok=100, **kw: {  # noqa: E731
        "type": typ, "time": since + int(h * H), "_sid": kw.pop("sid", "s-1"),
        "data": {"usage": {"inputTokens": tok, "outputTokens": 0,
                           "cacheReadTokens": 0, "cacheWriteTokens": 0,
                           "totalTokens": tok, **kw.get("usage", {})},
                 **kw.get("data", {})},
    }

    # 正样本：窗口内 3 条 usage
    a = aggregate([mark(1, tok=100), mark(2, tok=200), mark(3, tok=300)], since, until)
    chk("正样本 tokens=600", a["totals"]["tokens"] == 600, str(a["totals"]["tokens"]))
    chk("正样本 calls=3", a["totals"]["calls"] == 3, str(a["totals"]["calls"]))
    chk("正样本 均值=200", abs(a["totals"]["avg_tokens_per_call"] - 200) < 1e-9)
    chk("正样本 会话数=1", len(a["sessions"]) == 1)

    # ⚪真阴性①：窗口外（早于 since / 晚于等于 until）**不得**计入
    b = aggregate([mark(-1, tok=999), mark(24, tok=999)], since, until)
    chk("⚪真阴性① 窗口外不计", b["totals"]["tokens"] == 0 and b["totals"]["calls"] == 0,
        f"tokens={b['totals']['tokens']} calls={b['totals']['calls']}")
    # 边界：until 为半开 ⇒ 恰在 until 的事件不计；until-1ms 计
    edge = aggregate([{"type": "assistant/message", "time": until, "_sid": "s",
                       "data": {"usage": {"totalTokens": 5}}},
                      {"type": "assistant/message", "time": until - 1, "_sid": "s",
                       "data": {"usage": {"totalTokens": 7}}}], since, until)
    chk("⚪真阴性② 半开区间边界", edge["totals"]["tokens"] == 7, str(edge["totals"]["tokens"]))

    # 负样本①：缺 totalTokens 时回退 i+o+cr+cw
    fb = aggregate([mark(1, usage={"totalTokens": None, "inputTokens": 10,
                                   "outputTokens": 20, "cacheReadTokens": 30,
                                   "cacheWriteTokens": 40})], since, until)
    chk("负样本① totalTokens 缺失回退", fb["totals"]["tokens"] == 100,
        str(fb["totals"]["tokens"]))

    # 负样本②：无 usage 的事件只计次数、不产生"调用"
    cnt = aggregate([{"type": "assistant/attempt", "time": since + H, "_sid": "s"},
                     {"type": "llm/retry", "time": since + H, "_sid": "s"},
                     {"type": "session/title", "time": since + H, "_sid": "s"}],
                    since, until)
    chk("负样本② 无 usage 不计调用", cnt["totals"]["calls"] == 0, str(cnt["totals"]["calls"]))
    chk("负样本② 计数类仍统计",
        cnt["counters"].get("attempts") == 1 and cnt["counters"].get("retries") == 1
        and cnt["counters"].get("titles") == 1, str(dict(cnt["counters"])))

    # 负样本③：compaction/summary 单独记账
    cp = aggregate([mark(1, typ="compaction/summary", tok=500)], since, until)
    chk("负样本③ compaction 单独记账",
        cp["counters"].get("compaction_tokens") == 500 and
        cp["by_type_tokens"].get("compaction/summary") == 500, str(dict(cp["counters"])))

    # 负样本④：多会话/按日切分（窗口放宽到 48h，覆盖跨日）
    win48 = since + 48 * H
    md = aggregate([mark(1, tok=10, sid="s-a"), mark(2, tok=20, sid="s-b"),
                    {"type": "assistant/message", "time": since + 25 * H, "_sid": "s-b",
                     "data": {"usage": {"totalTokens": 30}}}], since, win48)
    chk("负样本④ 会话切分", {s["session"]: s["tokens"] for s in md["sessions"]}
        == {"s-b": 50, "s-a": 10}, str([(s['session'], s['tokens']) for s in md['sessions']]))
    chk("负样本④ 跨日切分", [d["tokens"] for d in md["days"]] == [30, 30],
        str([(d["date"], d["tokens"]) for d in md["days"]]))

    # 负样本⑤：无时间戳记录计入 skipped，不污染读数
    sk = aggregate([{"type": "assistant/message", "data": {"usage": {"totalTokens": 9}}}],
                   since, until)
    chk("负样本⑤ 无时间戳跳过", sk["skipped_no_time"] == 1 and sk["totals"]["tokens"] == 0,
        f"skipped={sk['skipped_no_time']} tokens={sk['totals']['tokens']}")

    # 负样本⑥：expect-total 判定语义（相等 PASS / 超容差 FAIL）
    ok = check_expect({"tokens": 1000}, 1000, 0.01)
    bad = check_expect({"tokens": 1000}, 1020, 0.01)
    chk("负样本⑥ expect-total 相等 PASS", ok["ok"] and ok["deviation"] == 0, str(ok))
    chk("负样本⑥ expect-total 超容差 FAIL", not bad["ok"], str(bad))

    # 负样本⑦：CLI 窗口解析 —— 显式 --until 必须生效（回归 2026-11-06 曾出现的
    #          「scan 内把 until 写成 now ⇒ --until 被静默忽略」缺陷）
    ref_now = datetime(2026, 11, 6, 12, 0)
    w = resolve_window("2026-11-01", "2026-11-06T10:02:00", None, ref_now)
    chk("负样本⑦ --until 生效（不被 now 覆盖）",
        w == (parse_ts("2026-11-01"), parse_ts("2026-11-06T10:02:00")),
        f"{_fmt(w[0])} ~ {_fmt(w[1])}")
    w2 = resolve_window(None, None, 7, ref_now)
    chk("负样本⑦ --days 7 起点=今天-6 日 00:00",
        w2[0] == int(datetime(2026, 10, 31).timestamp() * 1000),
        _fmt(w2[0]))
    try:
        resolve_window("2026-11-06", "2026-11-01", None, ref_now)
        bad_win = False
    except ValueError:
        bad_win = True
    chk("负样本⑦ 非法窗口抛错（until<=since）", bad_win)

    # 负样本⑧：同目录多转录去重（v4 优先）—— 防「全时段」统计把两份转录相加
    P = lambda *p: Path(*p)  # noqa: E731
    kept, dual_sk = dedupe_session_files([
        P("/s/a/session.jsonl.zstd"), P("/s/a/session.v4.jsonl.zstd"),
        P("/s/b/session.jsonl.zstd"),
    ])
    names = sorted(str(k).replace(chr(92), "/") for k in kept)
    chk("负样本⑧ 双转录去重（v4 优先 · 每目录留 1）",
        names == ["/s/a/session.v4.jsonl.zstd", "/s/b/session.jsonl.zstd"] and dual_sk == 1,
        f"kept={names} skipped={dual_sk}")

    # 正样本②：真实数据可读性（不参与判定，只报告）
    reader = load_reader()
    real_note = "dsh_session 可导入" if reader else "🔴 dsh_session 不可导入"
    chk("真实读者可导入", reader is not None, real_note)

    failed = [r for r in results if not r[1]]
    print(f"_wishos_cost_report.py --selfcheck —— 合成夹具 {len(results)} 检 · "
          f"PASS {len(results) - len(failed)} / FAIL {len(failed)}")
    for name, passed, detail in results:
        if verbose or not passed:
            print(f"  {'✅' if passed else '🔴'} {name}" + (f"  [{detail}]" if detail else ""))
    return 0 if not failed else 2


def check_expect(totals: dict, expected: int, tolerance: float) -> dict:
    actual = totals["tokens"]
    dev = abs(actual - expected) / expected if expected else 1.0
    return {"expected": expected, "actual": actual, "deviation": dev,
            "tolerance": tolerance, "ok": dev <= tolerance}


# ── CLI ───────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="WishOS 成本读数（C1）：只读 DSH 会话转录，按日/按会话汇总 usage。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--since", help="窗口起点（本地时区）YYYY-MM-DD 或 YYYY-MM-DDTHH:MM[:SS]")
    p.add_argument("--until", help="窗口终点（半开，不含）YYYY-MM-DD 或 YYYY-MM-DDTHH:MM[:SS]")
    p.add_argument("--days", type=int, help="便捷：窗口=今天-0 起往前 N 天（含今天）")
    p.add_argument("--caliber", choices=("full", "plan"), default="full",
                   help="full=全部会话目录（默认）；plan=只扫 session-* 目录（复现 11-06 规划基线）")
    p.add_argument("--json", action="store_true", help="输出 JSON（机器可读）")
    p.add_argument("--top", type=int, default=8, help="会话 Top N（默认 8；0=不列）")
    p.add_argument("--expect-total", type=int,
                   help="S4 硬校验：期望 tokens 总量；超容差 ⇒ 退码 2")
    p.add_argument("--tolerance", type=float, default=0.01, help="expect-total 容差（默认 0.01）")
    p.add_argument("--selfcheck", action="store_true", help="合成夹具自证（含⚪真阴性）")
    p.add_argument("--verbose", action="store_true", help="selfcheck 打印全部检查项")
    p.add_argument("--max-files", type=int, help="仅用于自证/排障：限制扫描文件数")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selfcheck:
        return selfcheck(args.verbose)

    now = datetime.now()
    try:
        since_ms, until_ms = resolve_window(args.since, args.until, args.days, now)
    except (ValueError, TypeError) as e:
        print(f"🔴 退码 2：窗口参数非法 —— {e}", file=sys.stderr)
        return 2

    agg = scan(since_ms, until_ms, args.caliber, args.max_files)
    expect = None
    rc = 0
    if args.expect_total is not None:
        expect = check_expect(agg["totals"], args.expect_total, args.tolerance)
        if not expect["ok"]:
            rc = 2

    if args.json:
        payload = dict(agg)
        payload["generated_at"] = _fmt(int(now.timestamp() * 1000))
        payload["check"] = expect
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        print(f"# WishOS 成本读数（C1）· 生成于 {_fmt(int(now.timestamp() * 1000))}")
        print()
        print(render_md(agg, args.caliber, args.top, expect))
        if expect and not expect["ok"]:
            print()
            print(f"🔴 退码 2：expect-total 未通过（偏差 {expect['deviation'] * 100:+.4f}% "
                  f"> ±{expect['tolerance'] * 100:.1f}%）")
    return rc


if __name__ == "__main__":
    sys.exit(main())
