# -*- coding: utf-8 -*-
"""WishOS + v12-core 一套到底验证器（只读 · 可复跑 · 2026-11-02 v1.1）

设计口径（与项目既有件一致，不另造判据）：
  L0 静态/骨架层（本件主体）：复用 `_wishos_gate.py`（E1~E7）+ `_v12core_accept.py`（A~F）+
     2026-11-02 耦合指标 + 技能目录成本/数量 + 基线 md5 漂移 + 126 未挂核对。
  L1 运行时目录层（--session / --auto）：从 DSH 会话 jsonl.zstd 里读**生效预设**（事件 agent-preset/selected；header 只记创建默认值）与
     `<available_skills>` 目录，判据 = 「preset 两根的 22 件一件不缺」+「无旧体系件泄漏」；
     preset 之外的件（宿主插件注册 / 运行时注册）只报告、不判红（不受 includeDefaultRoots 管）。

  🔧 v1.1（2026-11-02 · 三处判据缺陷修正；v1.0 原件见 _wishos_verify.py.bak-20261102-1615）：
     ① 预设锚错：v1.0 读会话 header.agentPreset，实测该字段只记**创建时默认值**（恒 'standard'），
        GUI 里选的预设在事件 `{"type":"agent-preset/selected","data":{"agentPreset":…}}` 里
        ⇒ --auto 永远搜不到自定义预设会话（永久假红）。改：事件优先、header 回退。
     ② 期望集过窄：v1.0 要求目录**恰好 22**。运行时目录 = preset 两根 22 + 宿主插件注册件
        （remotion-* / diagnose-windows-sandbox-acl）+ 运行时注册件（p0-probe-runtime）；
        includeDefaultRoots:false 只作用于**文件系统根**，管不到后两类 ⇒ 等值必然假红。
     ③ 取块失配：v1.0 用 rfind("<available_skills>")，正文引用该标记时取到引用文本
        （验证矩阵文档 L61 就写着它）⇒ 解析 0 件；且日志里目录块行分隔是**转义** `\\n`
        （JSON 字符串内），真换行正则匹配不到。改：取「真目录块」而非最后一个标记。

  🔧 v1.2（2026-11-02T16:4x，独立复核 3 处缺口修正；v1.1 见 git 无版本库，原件 .bak-20261102-1615）：
     ④ 取块仍按**位置**（「最后一个 ≥15 条 bullet 块」）⇒ 真块只 8 件、其后某条 tool/result
        回显 22 件时会把回显当目录（**假绿**，复核合成实测）。改：按**来源**锚定 —— 真目录块只在
        `type=user/message` 的注入事件里；找不到同形事件才退回位置兜底。
     ⑤ 旧件黑名单写死 6 名 ⇒ 漏判：`autonomous-flywheel` / `class-brain-coordinator` 混入时判绿
        （实测它们在真实会话目录里确有；写死的 v12-router / shutdown_protocol 反而从未出现）。
        改：旧件全集 = **扫各技能根目录**（v12 根 + 用户根 + 该会话 cwd 的工作区根）− 22 件。
     ⑥ `CATALOG_MIN=15` 反噬诊断：缺 ≥8 件时会话只余 <15 条 ⇒ 报「无目录块（可能没跑过）」，
        把「技能根没挂」误诊成「会话没跑」。改：来源锚定后不再用条数当门槛，<15 也照常报缺件。
     ⑦ `--auto` 双窗口无兜底：预设事件晚于前 40 帧、或会话被挤出最近 40 个 ⇒ 永久假红。
        改：head 扫不到时，对最近 12 个会话各做一次全量预设判定（成本只付在失败路径）。


用法：
  python _wishos_verify.py                      # L0 全检（默认；写 baseline 不覆盖）
  python _wishos_verify.py --update-baseline    # 首次/验收通过后写基线 md5（唯一写盘动作）
  python _wishos_verify.py --session <sessionId>  # L0 + 指定会话的 L1
  python _wishos_verify.py --auto               # L0 + 找最近「生效 preset=wishos」的会话做 L1
  python _wishos_verify.py --json               # 机器可读摘要（stdout）
  python _wishos_verify.py --selftest           # 自证：目录解析/耦合计数/期望集合（不碰真配置）

退出码：0 全过 / 2 有失败 / 3 环境不可读
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOME = os.path.expanduser("~")
DSH_HOME = os.environ.get("DSH_HOME") or os.path.join(HOME, ".dsh")
DSH_PROFILE = os.environ.get("DSH_PROFILE") or "web"
WISHOS_ROOT = os.environ.get("WISHOS_ROOT") or os.path.join(os.getcwd(), "wishos")
DSH = DSH_HOME
WISH_ROOT = os.path.join(DSH, ".agent-presets", "wishos")
WISH_SKILLS = os.path.join(WISH_ROOT, "skills")
CORE_SKILLS = os.path.join(WISH_ROOT, "v12-core", "skills")
V12_SKILLS = os.path.join(DSH, ".agent-presets", "v12", "skills")
PATCH = os.path.join(DSH, "profiles", DSH_PROFILE, "cordis.patch.yml")
SESSIONS = os.path.join(DSH, "sessions")
WORK = WISHOS_ROOT
TOOLS = os.path.join(WORK, "tools")
BASELINE_DIR = os.path.join(WORK, "baseline")
BASELINE = os.path.join(BASELINE_DIR, "wishos-baseline.json")
REPORT = os.path.join(WORK, "_tmp", "verify-report.md")
PROJECT = os.environ.get("WISHOS_PROJECT") or os.getcwd()   # 仅供自证取一个「真实工作区技能根」样本；真实会话的 cwd 由会话头给

W8 = ["w-calibrate", "w-capture", "w-enter", "w-evolve",
      "w-recall", "w-router", "w-watchdog", "w-wish"]
V14 = ["attention-failure-guard", "criteria-design-standard",
       "declared-value-drift-guard", "doc-plan-protocol", "four-rules-v3",
       "info-analyst", "introspect-guard", "memory-efficiency", "plan",
       "plan-auditor", "plan-executor", "plan-template", "session-guard",
       "shutdown-protocol"]
EXPECT22 = sorted(W8 + V14)
KNOWN_V12_ONLY = ["v12-router", "intel-analyst", "brain-daemon",
                  "knowledge-retrieve", "knowledge-capture", "shutdown_protocol"]
CATALOG_CHAR_BUDGET = 12000
KNOWN_RESIDUAL_LINES = {  # 2026-11-02 W1-c 裁定保留的 2 处耦合指标残留
    "four-rules-v3": [832, 1190],
}
COUPLING_PATS = [
    ("P1", re.compile(r"[A-Za-z]:\\Users\\64908\\\.workbuddy", re.I)),
("P2", re.compile(os.environ.get("WISHOS_EXTRA_COUPLING_RE") or r"zzz_no_match_zzz")),
    ("P3", re.compile(r"~[/\\]\.workbuddy", re.I)),
]


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8-sig", errors="replace")


def skill_files():
    """返回 [(root_tag, dir_name, SKILL.md path)]，与 dsh-skill-filesystem 发现同口径。"""
    out = []
    for tag, root in (("w", WISH_SKILLS), ("c", CORE_SKILLS)):
        if not os.path.isdir(root):
            continue
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d, "SKILL.md")
            if os.path.isdir(os.path.join(root, d)) and os.path.isfile(p):
                out.append((tag, d, p))
    return out


def frontmatter_len(text):
    """目录成本口径：name + description + whenToUse 的字符数（YAML 块标量按落盘值算）。"""
    import yaml

    class L(yaml.SafeLoader):
        pass

    L.add_constructor("tag:yaml.org,2002:js", lambda l, n: l.construct_scalar(n))
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return 0, {}
    try:
        fm = yaml.load(m.group(1), Loader=L) or {}
    except Exception:
        return 0, {}
    n = sum(len(str(fm.get(k, ""))) for k in ("name", "description", "whenToUse"))
    return n, fm


def run_py(script, timeout=180):
    try:
        out = subprocess.run([sys.executable, script], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except Exception as e:  # noqa: BLE001
        return -1, "subprocess 异常: %s" % e


# ── L0 ────────────────────────────────────────────────────────────────
def check_l0():
    fails, warns, rows = [], [], []

    # 1) 既有两件门禁（不重复造判据）
    for name, script in (("_wishos_gate.py", os.path.join(TOOLS, "_wishos_gate.py")),
                         ("_v12core_accept.py", os.path.join(TOOLS, "_v12core_accept.py"))):
        if not os.path.isfile(script):
            fails.append(("GATE", "缺件: " + script))
            continue
        rc, out = run_py(script)
        ok = rc == 0
        rows.append(("gate", "%s rc=%d" % (name, rc)))
        if not ok:
            fails.append(("GATE", "%s rc=%d（输出尾部: %s）" % (name, rc, out.strip().splitlines()[-1:] or "")))

    # 2) 技能目录: 22 = 8 + 14
    files = skill_files()
    tags = {"w": [d for t, d, _ in files if t == "w"], "c": [d for t, d, _ in files if t == "c"]}
    if sorted(tags["w"]) != sorted(W8):
        fails.append(("E", "w-* 目录不符: %r" % sorted(tags["w"])))
    if sorted(tags["c"]) != sorted(V14):
        fails.append(("E", "v12-core 不符: %r" % sorted(tags["c"])))
    if len(files) != 22:
        fails.append(("E", "可加载技能数=%d（应 22）" % len(files)))
    rows.append(("E", "可加载技能 = %d（8 + 14）" % len(files)))

    # 3) 目录成本（每轮注入成本）
    total = 0
    per = []
    for tag, d, p in files:
        n, fm = frontmatter_len(read(p))
        total += n
        per.append((d, n, len(str(fm.get("description", "")))))
    rows.append(("COST", "22 件目录 ≈%d 字符 ≈%d tok/轮（预算 %d）"
                 % (total, total // 2, CATALOG_CHAR_BUDGET)))
    if total > CATALOG_CHAR_BUDGET:
        fails.append(("COST", "目录成本 %d 字符 > 预算 %d（先看 description 最长的件）"
                      % (total, CATALOG_CHAR_BUDGET)))
    fat = sorted(per, key=lambda x: -x[2])[:3]
    warns.append(("COST", "description 最长三件: " + ", ".join("%s=%d字符" % (d, n) for d, _, n in fat)))

    # 4) 耦合指标（2026-11-02 口径；W1-c 后应只剩 2 处保留行）
    hits = []
    for tag, d, p in files:
        for i, line in enumerate(read(p).splitlines(), 1):
            for t, pat in COUPLING_PATS:
                if pat.search(line):
                    hits.append((d, i, t))
    known = sum(1 for d, i, _ in hits if i in KNOWN_RESIDUAL_LINES.get(d, []))
    if len(hits) != 2 or known != 2:
        fails.append(("PATHS", "耦合命中 %d 处（应恰 2 处已知保留行）: %r"
                      % (len(hits), [(d, i) for d, i, _ in hits[:8]])))
    rows.append(("PATHS", "WorkBuddy/正本耦合 = %d 处（余 2 处为 L832 声明 + L1190 历史行）" % len(hits)))

    # 5) 预设与旧体系未动
    n12 = len([d for d in os.listdir(V12_SKILLS) if os.path.isdir(os.path.join(V12_SKILLS, d))]) \
        if os.path.isdir(V12_SKILLS) else -1
    if n12 != 56:
        fails.append(("V12", "v12 预设技能数=%d（应 56）" % n12))
    rows.append(("V12", "v12 预设技能数 = %d（未动）" % n12))
    ptxt = read(PATCH) if os.path.isfile(PATCH) else ""
    if "v12-package-20261102" in ptxt:
        fails.append(("126", "patch 出现 126 解包副本路径"))
    rows.append(("126", "patch 无 126 全量路径"))
    if ("v12-core\\skills" not in ptxt) or ("wishos\\skills" not in ptxt):
        fails.append(("PATCH", "patch 未同时含两个技能根"))
    rows.append(("PATCH", "双技能根在 patch 中（wishos\\skills + wishos\\v12-core\\skills）"))

    # 6) 基线漂移（仅报告；改了技能就需重新验收并 --update-baseline）
    drift = []
    if os.path.isfile(BASELINE):
        try:
            base = json.loads(read(BASELINE))
            for key, rec in (base.get("files") or {}).items():
                if not os.path.isfile(key):
                    drift.append("缺件 " + key)
                elif md5(key) != rec:
                    drift.append(os.path.basename(os.path.dirname(key)))
        except Exception as e:  # noqa: BLE001
            warns.append(("BASE", "基线读取失败: %s" % e))
        if drift:
            warns.append(("BASE", "技能文件相对基线有改动（需重新验收并刷基线）: %r" % drift))
        else:
            rows.append(("BASE", "22 件技能 md5 与基线一致（baseline: %s）" % os.path.basename(BASELINE)))
    else:
        warns.append(("BASE", "尚无基线（首次验收通过后跑 --update-baseline）"))

    return fails, warns, rows


# ── L1：会话运行时目录 ────────────────────────────────────────────────
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
CATALOG_MIN = 15   # 真目录块下限（正文引用通常只提 1~3 件）
HEAD_FRAMES = 40   # --auto 扫会话时只解前若干帧（header / 预设选择事件都在首几帧）


def _decompress_session(path):
    try:
        from compression import zstd  # Python >= 3.14
        return zstd.decompress(open(path, "rb").read()).decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("解压失败（需 Python≥3.14 标准库 compression.zstd）: %s" % e)


def _frame_bounds(raw):
    """会话 jsonl.zstd 是「每帧一次追加」⇒ 按 magic 切帧，返回 [(start, end)]。"""
    offs, i = [], raw.find(ZSTD_MAGIC)
    while i >= 0:
        offs.append(i)
        i = raw.find(ZSTD_MAGIC, i + 4)
    return [(o, offs[k + 1] if k + 1 < len(offs) else len(raw))
            for k, o in enumerate(offs)]


def session_probe(path, max_frames=HEAD_FRAMES):
    """(header, head_text)：只解前若干帧（全量解压大会话很慢，--auto 要扫多个会话）。

    ⚠️ Node 侧 zstdDecompressSync 只返回第一帧；全量解压必须走 Python（≥3.14）。
    """
    from compression import zstd
    raw = open(path, "rb").read()
    fr = _frame_bounds(raw)
    if not fr:
        raise RuntimeError("非 zstd 文件")
    buf = []
    for a, b in fr[:max_frames]:
        try:
            buf.append(zstd.decompress(raw[a:b]))
        except Exception:  # 尾帧可能不完整 / 误判帧界
            break
    text = (_decompress_session(path) if not buf  # 首帧都解不开 -> 退回全量
            else b"".join(buf).decode("utf-8", errors="replace"))
    first = text.splitlines()[0] if text else ""
    try:
        return json.loads(first), text
    except Exception:  # noqa: BLE001
        return {}, text


def read_session_header(path):
    """兼容旧名：返回 (header, head_text)。"""
    return session_probe(path)


def session_preset(header, text):
    """返回 (生效预设, 来源)。来源 ∈ {'event', 'header'}。

    事件口径：`{"type":"agent-preset/selected","data":{"agentPreset":"wishos"}}`（取最后一次）。
    为什么不只信 header：header 记的是**创建时值** —— GUI 会话先创建、后选预设 ⇒ 恒 'standard'；
    而在 wishos 上下文里 spawn 的子会话 header 就是 'wishos' 且可能没有事件
    ⇒ 事件优先、header 回退两边都要（任何一边写成公理都会误判另一形态）。
    """
    sels = re.findall(
        r'"type"\s*:\s*"agent-preset/selected"[^\n]*?"agentPreset"\s*:\s*"([^"]+)"', text)
    if sels:
        return sels[-1], "event"
    return header.get("agentPreset"), "header"


BULLET = re.compile(r"(?:^|\\n|\n)\s*-\s+`([a-z0-9][a-z0-9-]*)`\s*:", re.M)


def parse_catalog(text):
    """取**真目录块**的名单：先按来源（user/message 注入事件），再按位置兜底。

    两轮实测坑（v1.1 → v1.2）：
      ① v1.0 用 rfind 取最后一个标记 ⇒ 正文/文档引用该标记时解析 0 件（假红）；
      ② v1.1 用「最后一个 ≥15 条 bullet 块」仍按**位置**取 ⇒ 真块只 8 件、其后某条
         tool/result 回显 22 件时，会拿回显当目录（**假绿**，复核合成实测）。
    ⇒ v1.2：真目录块只出现在 `type=user/message` 的注入事件（system-reminder）里，按来源锚定；
      条数不再当门槛（小目录块照常返回，交给判据报「缺 N 件」），只在没有同形事件时退回位置兜底。
    """
    best = None
    for line in text.splitlines():
        if "<available_skills>" not in line:
            continue
        try:
            ev = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if ev.get("type") != "user/message":   # 工具回显 / assistant 引用不算目录
            continue
        for m in re.finditer(r"<available_skills>(.{0,40000}?)</available_skills>", line, re.S):
            names = sorted(set(BULLET.findall(m.group(1))))
            if names:
                best = names
    if best is not None:
        return best
    # 兜底（旧日志 / 非事件文本）：按位置取最后一个够大的块
    for m in re.finditer(r"<available_skills>(.{0,40000}?)</available_skills>", text, re.S):
        names = sorted(set(BULLET.findall(m.group(1))))
        if len(names) >= CATALOG_MIN:
            best = names
    return best


def _dir_names(root):
    """某技能根下的目录名集合（跳过 .git / .skm-backups 一类隐藏项）。"""
    if not root or not os.path.isdir(root):
        return set()
    return {d for d in os.listdir(root)
            if not d.startswith(".") and os.path.isdir(os.path.join(root, d))}


def legacy_names(cwd=None):
    """旧体系件名全集（单一真源 = **各技能根目录**，不在代码里写死名单）。

    2026-11-02 复核实测：v1.1 写死的 6 名漏了 `autonomous-flywheel` / `class-brain-coordinator`
    （这两件在真实会话目录里确有），而写死的 `v12-router` / `shutdown_protocol` 在真实目录里
    从未出现 ⇒ 黑名单窄了直接漏判（假绿）。改为扫目录：v12 预设根 + 用户根 + 该会话 cwd 的
    工作区根，减去本预设 22 件。插件 / 运行时注册件不在这些目录里，不会被误判为旧件。
    """
    names = set(KNOWN_V12_ONLY)   # 兜底补名（目录不可读时仍能判）
    for root in (V12_SKILLS, os.path.join(DSH, "skills")):
        names |= _dir_names(root)
    if cwd:
        names |= _dir_names(os.path.join(cwd, ".dsh", "skills"))
    return sorted(names - set(EXPECT22))


def catalog_judge(cat, legacy=None):
    """L1 判据（可证伪）：preset 两根的 22 件**一件不缺** + **无旧体系件** ⇒ 通过。

    为什么不是「恰好 22 相等」：运行时目录 = preset 两根 22 + 宿主插件注册件
    （remotion-* / diagnose-windows-sandbox-acl）+ 运行时注册件（p0-probe-runtime），
    后两类不受 `includeDefaultRoots:false` 管（该选项只作用于文件系统根）⇒ 等值必假红。
    返回 (fails, missing, leaked, extras)。
    """
    fails, got = [], set(cat)
    legacy = set(legacy) if legacy is not None else set(legacy_names())
    missing = sorted(set(EXPECT22) - got)
    leaked = sorted(n for n in got if n in legacy)
    extras = sorted(got - set(EXPECT22) - set(leaked))
    if missing:
        fails.append(("L1", "preset 技能缺失 %d 件: %r" % (len(missing), missing[:10])))
    if leaked:
        fails.append(("L1", "旧体系件泄漏 %d 件: %r" % (len(leaked), leaked[:10])))
    return fails, missing, leaked, extras


def extras_brief(extras):
    """额外件缩写：remotion-* 合并计数，其余列名（报告行不要太长）。"""
    if not extras:
        return "0 件"
    rem = [n for n in extras if n.startswith("remotion-")]
    other = [n for n in extras if not n.startswith("remotion-")]
    parts = (["remotion-*×%d" % len(rem)] if rem else []) + other
    return "%d 件（%s）" % (len(extras), "、".join(parts))


def find_sessions():
    pats = [os.path.join(SESSIONS, "*", "*", "session*.jsonl.zstd"),
            os.path.join(SESSIONS, "*", "*", "session.jsonl.zstd")]
    seen = {}
    for pat in pats:
        for p in glob.glob(pat):
            seen[p] = os.path.getmtime(p)
    return [p for p, _ in sorted(seen.items(), key=lambda x: -x[1])]


def session_meta(path):
    header, text = read_session_header(path)
    return header, text


def full_session_text(path):
    return _decompress_session(path)


def check_l1_session(path, expect_preset="wishos"):
    fails, warns, rows = [], [], []
    try:
        header, head = session_probe(path)
    except Exception as e:  # noqa: BLE001
        return [("L1", "读取会话失败: %s" % e)], [], []
    preset, src = session_preset(header, head)
    sid = header.get("id") or os.path.basename(os.path.dirname(path))
    if expect_preset and preset != expect_preset:
        try:  # 前若干帧没覆盖到选择事件时，全量再读一次（只在这里付一次代价）
            p2, s2 = session_preset(header, full_session_text(path))
            if p2 == expect_preset:
                preset, src = p2, s2
        except Exception:  # noqa: BLE001
            pass
    rows.append(("L1", "session=%s · 生效 agentPreset=%r（来源=%s；header 记 %r）· cwd=%r"
                 % (sid, preset, src, header.get("agentPreset"), header.get("cwd"))))
    if expect_preset and preset != expect_preset:
        fails.append(("L1", "生效 agentPreset=%r（来源=%s，应 %r）" % (preset, src, expect_preset)))
        return fails, warns, rows
    try:
        text = full_session_text(path)
    except Exception as e:  # noqa: BLE001
        return [("L1", "解压会话失败: %s" % e)], [], rows
    cat = parse_catalog(text)
    if cat is None:
        fails.append(("L1", "会话日志里找不到可解析的 <available_skills> 目录块"
                            "（该会话可能尚未跑过一轮；若已跑过 ⇒ 目录块形态变了，先修解析器）"))
        return fails, warns, rows
    legacy = legacy_names(header.get("cwd"))
    jfails, missing, leaked, extras = catalog_judge(cat, legacy)
    rows.append(("L1", "目录可见 %d 件 = preset %d（8 w-* + 14 v12-core）+ 非 preset 根 %s"
                 % (len(cat), len(set(cat) & set(EXPECT22)), extras_brief(extras))))
    fails += jfails
    if not jfails:
        rows.append(("L1", "✅ preset 两根 22 件全在 · 旧体系 0 泄漏（旧件全集按目录扫，%d 名）"
                     % len(legacy)))
    return fails, warns, rows


def check_l1(session_id=None):
    files = find_sessions()
    if not files:
        return [("L1", "找不到会话日志目录: " + SESSIONS)], [], []
    if session_id:
        hits = [p for p in files if session_id in p]
        if not hits:
            return [("L1", "找不到会话: " + session_id)], [], []
        return check_l1_session(hits[0])
    # --auto ①：最近 40 个会话只看前 40 帧（预设选择事件通常就在第 2 帧）
    for p in files[:40]:
        try:
            header, head = session_probe(p)
        except Exception:  # noqa: BLE001
            continue
        if session_preset(header, head)[0] == "wishos":
            return check_l1_session(p)
    # --auto ②：兜底 —— 预设事件晚于前 40 帧（GUI 中途切预设）时，最近 12 个会话全量再判一次
    for p in files[:12]:
        try:
            header = session_probe(p)[0]
            if session_preset(header, full_session_text(p))[0] == "wishos":
                return check_l1_session(p)
        except Exception:  # noqa: BLE001
            continue
    return [("L1", "最近 40 个会话（前 40 帧）+ 最近 12 个会话（全量兜底）都没有生效 preset=wishos "
                  "的会话（口径：agent-preset/selected 事件，回退 header）→ 先在 GUI 新建一个 "
                  "WishOS 会话（并跑过至少一轮）再执行 --auto")], [], []


# ── 自证 ──────────────────────────────────────────────────────────────
def selftest():
    """自证 L1 判据的**真路径**（取块 / 预设锚 / 期望集），不碰真配置。

    教训（v1.0）：三条自证全是合成串，从不覆盖真会话的「转义换行目录块 / 引用标记 /
    header≠生效预设」⇒ L1 一路绿着却判不了真数。故每题都拿 v1.0 会踩的坏样本做输入。
    """
    bad = 0

    def chk(ok, msg):
        print("  %s %s" % ("✅" if ok else "🔴", msg))
        return 0 if ok else 1

    # ① 取块：真目录块在前、正文引用标记在后（v1.0 的 rfind 会取到引用文本 → 0 件）
    real = ("<available_skills>\\n"
            + "\\n".join("- `%s`: desc" % n for n in EXPECT22)
            + "\\n</available_skills>")
    tail = "读文档时引用了标记：<available_skills>\\n- `w-wish`: 示例\\n"   # 无闭合标签
    got = parse_catalog(real + "\n中间正文\n" + tail)
    bad += chk(got == sorted(EXPECT22), "① 取块：跳过引用、取真目录块（转义换行，22 件）")

    # ② 耦合计数：3 条合成行 → 恰 3 命中
    sample = ("x ~/.workbuddy/y\n<legacy-root>/z\nC:\\Users\\<user>\\.workbuddy\\q\n")
    _extra = re.compile(r"<legacy-root>")
    n = sum(len(pat.findall(sample)) for _, pat in COUPLING_PATS) + len(_extra.findall(sample))
    bad += chk(n == 3, "② 耦合计数（合成 3 处）实得 %d" % n)

    # ③ 期望集合：22 且无重名
    bad += chk(len(set(EXPECT22)) == 22, "③ 期望集合 22 件无重名")

    # ④ 预设锚：header=standard + 事件=wishos ⇒ 必须认成 wishos（来源 event）；无事件回退 header
    fake = ('{"type":"session","agentPreset":"standard"}\n'
            '{"type":"agent-preset/selected","seq":3,"data":{"agentPreset":"wishos"}}\n')
    hdr = json.loads(fake.splitlines()[0])
    p1, s1 = session_preset(hdr, fake)
    bad += chk(p1 == "wishos" and s1 == "event", "④ 预设锚：事件优先（%r/%s）" % (p1, s1))
    p2, s2 = session_preset(hdr, fake.splitlines()[0] + "\n")
    bad += chk(p2 == "standard" and s2 == "header", "④b 无事件时回退 header（%r/%s）" % (p2, s2))

    # ⑤ 期望集判据：22 + 插件/运行时件 ⇒ 不红；缺一件 ⇒ 红；混旧体系件 ⇒ 红
    f_ok = catalog_judge(EXPECT22 + ["remotion-create", "diagnose-windows-sandbox-acl",
                                     "p0-probe-runtime"])[0]
    f_miss = catalog_judge([x for x in EXPECT22 if x != "w-wish"])[0]
    f_leak = catalog_judge(EXPECT22 + ["brain-daemon"])[0]
    bad += chk((not f_ok) and bool(f_miss) and bool(f_leak),
               "⑤ 期望集判据：插件件不红、缺件/旧件必红（%d/%d/%d）"
               % (len(f_ok), len(f_miss), len(f_leak)))

    # ⑥ 旧件全集来自**目录扫**（不写死）：数量够 + 任意旧件名混入必红
    legacy = legacy_names(PROJECT if os.path.isdir(PROJECT) else None)
    f_l1 = catalog_judge(EXPECT22 + ["autonomous-flywheel"], legacy=legacy)[0]
    f_l2 = catalog_judge(EXPECT22 + ["class-brain-coordinator"], legacy=legacy)[0]
    bad += chk(len(legacy) >= 20 and bool(f_l1) and bool(f_l2),
               "⑥ 旧件全集按目录扫（%d 名）· 复核漏判的两名混入必红（%d/%d）"
               % (len(legacy), len(f_l1), len(f_l2)))

    # ⑦ 取块按**来源**：真块只 8 件 + 其后 tool/result 回显 22 件 ⇒ 必须取 8 件（v1.1 会取 22 = 假绿）
    def ev(t, names):
        return json.dumps({"type": t, "data": {
            "text": "<available_skills>\\n" + "\\n".join("- `%s`: desc" % n for n in names)
                    + "\\n</available_skills>"}}, ensure_ascii=False)
    small = sorted(EXPECT22)[:8]
    got = parse_catalog(ev("user/message", small) + "\n" + ev("tool/result", EXPECT22))
    bad += chk(got == small, "⑦ 取块按来源：工具回显 22 件不得冒充真块（实得 %d 件）"
               % (len(got) if got else 0))

    print("  " + ("✅ 自证 9 检通过" if bad == 0 else "🔴 自证未过（%d 处）" % bad))
    return 0 if bad == 0 else 2


# ── 报告 ──────────────────────────────────────────────────────────────
def render(fails, warns, rows, l1_on):
    lines = ["# WishOS + v12-core · 验证报告", "",
             "- 时间：%s" % __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
             "- 件：`%s`（只读聚合；L0=%s）" % (__file__, "L0+L1" if l1_on else "L0"),
             "- 判据来源：`_wishos_gate.py` E1~E7 · `_v12core_accept.py` A~F · 2026-11-02 耦合口径 ·"
             " L1 v1.2（预设锚=事件优先 · 期望集=⊇22 且无旧件 · 取块=来源锚定 · 旧件全集=扫目录）",
             "", "## 判定", "", "**%s**（失败 %d / 警告 %d）"
             % ("✅ 全过" if not fails else "🔴 未全过", len(fails), len(warns)), "",
             "| 层 | 读数 |", "|:--|:--|"]
    lines += ["| %s | %s |" % (k, v.replace("|", "\\|")) for k, v in rows]
    if warns:
        lines += ["", "## 警告（不阻断）", ""]
        lines += ["- 🔶 [%s] %s" % (k, v.replace("|", "\\|")) for k, v in warns]
    if fails:
        lines += ["", "## 失败项", ""]
        lines += ["- 🔴 [%s] %s" % (k, v.replace("|", "\\|")) for k, v in fails]
    lines += ["", ]
    return "\n".join(lines)


def write_baseline():
    os.makedirs(BASELINE_DIR, exist_ok=True)
    files = {}
    for tag, d, p in skill_files():
        files[p] = md5(p)
    doc = {"created_at": __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
           "patch": {"path": PATCH, "md5": md5(PATCH) if os.path.isfile(PATCH) else None},
           "skills": len(files), "files": files}
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("baseline -> %s（%d 件技能 + patch md5）" % (BASELINE, len(files)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=None)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=REPORT)
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if a.update_baseline:
        write_baseline()
        return 0

    fails, warns, rows = check_l0()
    l1_on = bool(a.session or a.auto)
    if l1_on:
        f2, w2, r2 = check_l1(a.session)
        fails += f2
        warns += w2
        rows += r2

    md = render(fails, warns, rows, l1_on)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(md)
    if a.json:
        print(json.dumps({"ok": not fails, "fails": fails, "warns": warns,
                          "rows": [[k, v] for k, v in rows]}, ensure_ascii=False, indent=1))
    else:
        print(md)
        print("\n报告 -> " + a.out)
        print("退出码 = " + ("0" if not fails else "2"))
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
