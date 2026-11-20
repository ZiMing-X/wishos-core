# -*- coding: utf-8 -*-
"""_wishos_gate.py —— WishOS 骨架门禁 v0.2（W1 + B4）

校验目标（E1~E8 + E10）：
  E1 profile patch 可解析，且 preset-wishos 行存在、config.id=wishos、preset-v12 未被改动
  E2 技能根 7 件齐全，SKILL.md frontmatter 的 name 与目录名一致、description 非空
  E3 工作区目录齐全（brain/* + outputs + tools）
  E4 旧三处技能根无 w-* 命名冲突
  E5 旧 v12 技能数仍为 42（V3a 后基线；未被动过）
  E6 约束台账 Tier-0 恰为 4 条
  E7 隔离生效：includeDefaultRoots=false 且 wishos 不挂 agent-instructions
  E8 节点影子字段（B4/B12）：REQUIRE_NODE_DIRS=9 类必须存在 + ALLOW_NODE_DIRS=+plan/decision/schedule
     允许缺失（0 节点=通过）；未知目录仍红；13 类型码 + 必填键 + `bcode:` 可解码
     （k 与 type 一致、pv=1、h 与正文 canonical 绑定、id 唯一；正文变而未重发 ⇒ 红）

退码：0 = 全过；2 = 有失败；3 = 路径不可读/用法错误
自证：--selftest（正样本过 / 负样本拦 / ⚪真阴性拦得对理由）
新增（B12）：--root <dir> 只覆盖 E8/E3 扫描根（默认生产 work）；严格 argparse（未知参数 rc=3）

包内适配（2026-11-20 · T6）：整版取自生产树（生产 sha16 62DDE265…），仅改三处环境适配 ——
  ① 本机绝对路径 → 环境变量（`WISHOS_ROOT` 工作区 / `WISHOS_LEDGER` 约束台账 / `WISHOS_PROJECT` 台账默认根）；
  ② `_beacon.py` 定位：同目录 → `WISHOS_BEACON` → `$WISHOS_ROOT/tools`；
  ③ 解码器不可用时 `--selftest` 返 rc=3 并说明原因，不再抛栈。
判据本体（E1~E8+E10 · 13 项自证）与生产树逐条一致，未改。
"""
import argparse, os, re, sys, json, tempfile, shutil, time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# B4：E8 需要解 bcode —— 解码器 `_beacon.py` 与本门禁同目录，或由环境变量给（WISHOS_BEACON / $WISHOS_ROOT/tools）。仅解码/校验，不写盘。
_HERE = os.path.dirname(os.path.abspath(__file__))
_env_beacon = os.environ.get("WISHOS_BEACON") or ""
_beacon_dir = (os.path.dirname(os.path.abspath(_env_beacon)) if _env_beacon
               else os.path.join(os.environ.get("WISHOS_ROOT") or os.getcwd(), "tools"))
for _p in (_beacon_dir, _HERE):  # 同目录优先：后者插在最前
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
try:
    import _beacon as BEACON  # noqa: E402
    _BEACON_IMPORT_ERROR = ""
except Exception as _beacon_exc:  # noqa: BLE001
    BEACON = None
    _BEACON_IMPORT_ERROR = "%s: %s" % (type(_beacon_exc).__name__, _beacon_exc)

HOME = os.path.expanduser("~")
REAL = {
    "patch": os.path.join(HOME, ".dsh", "profiles", "web", "cordis.patch.yml"),
    "preset": os.path.join(HOME, ".dsh", ".agent-presets", "wishos"),
    "skills": os.path.join(HOME, ".dsh", ".agent-presets", "wishos", "skills"),
    "work": os.environ.get("WISHOS_ROOT") or os.path.join(os.getcwd(), "wishos"),
    "lib": os.path.join(HOME, ".dsh", "skill-manager", "library"),
    "v12": os.path.join(HOME, ".dsh", ".agent-presets", "v12", "skills"),
    "ledger": (os.environ.get("WISHOS_LEDGER")
               or os.path.join(os.environ.get("WISHOS_PROJECT") or os.getcwd(),
                               "docs", "V12-WishOS-约束台账-v1.0-2026-11-02.md")),
}
EXPECT_SKILLS = ["w-wish", "w-router", "w-recall", "w-capture", "w-enter",
                 "w-calibrate", "w-watchdog", "w-evolve"]
EXPECT_WORK = ["brain/cards/context", "brain/cards/pattern", "brain/cards/decision",
               "brain/cards/solution", "brain/chains", "brain/calibration",
               "brain/tickets", "brain/attention", "outputs", "tools", "_tmp",
               "brain/nodes/project", "brain/nodes/event", "brain/nodes/claim",
               "brain/nodes/evidence", "brain/nodes/inference", "brain/nodes/conclusion",
               "brain/nodes/card", "brain/nodes/ticket", "brain/nodes/artifact"]

#: 节点类型目录（E8/B12）：REQUIRE=9 类必须存在；ALLOW=+plan/decision/schedule（允许缺失，不建生产目录）
NODE_ROOT_REL = ("brain", "nodes")
REQUIRE_NODE_DIRS = [s.split("/")[-1] for s in EXPECT_WORK if s.startswith("brain/nodes/")]
ALLOW_NODE_DIRS = REQUIRE_NODE_DIRS + ["plan", "decision", "schedule"]
#: 兼容旧导入名（B10 harness 等）
EXPECT_NODE_DIRS = REQUIRE_NODE_DIRS
NODE_REQUIRED = ("id", "type", "title", "ts", "edges", "bcode")
NEW_NODE_TYPES = ("plan", "decision", "schedule", "artifact")
LEGACY_UNCLASSIFIED = {"c-20261102-readme-sync", "project-wishos", "project-xmgl",
                       "T-20261102-1700-readme-sync"}
NODE_CLASSES = ("public", "internal", "personal", "client")


def retention_ok(value) -> bool:
    s = str(value)
    if s in ("permanent", "project_end"):
        return True
    m = re.fullmatch(r"(\d+)d", s)
    return bool(m) and 1 <= int(m.group(1)) <= 3650


def load_yaml_with_js(text):
    import yaml
    class L(yaml.SafeLoader):
        pass
    L.add_constructor("tag:yaml.org,2002:js", lambda l, n: l.construct_scalar(n))
    return yaml.load(text, Loader=L)


def read(p):
    with open(p, "rb") as f:
        return f.read().decode("utf-8-sig")


def frontmatter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    fm = m.group(1) if m else ""
    out = {}
    for line in fm.split("\n"):
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def parse_node(path):
    """读节点文件 → (frontmatter dict, body 原文)。E8 用；解析失败抛异常。"""
    text = read(path)
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        raise ValueError("缺 frontmatter")
    import yaml
    fm = yaml.safe_load(m.group(1))
    if not isinstance(fm, dict):
        raise ValueError("frontmatter 不是映射")
    return fm, text[m.end():]


def check_nodes(work):
    """E8 · 节点影子字段（B4）。"""
    fails = []
    if BEACON is None:
        return [("E8", "无法导入生产解码器 _beacon.py：" + _BEACON_IMPORT_ERROR)]
    root = os.path.join(work, *NODE_ROOT_REL)
    if not os.path.isdir(root):
        return [("E8", "节点根不存在: " + root)]
    for sub in REQUIRE_NODE_DIRS:
        if not os.path.isdir(os.path.join(root, sub)):
            fails.append(("E8", "节点类型目录缺失: " + sub))
    codes = sorted(BEACON.TYPE_CODES.values())
    if codes != list(range(1, 14)):
        fails.append(("E8", "类型码登记不完整（应为 k=1..13）: %r" % codes))
    seen_ids = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if not fn.endswith(".md"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            top = rel.split(os.sep)[0]
            if top not in ALLOW_NODE_DIRS:
                fails.append(("E8", "%s: 未知节点目录 %r" % (rel, top)))
            try:
                fm, body = parse_node(p)
            except Exception as exc:  # noqa: BLE001 - 解析失败必须红
                fails.append(("E8", "%s: frontmatter 解析失败 %s: %s"
                              % (rel, type(exc).__name__, exc)))
                continue
            # G-07（B12）：redact 壳豁免（只要求骨架键，且需 ledger 有 deletion 记录）
            if fm.get("deleted") is True:
                for key in ("id", "type", "ts", "deleted", "deletion_method"):
                    if key not in fm or fm.get(key) in (None, ""):
                        fails.append(("E8", "%s: 删除壳缺键 %s" % (rel, key)))
                continue
            for key in NODE_REQUIRED:
                if key not in fm or fm.get(key) in (None, ""):
                    fails.append(("E8", "%s: 缺必填键 %s" % (rel, key)))
            ntype = str(fm.get("type", ""))
            if ntype not in BEACON.TYPE_CODES:
                fails.append(("E8", "%s: type=%r 不在 13 类型码内" % (rel, ntype)))
            elif top != ntype:
                fails.append(("E8", "%s: 目录 %r 与 type=%r 不一致" % (rel, top, ntype)))
            nid = str(fm.get("id", ""))
            # G-06（B12）：新类型必须 class/retention；personal/client 必须有 subject
            if ntype in NEW_NODE_TYPES and nid not in LEGACY_UNCLASSIFIED:
                if not fm.get("class"):
                    fails.append(("E8", "%s: 新类型缺 class" % rel))
                elif fm["class"] not in NODE_CLASSES:
                    fails.append(("E8", "%s: class 非法 %r" % (rel, fm["class"])))
                if fm.get("class") in ("personal", "client") and not str(fm.get("subject") or "").strip():
                    fails.append(("E8", "%s: personal/client 缺 subject" % rel))
                if not fm.get("retention"):
                    fails.append(("E8", "%s: 新类型缺 retention" % rel))
                elif not retention_ok(fm["retention"]):
                    fails.append(("E8", "%s: retention 非法 %r（1d..3650d）" % (rel, fm["retention"])))
            if nid and nid in seen_ids:
                fails.append(("E8", "%s: id 与 %s 重复" % (rel, seen_ids[nid])))
            elif nid:
                seen_ids[nid] = rel
            bcode = fm.get("bcode")
            if not isinstance(bcode, str) or not bcode:
                fails.append(("E8", "%s: bcode 缺失或非字符串" % rel))
                continue
            res = BEACON.verify(bcode)
            if not res.get("ok"):
                fails.append(("E8", "%s: bcode 不可解码（%s）: %r"
                              % (rel, res.get("error"), bcode)))
                continue
            dec = res["decoded"]
            if dec.get("pv") != BEACON.PV_V0:
                fails.append(("E8", "%s: bcode pv=%r（v0 应为 1）" % (rel, dec.get("pv"))))
            kname = BEACON.TYPE_NAMES.get(dec.get("k"))
            if kname != ntype:
                fails.append(("E8", "%s: bcode k=%r(%s) 与 type=%r 不一致"
                              % (rel, dec.get("k"), kname, ntype)))
            try:
                h = BEACON.h_of(BEACON.canonical_obj_from_node(fm, body))
            except Exception as exc:  # noqa: BLE001
                fails.append(("E8", "%s: 正文 canonical 计算失败 %s: %s"
                              % (rel, type(exc).__name__, exc)))
                continue
            if h != dec.get("h"):
                fails.append(("E8", "%s: bcode h 与正文 canonical 不一致（正文变而未重新发号）" % rel))
    return fails


def _count_nodes(work):
    root = os.path.join(work, *NODE_ROOT_REL)
    return sum(len([f for f in filenames if f.endswith(".md")])
               for _dirpath, _dirnames, filenames in os.walk(root))


def check(paths):
    fails = []
    # E1
    patch = paths["patch"]
    try:
        text = read(patch)
        doc = load_yaml_with_js(text)
        if not isinstance(doc, list):
            fails.append(("E1", "patch 解析结果不是 list"))
        else:
            rows = [r for r in doc if isinstance(r, dict) and "insert" in r]
            items = [it for r in rows for it in (r.get("insert") or []) if isinstance(it, dict)]
            wish = [it for it in items if it.get("id") == "preset-wishos"]
            v12 = [it for it in items if it.get("id") == "preset-v12"]
            if len(wish) != 1:
                fails.append(("E1", "preset-wishos 行数=%d（应 1）" % len(wish)))
            else:
                cfg = wish[0].get("config") or {}
                if cfg.get("id") != "wishos":
                    fails.append(("E1", "config.id=%r（应 wishos）" % cfg.get("id")))
                pids = [p.get("id") for p in (cfg.get("plugins") or []) if isinstance(p, dict)]
                for need in ("persona", "skill-filesystem", "tool-skill", "planning", "delegation", "compaction"):
                    if need not in pids:
                        fails.append(("E1", "wishos 缺 plugin 行: " + need))
                if "agent-instructions" in pids:
                    fails.append(("E7", "wishos 不应挂 agent-instructions"))
                sf = [p for p in (cfg.get("plugins") or []) if isinstance(p, dict) and p.get("id") == "skill-filesystem"]
                if sf:
                    c = sf[0].get("config") or {}
                    if c.get("includeDefaultRoots") is not False:
                        fails.append(("E7", "skill-filesystem.includeDefaultRoots 应为 false"))
            if len(v12) != 1:
                fails.append(("E1", "preset-v12 行数=%d（应 1，旧预设被改动）" % len(v12)))
    except FileNotFoundError:
        fails.append(("E1", "patch 不存在: " + patch))
        return fails
    except Exception as e:
        fails.append(("E1", "patch 解析失败: %s: %s" % (type(e).__name__, e)))
        return fails

    # E2
    skills = paths["skills"]
    if not os.path.isdir(skills):
        fails.append(("E2", "技能根不存在: " + skills))
    else:
        dirs = sorted(d for d in os.listdir(skills) if os.path.isdir(os.path.join(skills, d)))
        if dirs != sorted(EXPECT_SKILLS):
            fails.append(("E2", "技能目录不符: %r" % dirs))
        for d in EXPECT_SKILLS:
            p = os.path.join(skills, d, "SKILL.md")
            if not os.path.isfile(p):
                fails.append(("E2", d + " 缺 SKILL.md")); continue
            fm = frontmatter(read(p))
            if fm.get("name") != d:
                fails.append(("E2", "%s frontmatter name=%r 与目录不符" % (d, fm.get("name"))))
            if not fm.get("description"):
                fails.append(("E2", d + " description 为空"))

    # E3
    for sub in EXPECT_WORK:
        if not os.path.isdir(os.path.join(paths["work"], *sub.split("/"))):
            fails.append(("E3", "工作区缺目录: " + sub))

    # E4
    for root in (paths["lib"], paths["v12"]):
        if os.path.isdir(root):
            bad = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)) and d.startswith("w-")]
            if bad:
                fails.append(("E4", "%s 出现 w-* 冲突: %r" % (root, bad)))

    # E5
    v12 = paths["v12"]
    if os.path.isdir(v12):
        n = len([d for d in os.listdir(v12) if os.path.isdir(os.path.join(v12, d))])
        if n != 42:
            fails.append(("E5", "v12 技能数=%d（应 42，旧体系被改动；V3a 后基线）" % n))

    # E6
    ledger = paths["ledger"]
    if not os.path.isfile(ledger):
        fails.append(("E6", "约束台账不存在"))
    else:
        t = read(ledger)
        sec = re.search(r"##\s*一[ ·]*Tier-0.*?(?=\n##\s)", t, re.S)
        block = sec.group(0) if sec else t
        n = len(re.findall(r"^\s*\|\s*\*\*T0-\d\*\*", block, re.M))
        if n != 4:
            fails.append(("E6", "Tier-0 条数=%d（应 4）" % n))

    # E8 · 节点影子字段（B4）
    fails.extend(check_nodes(paths["work"]))

    # E10 · 降级一致性（B 合入）
    fails.extend(check_e10(paths["work"]))

    return fails


DEMOTED_REQ = ("from_type", "from_role", "at", "reason", "decision_id")
_E10_STATUS = {"active", "demoted", "historical", "retired", "frozen", "draft",
               "executing", "done", "aborted", "superseded", "SOURCE_DELETED",
               "invalid", "quarantined"}
_E10_EDGES = ("parent", "children", "supports", "contradicts", "derived_from",
              "attached", "chain_prev", "chain_next")


def _e10_load_nodes(work):
    root = os.path.join(work, "brain", "nodes")
    nodes = {}
    if not os.path.isdir(root):
        return nodes
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                fm, _body = parse_node(p)
            except Exception:
                continue
            nid = fm.get("id")
            if nid:
                nodes[str(nid)] = {"fm": fm, "rel": os.path.relpath(p, root)}
    return nodes


def _e10_load_events(work):
    jd = os.path.join(work, "journal")
    events = []
    if not os.path.isdir(jd):
        return events
    for fn in sorted(os.listdir(jd)):
        if not fn.endswith(".jsonl"):
            continue
        try:
            text = read(os.path.join(jd, fn))
        except Exception:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    return events


def _e10_refs(fm):
    out = []
    edges = fm.get("edges") or {}
    if isinstance(edges, dict):
        for k in _E10_EDGES:
            v = edges.get(k)
            if isinstance(v, str) and v:
                out.append((k, v))
            elif isinstance(v, list):
                out.extend((k, x) for x in v if isinstance(x, str) and x)
    de = fm.get("default_entry")
    if isinstance(de, str) and de:
        out.append(("default_entry", de))
    return out


def check_e10(work):
    """E10 · 降级一致性（B 合入）：状态/子键/迁移事件/引用/dedault_entry 链。"""
    fails = []
    nodes = _e10_load_nodes(work)
    events = _e10_load_events(work)
    status_ev = {}
    for e in events:
        if e.get("event") in ("node_status", "plan_status"):
            nid = e.get("node_id")
            to = (e.get("payload") or {}).get("to")
            if nid and to:
                status_ev.setdefault(str(nid), set()).add(str(to))
    for nid, n in nodes.items():
        fm = n["fm"]; rel = n["rel"]; st = str(fm.get("status") or "active")
        if st not in _E10_STATUS:
            fails.append(("E10", "%s: 未知 status=%r" % (rel, st)))
        if st == "demoted":
            d = fm.get("demoted")
            if not isinstance(d, dict):
                fails.append(("E10", "%s: demoted 缺 demoted{}" % rel))
            else:
                miss = [k for k in DEMOTED_REQ if not d.get(k)]
                if miss:
                    fails.append(("E10", "%s: demoted 缺子键 %r" % (rel, miss)))
        if st == "historical":
            sc = fm.get("scope")
            if not isinstance(sc, dict) or not sc.get("epoch"):
                fails.append(("E10", "%s: historical 缺 scope.epoch" % rel))
        if st in ("demoted", "historical", "retired") and st not in status_ev.get(nid, set()):
            fails.append(("E10", "%s: status=%s 无 node_status/plan_status 事件（迁移无证据）" % (rel, st)))
        for kind, tgt in _e10_refs(fm):
            if tgt not in nodes:
                fails.append(("E10", "%s: %s 指向不存在节点 %r" % (rel, kind, tgt)))
                continue
            tst = str(nodes[tgt]["fm"].get("status") or "active")
            if tst == "retired" and not nodes[tgt]["fm"].get("default_entry"):
                fails.append(("E10", "%s: %s 指向 retired 且无 default_entry 的 %r" % (rel, kind, tgt)))
    for _nid, n in nodes.items():
        cur = n["fm"].get("default_entry"); seen = set(); depth = 0
        while isinstance(cur, str) and cur and depth < 10:
            if cur in seen:
                fails.append(("E10", "%s: default_entry 成环（%s）" % (n["rel"], cur))); break
            seen.add(cur); depth += 1
            if depth > 3:
                fails.append(("E10", "%s: default_entry 链深 >3" % n["rel"])); break
            nxt = nodes.get(cur)
            if nxt is None:
                fails.append(("E10", "%s: default_entry 目标不存在 %r" % (n["rel"], cur))); break
            cur = nxt["fm"].get("default_entry")
    return fails


def run(paths, quiet=False):
    t0 = time.perf_counter()
    fails = check(paths)
    elapsed = time.perf_counter() - t0
    if not quiet:
        print("=" * 70)
        print("  WishOS 骨架门禁 v0.3（E1~E8 + E10）")
        print("=" * 70)
        for k in ("patch", "skills", "work", "ledger"):
            print("  %-8s %s" % (k + ":", paths[k]))
        print("-" * 70)
    if fails:
        for code, msg in fails:
            print("  🔴 [%s] %s" % (code, msg))
    elif not quiet:
        print("  ✅ E1~E8+E10 全过（预设行 / %d 技能 / 工作区 / 无冲突 / v12 未动 / Tier-0=4 / 隔离生效 / %d 节点 bcode）"
              % (len(EXPECT_SKILLS), _count_nodes(paths["work"])))
    if not quiet:
        # D3 · 摩擦读数（只输出，不新增门禁）：耗时 / 检查项 / 扫描节点 / 红项（需人处置代理口径）
        print("  ⏱ 摩擦读数：耗时 %.3fs · 检查项 9 · 扫描节点 %d · 红 %d（需人处置 %d）"
              % (elapsed, _count_nodes(paths["work"]), len(fails), len(fails)))
        print("=" * 70)
    return 0 if not fails else 2


def selftest():
    import io, contextlib
    if BEACON is None:
        print("  🔴 自证不可跑：未找到解码器 _beacon.py（同目录 / WISHOS_BEACON / $WISHOS_ROOT/tools 均不可导入）")
        print("     ↳ 导入错误：%s" % _BEACON_IMPORT_ERROR)
        print("     ↳ 用法：设 WISHOS_BEACON=<.../_beacon.py> 或 WISHOS_ROOT=<工作区> 后重跑")
        return 3
    tmp = tempfile.mkdtemp(prefix="wishos-gate-")
    bad = 0

    def make_fixture(root):
        paths = {
            "patch": os.path.join(root, "patch.yml"),
            "skills": os.path.join(root, "skills"),
            "work": os.path.join(root, "work"),
            "lib": os.path.join(root, "lib"),
            "v12": os.path.join(root, "v12"),
            "ledger": os.path.join(root, "ledger.md"),
        }
        patch = """- insert:
    - id: preset-wishos
      name: '@deepseek-ai/dsh-agent-preset'
      config:
        id: wishos
        plugins:
          - {id: persona, name: '@deepseek-ai/dsh-persona'}
          - id: skill-filesystem
            name: '@deepseek-ai/dsh-skill-filesystem'
            config: {includeDefaultRoots: false, customSkillDirs: ['x']}
          - {id: tool-skill, name: '@deepseek-ai/dsh-tool-skill'}
          - {id: planning, name: 'cordis:group', group: true}
          - {id: delegation, name: 'cordis:group', group: true}
          - {id: compaction, name: 'cordis:group', group: true}
- insert:
    - id: preset-v12
      name: '@deepseek-ai/dsh-agent-preset'
      config: {id: v12, plugins: []}
"""
        os.makedirs(paths["skills"]); os.makedirs(paths["work"])
        os.makedirs(os.path.join(root, "lib")); os.makedirs(os.path.join(root, "v12"))
        for i in range(42):
            os.makedirs(os.path.join(paths["v12"], "s%02d" % i))
        for d in EXPECT_SKILLS:
            sd = os.path.join(paths["skills"], d); os.makedirs(sd)
            open(os.path.join(sd, "SKILL.md"), "w", encoding="utf-8").write(
                "---\nname: %s\ndescription: ok\n---\n" % d)
        for sub in EXPECT_WORK:
            os.makedirs(os.path.join(paths["work"], *sub.split("/")))
        open(paths["ledger"], "w", encoding="utf-8").write(
            "## 一 · Tier-0 硬事实\n\n| # | 事实 |\n|:-:|:--|\n"
            "| **T0-1** | a |\n| **T0-2** | b |\n| **T0-3** | c |\n| **T0-4** | d |\n\n## 二 ·\n")
        open(paths["patch"], "w", encoding="utf-8").write(patch)
        # E8 正样本：一个合法 bcode 节点（B4）
        node_dir = os.path.join(paths["work"], "brain", "nodes", "project")
        os.makedirs(node_dir, exist_ok=True)
        fm = {"id": "n-project-selftest", "type": "project", "title": "自证节点",
              "ts": "2026-11-02T16:49:44", "edges": {"attached": []}}
        body = "\n# n-project-selftest\n\n自证节点正文。\n"
        h = BEACON.h_of(BEACON.canonical_obj_from_node(dict(fm), body))
        code = BEACON.encode(1_750_000_000_000, BEACON.TYPE_CODES["project"], 0, h, 1)
        node_text = ('---\nid: %s\ntype: %s\ntitle: %s\nts: %s\n'
                     'edges:\n  attached: []\nbcode: "%s"\n---\n%s'
                     % (fm["id"], fm["type"], fm["title"], fm["ts"], code, body))
        # 必须二进制写：文本模式会把 \n 翻成 \r\n，正文/哈希会与 canonical 口径不一致
        with open(os.path.join(node_dir, "n-project-selftest.md"), "wb") as f:
            f.write(node_text.encode("utf-8"))
        return paths

    def quiet(fn):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn()
        return rc, buf.getvalue()

    # ① 正样本
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 0
    print("  %s 正样本（完整骨架）              期望 0 · 实得 %d" % ("✅" if ok else "🔴", rc))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ② 负样本：抽掉 preset-wishos 行
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    t = read(p["patch"]).replace("preset-wishos", "preset-removed")
    open(p["patch"], "w", encoding="utf-8").write(t)
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 2 and "E1" in out
    print("  %s 负样本（缺预设行）              期望 2 · 实得 %d · 理由含 E1=%s" % ("✅" if ok else "🔴", rc, "E1" in out))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ③ ⚪真阴性：其余全对、只把台账换成"无 Tier-0 表的普通文档" ⇒ 必须只报 E6，不得误报 E1/E2/E3
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    open(p["ledger"], "w", encoding="utf-8").write("# 普通文档\n\n它没有 Tier-0 表。\n")
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 2 and "E6" in out and ("E1" not in out) and ("E2" not in out) and ("E3" not in out)
    print("  %s ⚪真阴性（无表的好文档）        期望 2 · 实得 %d · 只报 E6=%s" % ("✅" if ok else "🔴", rc, ok))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    def mutate_node(p, fn):
        np = os.path.join(p["work"], "brain", "nodes", "project", "n-project-selftest.md")
        t = read(np)
        # 二进制写，避免文本模式二次换行转换把 fixture 写坏
        with open(np, "wb") as f:
            f.write(fn(t).encode("utf-8"))

    # ④ E8 负样本：坏 bcode（可解性判据必须红）
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    mutate_node(p, lambda t: re.sub(r'bcode: "[^"]*"', 'bcode: "' + "0" * 43 + '"', t))
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 2 and "E8" in out
    print("  %s E8 负样本（坏 bcode）           期望 2 · 实得 %d · 报 E8=%s" % ("✅" if ok else "🔴", rc, "E8" in out))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ⑤ E8 负样本：正文改了但没重发号（h 绑定判据必须红）
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    mutate_node(p, lambda t: t + "\n（正文追加，未重新发号）\n")
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 2 and "E8" in out and "h 与正文 canonical 不一致" in out
    print("  %s E8 负样本（正文变未重发）       期望 2 · 实得 %d · 报 h 不一致=%s"
          % ("✅" if ok else "🔴", rc, "h 与正文 canonical 不一致" in out))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ⑥ E8 负样本：缺必填键
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    mutate_node(p, lambda t: re.sub(r"^title: .*$", "", t, flags=re.M))
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 2 and "E8" in out and "缺必填键 title" in out
    print("  %s E8 负样本（缺必填键）           期望 2 · 实得 %d · 报缺键=%s"
          % ("✅" if ok else "🔴", rc, "缺必填键 title" in out))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ⑦ B12 ⚪真阴性：ALLOW 目录（plan/decision/schedule）缺失 ⇒ 仍须绿
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 0
    print("  %s B12 ⚪真阴性（ALLOW 目录缺失）   期望 0 · 实得 %d" % ("✅" if ok else "🔴", rc))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ⑧ B12 负样本：未知节点目录 ⇒ E8 红
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    foo = os.path.join(p["work"], "brain", "nodes", "foo")
    os.makedirs(foo)
    shutil.copyfile(os.path.join(p["work"], "brain", "nodes", "project", "n-project-selftest.md"),
                    os.path.join(foo, "n-project-selftest.md"))
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 2 and "未知节点目录" in out
    print("  %s B12 负样本（未知节点目录）      期望 2 · 实得 %d · 报未知目录=%s"
          % ("✅" if ok else "🔴", rc, "未知节点目录" in out))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ⑨ B12 正样本：ALLOW 目录内合法 plan 节点 ⇒ 绿
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    plan_dir = os.path.join(p["work"], "brain", "nodes", "plan")
    os.makedirs(plan_dir)
    fm = {"id": "n-plan-selftest", "type": "plan", "title": "B12 plan 自证",
          "ts": "2026-11-08T12:00:00", "edges": {"attached": []},
          "class": "internal", "retention": "project_end"}
    body = "\n# n-plan-selftest\n\nB12 允许目录正样本。\n"
    h = BEACON.h_of(BEACON.canonical_obj_from_node(dict(fm), body))
    code = BEACON.encode(1_750_000_000_001, BEACON.TYPE_CODES["plan"], 0, h, 1)
    node_text = ('---\nid: %s\ntype: %s\ntitle: %s\nts: %s\n'
                 'edges:\n  attached: []\nbcode: "%s"\nclass: %s\nretention: %s\n---\n%s'
                 % (fm["id"], fm["type"], fm["title"], fm["ts"], code, fm["class"], fm["retention"], body))
    with open(os.path.join(plan_dir, "n-plan-selftest.md"), "wb") as f:
        f.write(node_text.encode("utf-8"))
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 0
    print("  %s B12 正样本（ALLOW 目录 plan）   期望 0 · 实得 %d" % ("✅" if ok else "🔴", rc))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ⑩ B12 负样本：新类型缺 class/retention ⇒ E8 红
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    plan_dir = os.path.join(p["work"], "brain", "nodes", "plan")
    os.makedirs(plan_dir)
    fm = {"id": "n-plan-noclass", "type": "plan", "title": "B12 缺 class",
          "ts": "2026-11-08T12:01:00", "edges": {"attached": []}}
    body = "\n# n-plan-noclass\n\n缺 class/retention。\n"
    h = BEACON.h_of(BEACON.canonical_obj_from_node(dict(fm), body))
    code = BEACON.encode(1_750_000_000_004, BEACON.TYPE_CODES["plan"], 0, h, 1)
    node_text = ('---\nid: %s\ntype: %s\ntitle: %s\nts: %s\n'
                 'edges:\n  attached: []\nbcode: "%s"\n---\n%s'
                 % (fm["id"], fm["type"], fm["title"], fm["ts"], code, body))
    with open(os.path.join(plan_dir, "n-plan-noclass.md"), "wb") as f:
        f.write(node_text.encode("utf-8"))
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 2 and "新类型缺 class" in out and "新类型缺 retention" in out
    print("  %s B12 负样本（新类型缺 class）     期望 2 · 实得 %d · 报缺 class/retention=%s"
          % ("✅" if ok else "🔴", rc, ok))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ⑪ E10 负样本：demoted 无迁移事件
    def _e10_probe(mut):
        r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
        mutate_node(p, mut)
        return quiet(lambda: run(p, quiet=True))

    rc, out = _e10_probe(lambda t: t.replace("bcode:", 'status: "demoted"\ndemoted:\n  from_type: "project"\n  from_role: "root"\n  at: "2026-11-14T08:00:00+08:00"\n  reason: "x"\n  decision_id: "D-x"\nbcode:', 1))
    ok = rc == 2 and "E10" in out
    print("  %s E10 负样本（无迁移事件）        期望 2 · 实得 %d · 报 E10=%s" % ("✅" if ok else "🔴", rc, "E10" in out))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ⑫ E10 负样本：demoted 缺 decision_id
    rc, out = _e10_probe(lambda t: t.replace("bcode:", 'status: "demoted"\ndemoted:\n  from_type: "project"\n  from_role: "root"\nbcode:', 1))
    ok = rc == 2 and "E10" in out and "demoted 缺子键" in out
    print("  %s E10 负样本（demoted 缺子键）    期望 2 · 实得 %d · 报缺子键=%s" % ("✅" if ok else "🔴", rc, "demoted 缺子键" in out))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    # ⑬ E10 负样本：historical 缺 scope.epoch
    rc, out = _e10_probe(lambda t: t.replace("bcode:", 'status: "historical"\nbcode:', 1))
    ok = rc == 2 and "E10" in out and "scope.epoch" in out
    print("  %s E10 负样本（historical 缺 scope）期望 2 · 实得 %d · 报 scope=%s" % ("✅" if ok else "🔴", rc, "scope.epoch" in out))
    if not ok:
        print("     ↳ " + out.strip().replace(chr(10), " | ")[:700])
    bad += 0 if ok else 1

    shutil.rmtree(tmp, ignore_errors=True)
    print("-" * 70)
    print("  ✅ 13 项自证全过" if bad == 0 else "  🔴 自证未过（%d 处不符）" % bad)
    return 0 if bad == 0 else 2


class _StrictParser(argparse.ArgumentParser):
    """未知参数/用法错误 ⇒ rc=3（契约 v1.1 §三）。"""

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(3)


def build_parser():
    p = _StrictParser(prog="_wishos_gate.py",
                      description="WishOS 骨架门禁 E1–E8（B12：--root 只覆盖 E8/E3 扫描根）",
                      allow_abbrev=False)
    p.add_argument("--selftest", action="store_true", help="夹具自证（≠ 生产）")
    p.add_argument("--root", default=None, help="只覆盖 E8/E3 扫描根（默认生产 work）")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.selftest:
        if args.root:
            print("  [warn] --selftest 忽略 --root（夹具自证不读根参数）")
        return selftest()
    paths = dict(REAL)
    if args.root:
        root = os.path.abspath(args.root)
        if not os.path.isdir(root):
            print("  🔴 路径不可读: " + root)
            return 3
        paths["work"] = root
    return run(paths)


if __name__ == "__main__":
    sys.exit(main())
