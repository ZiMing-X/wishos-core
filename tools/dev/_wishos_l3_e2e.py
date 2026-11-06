# -*- coding: utf-8 -*-
"""WishOS L3 端到端一键复跑判据（只读 · 2026-11-02 v1.0）

判据来源（不新造口径，全部取自技能正文与验证矩阵 §四）：
  · Ticket  schema：w-wish §一（id/wish/intent/acceptance/budget/risk/status/created_at/worker）+ README「带 focus_node」
  · Card    schema：w-capture §一/§二（statement/evidence/confidence/falsifiable/source；三空拒收）
  · Node    schema：w-enter §一（brain/nodes/<type>/<id>.md，frontmatter id/type/title/ts/edges）
  · 焦点栈        ：w-enter §二.3（写 brain/focus.json：focus + stack + ts）
  · 巡检          ：w-watchdog §二（outputs/check-<YYYYMMDD>.md，四节：读数/异常/建议/需人决定）
                    + 矩阵 §四.4（报告**有票据**）
  · 注意力预算    ：w-router §三（同一愿望唤起人 ≤2 次，记账 brain/attention/<date>.jsonl）

用法：
  python _wishos_l3_e2e.py --run T-20261102-1700-readme-sync      # 判某一跑
  python _wishos_l3_e2e.py --latest                               # 判 brain/tickets 里最新一张（按 created_at）
  python _wishos_l3_e2e.py --unclosed                             # 只列未闭合票据（中断/resume 后先跑它）
  python _wishos_l3_e2e.py --closure                              # 收工闭合（存档+请求ID+校准对+无未闭合）
  python _wishos_l3_e2e.py --selfcheck                            # 判据自证：1 正样本 + 9 坏样本必须能红
  python _wishos_l3_e2e.py --run <id> --json

退出码：0 全过 / 2 有失败 / 3 前置不可读
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.environ.get("WISHOS_ROOT") or os.path.join(os.getcwd(), "wishos")
REQUIRED_KEYS = ("id", "wish", "intent", "acceptance", "budget", "risk",
                 "status", "created_at", "worker")
STATUSES = {"idle", "working", "person", "blocked", "failed", "done"}
CARD_TYPES = {"context", "pattern", "decision", "solution"}
NODE_TYPES = {"project", "event", "claim", "evidence", "inference", "conclusion",
              "card", "ticket", "artifact", "session"}
WATCH_SECTIONS = ("读数", "异常", "建议", "需人决定")


# ── 基础 ────────────────────────────────────────────────────────────────
def read(p):
    with open(p, "rb") as f:
        return f.read().decode("utf-8-sig", errors="replace")


def fm_of(text):
    import yaml

    class L(yaml.SafeLoader):
        pass

    L.add_constructor("tag:yaml.org,2002:js", lambda l, n: l.construct_scalar(n))
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return None
    try:
        return yaml.load(m.group(1), Loader=L) or {}
    except Exception:  # noqa: BLE001
        return None


def load_tickets(root):
    out = {}
    for p in glob.glob(os.path.join(root, "brain", "tickets", "*.json")):
        try:
            doc = json.loads(read(p))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(doc, dict) and doc.get("id"):
            doc["_path"] = p
            out[doc["id"]] = doc
    return out


def load_cards(root):
    out = []
    for p in glob.glob(os.path.join(root, "brain", "cards", "*", "*.md")):
        fm = fm_of(read(p))
        if fm:
            fm["_path"] = p
            out.append(fm)
    return out


def load_nodes(root):
    out = {}
    for p in glob.glob(os.path.join(root, "brain", "nodes", "*", "*.md")):
        fm = fm_of(read(p))
        if not fm:
            continue
        nid = str(fm.get("id") or os.path.splitext(os.path.basename(p))[0])
        fm["_path"] = p
        out[nid] = fm
    return out


def focus_doc(root):
    p = os.path.join(root, "brain", "focus.json")
    if not os.path.isfile(p):
        return None
    try:
        return json.loads(read(p))
    except Exception:  # noqa: BLE001
        return None


def pathish(s):
    s = str(s)
    return bool(re.search(r"[A-Za-z]:\\|/", s))


def exists_path(s):
    s = str(s).strip().strip("`")
    cand = [s]
    if " -> " in s:
        cand.append(s.split(" -> ")[0].strip())
    for c in cand:
        if os.path.exists(c):
            return True
    return False


# ── 判据主体 ─────────────────────────────────────────────────────────────
def judge(root, run_id):
    fails, warns, rows = [], [], []
    tickets = load_tickets(root)
    cards = load_cards(root)
    nodes = load_nodes(root)
    focus = focus_doc(root)

    t = tickets.get(run_id)
    if not t:
        return [("T", "找不到 Ticket %r（brain/tickets/*.json）" % run_id)], warns, rows
    miss = [k for k in REQUIRED_KEYS if not t.get(k)]
    if miss:
        fails.append(("T", "Ticket 缺字段: %r" % miss))
    if not isinstance(t.get("acceptance"), list) or not t.get("acceptance"):
        fails.append(("T", "acceptance 为空 ⇒ 没有判据的愿望不该开工（w-wish §二）"))
    if t.get("status") not in STATUSES:
        fails.append(("T", "status=%r 不在状态机 %r" % (t.get("status"), sorted(STATUSES))))
    if t.get("status") != "done":
        fails.append(("T", "L3 跑完应闭合为 done，实为 %r" % t.get("status")))
    if not t.get("worker"):
        fails.append(("T", "worker 为空（没派发就自己干 = 违反 w-router §一）"))
    if not t.get("focus_node"):
        warns.append(("T", "无 focus_node（README 口径要求 Ticket 带 focus_node）"))
    tid_short = run_id
    rows.append(("T", "Ticket 命中 %s · status=%s · worker=%r"
                 % (os.path.basename(t["_path"]), t.get("status"), t.get("worker"))))

    my_cards = [c for c in cards if str(c.get("source") or "") == run_id]
    if not my_cards:
        fails.append(("C", "没有 source=%s 的卡片（w-capture 收口缺失）" % run_id))
    for c in my_cards:
        cid = c.get("id") or os.path.basename(c["_path"])
        for k in ("statement", "evidence", "falsifiable"):
            if not c.get(k):
                fails.append(("C", "卡片 %s 缺 %s（三空拒收，w-capture §二）" % (cid, k)))
        try:
            cf = float(c.get("confidence"))
            if not (0.0 <= cf <= 1.0):
                fails.append(("C", "卡片 %s confidence=%r 越界" % (cid, c.get("confidence"))))
        except Exception:  # noqa: BLE001
            fails.append(("C", "卡片 %s confidence 非数值: %r" % (cid, c.get("confidence"))))
        ev = c.get("evidence") or []
        ev = ev if isinstance(ev, list) else [ev]
        evp = [x for x in ev if pathish(x)]
        if not evp:
            fails.append(("C", "卡片 %s evidence 没有可溯源路径" % cid))
        bad = [x for x in evp if not exists_path(x)]
        if bad:
            fails.append(("C", "卡片 %s evidence 指向不存在的路径: %r" % (cid, bad[:3])))
        rows.append(("C", "卡片 %s · confidence=%s · evidence 路径 %d/%d 存在"
                     % (cid, c.get("confidence"), len(evp) - len(bad), len(evp))))

    # 跳转 3 次：focus.stack ≥3 且都能落到节点
    if focus is None:
        fails.append(("J", "缺 brain/focus.json（w-enter 定焦点未落盘）"))
    else:
        stack = focus.get("stack") or []
        if not isinstance(stack, list) or len(stack) < 3:
            fails.append(("J", "focus.stack 只有 %d 项（应 ≥3 次进入）"
                          % (len(stack) if isinstance(stack, list) else -1)))
        else:
            resolved, types = [], set()
            for it in stack:
                nid = it.get("id") if isinstance(it, dict) else str(it)
                n = nodes.get(str(nid))
                if n:
                    resolved.append(nid)
                    types.add(str(n.get("type")))
                elif str(nid).startswith("session:"):
                    resolved.append(nid)
                    types.add("session")
            if len(resolved) < 3:
                fails.append(("J", "stack 有 %d 项但只有 %d 项能落到节点/锚点"
                              % (len(stack), len(resolved))))
            if len(types) < 2:
                warns.append(("J", "3 次进入只落到 %d 类节点（%r）" % (len(types), sorted(types))))
            rows.append(("J", "焦点栈 %d 项 · 可解析 %d · 节点类型 %r"
                         % (len(stack), len(resolved), sorted(types))))
    for nid, n in nodes.items():
        lack = [k for k in ("id", "type", "title", "ts") if not n.get(k)]
        # edges 允许空映射（根节点没有边），只判「字段在不在」——不能拿空值当缺失
        if "edges" not in n or n.get("edges") is None:
            lack.append("edges")
        if lack:
            fails.append(("N", "节点 %s 缺 frontmatter 字段 %r（w-enter §一）" % (nid, lack)))
        if str(n.get("type")) not in NODE_TYPES:
            warns.append(("N", "节点 %s type=%r 不在白名单" % (nid, n.get("type"))))
    if nodes:
        rows.append(("N", "节点 %d 个 · 类型 %r"
                     % (len(nodes), sorted({str(n.get("type")) for n in nodes.values()}))))

    # 产出
    out_files = [p for p in glob.glob(os.path.join(root, "outputs", "**", "*"), recursive=True)
                 if os.path.isfile(p)]
    related = [p for p in out_files if run_id in os.path.basename(p) or run_id in p]
    if not related:
        fails.append(("O", "outputs/ 下找不到与 %s 相关的产出件" % run_id))
    else:
        rows.append(("O", "产出件 %d 个（例：%s）"
                     % (len(related), os.path.basename(related[0]))))

    # 巡检：报告四节 + 有票据
    checks = sorted(glob.glob(os.path.join(root, "outputs", "check-*.md")))
    if not checks:
        fails.append(("W", "缺 outputs/check-<YYYYMMDD>.md（w-watchdog §二）"))
    else:
        latest = checks[-1]
        body = read(latest)
        lack = [s for s in WATCH_SECTIONS if s not in body]
        if lack:
            fails.append(("W", "巡检报告缺小节 %r（应四节齐全）" % lack))
        base = os.path.basename(latest)
        cited = [tid for tid, d in tickets.items()
                 if base in json.dumps(d, ensure_ascii=False)]
        if not cited:
            fails.append(("W", "巡检报告 %s 没有对应票据（矩阵 §四.4「报告有票据」）" % base))
        else:
            rows.append(("W", "巡检报告 %s · 四节齐全 · 票据 %r" % (base, cited)))

    # 注意力预算
    att = glob.glob(os.path.join(root, "brain", "attention", "*.jsonl"))
    if att:
        n = 0
        for p in att:
            for line in read(p).splitlines():
                if run_id in line:
                    n += 1
        if n > 2:
            fails.append(("A", "同一愿望唤起人 %d 次 > 预算 2（w-router §三）" % n))
        rows.append(("A", "注意力记账含本愿望 %d 条（预算 ≤2）" % n))
    else:
        rows.append(("A", "无注意力记账 ⇒ 本轮未打扰人（沉默优先）"))

    # 校准（w-calibrate §三：brain/calibration/pairs.jsonl，一行一对；H-1 p 在块内、H-2 p 早于 y）
    pairs_path = os.path.join(root, "brain", "calibration", "pairs.jsonl")
    if not os.path.isfile(pairs_path):
        warns.append(("K", "缺 brain/calibration/pairs.jsonl（收工项：p/y 对未落）"))
    else:
        ok_p = closed = 0
        bad = []
        for i, line in enumerate(read(pairs_path).splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                bad.append(i); continue
            if d.get("p") is None:
                bad.append(i); continue
            ok_p += 1
            if d.get("y") is not None:
                closed += 1
        if bad:
            fails.append(("K", "pairs.jsonl 第 %r 行缺 p 或非法 JSON（H-1）" % bad[:5]))
        if ok_p == 0:
            fails.append(("K", "pairs.jsonl 无有效 p/y 对"))
        else:
            rows.append(("K", "校准对 %d 条 · 已闭合 y %d 条" % (ok_p, closed)))
            if closed < ok_p:
                warns.append(("K", "%d 条 y 待补（结局未到，按 H-4 标 RAW_PLACEHOLDER）"
                              % (ok_p - closed)))

    return fails, warns, rows


def unclosed(root):
    """未闭合票据清单（失败注入/中断后的一键检查）：status != done 即算未闭合。"""
    ts = load_tickets(root)
    left = [(d["id"], d.get("status"), d.get("created_at"))
            for d in ts.values() if d.get("status") != "done"]
    return sorted(left, key=lambda x: str(x[2] or ""))


CLOSURE_KEYS = ("请求ID", "存档", "校准")


def closure_check(root):
    """收工闭合判据（矩阵 §四.3 的 WishOS 口径）：存档指针 + 请求ID(可'待补') + 校准对 + 无未闭合票据。"""
    fails, rows = [], []
    docs = sorted(glob.glob(os.path.join(root, "outputs", "closure-*.md")))
    if not docs:
        fails.append(("X", "缺 outputs/closure-<YYYYMMDD>.md（收工记录无落点）"))
    else:
        body = read(docs[-1])
        miss = [k for k in CLOSURE_KEYS if k not in body]
        if miss:
            fails.append(("X", "收工记录缺 %r（存档/请求ID/校准 三件缺一不可）" % miss))
        rows.append(("X", "收工记录 %s · 关键字齐备=%s"
                     % (os.path.basename(docs[-1]), not miss)))
    pairs = os.path.join(root, "brain", "calibration", "pairs.jsonl")
    if not os.path.isfile(pairs):
        fails.append(("X", "缺 brain/calibration/pairs.jsonl（收工必须落 p）"))
    else:
        n = 0
        bad = []
        for i, line in enumerate(read(pairs).splitlines(), 1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                bad.append(i); continue
            if d.get("p") is None:
                bad.append(i)
            else:
                n += 1
        if bad:
            fails.append(("X", "pairs.jsonl 第 %r 行缺 p/非法（H-1）" % bad[:5]))
        rows.append(("X", "校准对 %d 条" % n))
    left = unclosed(root)
    if left:
        fails.append(("X", "仍有 %d 张未闭合票据: %r" % (len(left), [x[0] for x in left][:5])))
    else:
        rows.append(("X", "未闭合票据 0"))
    return fails, rows


# ── 自证：1 正样本 + 6 坏样本 ────────────────────────────────────────────
def _mk_run(root, *, ticket_status="done", acceptance=True, card_falsifiable=True,
            stack=3, watch_sections=True, watch_ticket=True, bad_evidence=False,
            cal_pairs=None, closure_fixed=True):
    def w(rel, text):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    tid = "T-20261102-0000-selftest"
    t = {"id": tid, "wish": "自证用愿望", "intent": "自证", "acceptance": ["能跑通"] if acceptance else [],
         "budget": {"minutes": 5, "steps": 3}, "risk": {"tier0": []}, "status": ticket_status,
         "created_at": "2026-11-02T00:00:00", "worker": "selftest-worker",
         "focus_node": "project-selftest"}
    w("brain/tickets/20261102-0000-selftest.json", json.dumps(t, ensure_ascii=False, indent=1))
    out = "outputs/%s/report.md" % tid
    w(out, "产出占位\n")
    ev = [os.path.join(root, out), os.path.join(root, "outputs", "missing.md")] if bad_evidence \
        else [os.path.join(root, out)]
    w("brain/cards/solution/c-20261102-selftest.md",
      "---\nid: c-20261102-selftest\nstatement: 自证卡\n"
      "evidence: %s\nconfidence: 0.8\nfalsifiable: %s\nsource: %s\nstatus: draft\nupdated: 2026-11-02\n---\n\n正文\n"
      % (json.dumps(ev, ensure_ascii=False), "若跑不通则算错" if card_falsifiable else "", tid))
    types = ["project", "ticket", "card"]
    ids = []
    for ty, nm in zip(types, ["project-selftest", "ticket-selftest", "card-selftest"]):
        w("brain/nodes/%s/%s.md" % (ty, nm),
          "---\nid: %s\ntype: %s\ntitle: 自证节点\nts: 2026-11-02T00:00:00\nedges: {}\n---\n" % (nm, ty))
        ids.append({"id": nm})
    w("brain/focus.json", json.dumps({"focus": ids[0]["id"], "stack": ids[:stack],
                                      "ts": "2026-11-02T00:00:00"}, ensure_ascii=False, indent=1))
    secs = "\n\n".join("## %s\n占位" % s for s in WATCH_SECTIONS)
    if not watch_sections:
        secs = secs.replace("## 需人决定\n占位", "")
    body = "# 巡检 2026-11-02\n\n" + secs + "\n"
    w("outputs/check-20261102.md", body)
    if watch_ticket:
        t2 = {"id": "T-20261102-0001-watchdog", "wish": "巡检报告 check-20261102.md 归档",
              "intent": "巡检", "acceptance": ["有报告"], "budget": {"minutes": 1, "steps": 1},
              "risk": {"tier0": []}, "status": "done", "created_at": "2026-11-02T00:10:00",
              "worker": "watchdog", "focus_node": "project-selftest"}
        w("brain/tickets/20261102-0001-watchdog.json", json.dumps(t2, ensure_ascii=False, indent=1))
    if cal_pairs is not None:
        w("brain/calibration/pairs.jsonl",
          "\n".join(json.dumps(x, ensure_ascii=False) for x in cal_pairs) + "\n")
    if closure_fixed is not None:
        head = "请求ID：待补\n存档指针：selftest\n校准：见 pairs.jsonl\n" if closure_fixed \
            else "存档指针：selftest\n校准：见 pairs.jsonl\n"
        w("outputs/closure-20261102.md", "# 收工\n\n" + head)
    return tid


def selfcheck():
    cases = [
        ("正样本：完整 L3 产物", {}, True),
        ("坏样本①：Ticket 无 acceptance", {"acceptance": False}, False),
        ("坏样本②：卡片 falsifiable 空", {"card_falsifiable": False}, False),
        ("坏样本③：焦点栈只有 2 次进入", {"stack": 2}, False),
        ("坏样本④：巡检报告缺「需人决定」节", {"watch_sections": False}, False),
        ("坏样本⑤：巡检报告无票据", {"watch_ticket": False}, False),
        ("坏样本⑥：卡片 evidence 指向不存在的路径", {"bad_evidence": True}, False),
    ]
    bad = 0
    for label, kw, want_ok in cases:
        tmp = tempfile.mkdtemp(prefix="l3sc-")
        try:
            tid = _mk_run(tmp, **kw)
            fails, warns, rows = judge(tmp, tid)
            ok = not fails
            good = (ok == want_ok)
            print("  %s %s（fails=%d）%s" % ("✅" if good else "🔴", label, len(fails),
                                            "" if good else " ← 判据没按预期红/绿"))
            bad += 0 if good else 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ⑧ 校准对（w-calibrate 真 schema）：有 p+y ⇒ 绿；缺 p 的行 ⇒ 红
    tmp = tempfile.mkdtemp(prefix="l3sc-")
    try:
        tid = _mk_run(tmp, cal_pairs=[{"p": 0.8, "y": 1, "q": "判据修正后 auto 会绿"}])
        ok_cal = not judge(tmp, tid)[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    tmp = tempfile.mkdtemp(prefix="l3sc-")
    try:
        tid = _mk_run(tmp, cal_pairs=[{"y": 1}])
        bad_cal = bool(judge(tmp, tid)[0])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    good = ok_cal and bad_cal
    print("  %s ⑧ 校准对判据：p+y 绿、缺 p 必红（%s/%s）"
          % ("✅" if good else "🔴", ok_cal, bad_cal))
    bad += 0 if good else 1

    # ⑨ 未闭合检出（失败注入的一键检查）
    tmp = tempfile.mkdtemp(prefix="l3sc-")
    try:
        _mk_run(tmp, ticket_status="working")
        found = bool(unclosed(tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    tmp = tempfile.mkdtemp(prefix="l3sc-")
    try:
        _mk_run(tmp)
        clean = not unclosed(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    good = found and clean
    print("  %s ⑨ 未闭合检出：working 票据必被列出、全 done 必为空（%s/%s）"
          % ("✅" if good else "🔴", found, clean))
    bad += 0 if good else 1

    # ⑩ 收工闭合：三件齐备 ⇒ 绿；缺「请求ID」⇒ 红
    tmp = tempfile.mkdtemp(prefix="l3sc-")
    try:
        _mk_run(tmp, cal_pairs=[{"p": 0.5, "y": None}])
        ok_cl = not closure_check(tmp)[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    tmp = tempfile.mkdtemp(prefix="l3sc-")
    try:
        _mk_run(tmp, cal_pairs=[{"p": 0.5, "y": None}], closure_fixed=False)
        bad_cl = bool(closure_check(tmp)[0])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    good = ok_cl and bad_cl
    print("  %s ⑩ 收工闭合判据：三件齐备绿、缺请求ID必红（%s/%s）"
          % ("✅" if good else "🔴", ok_cl, bad_cl))
    bad += 0 if good else 1

    print("  " + ("✅ 自证 10/10 通过（正样本绿、9 个坏样本全红）" if bad == 0
                  else "🔴 自证未过（%d 处）" % bad))
    return 0 if bad == 0 else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None)
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--unclosed", action="store_true", help="只列未闭合票据（中断/resume 后的一键检查）")
    ap.add_argument("--closure", action="store_true", help="收工闭合判据（存档+请求ID+校准对+无未闭合票据）")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=None, help="报告落盘路径（默认 _tmp/l3-report-<run>.md）")
    a = ap.parse_args()

    if a.selfcheck:
        return selfcheck()
    if a.unclosed:
        left = unclosed(a.root)
        if not left:
            print("✅ 无未闭合票据（全部 status=done）")
            return 0
        print("🔴 未闭合票据 %d 张（中断/resume 后先收口，再判 L3）：" % len(left))
        for tid, st, ts in left:
            print("  - %s  status=%s  created=%s" % (tid, st, ts))
        return 2
    if a.closure:
        fails, rows = closure_check(a.root)
        print("# WishOS 收工闭合读数")
        print()
        for k, v in rows:
            print("- [%s] %s" % (k, v))
        if fails:
            print("\n🔴 未闭合（%d 项）：" % len(fails))
            for k, v in fails:
                print("- 🔴 [%s] %s" % (k, v))
            return 2
        print("\n✅ 收工闭合（存档/请求ID/校准对/无未闭合票据 均齐）")
        return 0
    if not (a.run or a.latest):
        print(__doc__)
        return 0

    if a.latest:
        ts = load_tickets(a.root)
        if not ts:
            print("🔴 brain/tickets 下没有 Ticket"); return 3
        cards = load_cards(a.root)
        have_card = {str(c.get("source")) for c in cards}
        cand = [d for d in sorted(ts.values(), key=lambda x: str(x.get("created_at") or ""), reverse=True)
                if d["id"] in have_card]
        if not cand:
            print("🔴 最近票据里没有『有卡片收口』的（L3 判据只适用于走完 Wish→…→Card 的跑次）；"
                  "请用 --run <ticket-id> 指定")
            return 3
        run_id = cand[0]["id"]
    else:
        run_id = a.run

    fails, warns, rows = judge(a.root, run_id)
    md = ["# WishOS L3 端到端读数", "",
          "- 时间：%s" % datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
          "- 跑次：`%s` · root=`%s`" % (run_id, a.root),
          "- 判定：**%s**（失败 %d / 警告 %d）"
          % ("✅ 全过" if not fails else "🔴 未全过", len(fails), len(warns)),
          "", "| 类 | 读数 |", "|:--|:--|"]
    md += ["| %s | %s |" % (k, v.replace("|", "\\|")) for k, v in rows]
    if warns:
        md += ["", "## 警告（不阻断）", ""] + ["- 🔶 [%s] %s" % (k, v) for k, v in warns]
    if fails:
        md += ["", "## 失败项", ""] + ["- 🔴 [%s] %s" % (k, v) for k, v in fails]
    text = "\n".join(md) + "\n"
    out = a.out or os.path.join(a.root, "_tmp", "l3-report-%s.md" % re.sub(r"[^\w.-]", "_", run_id))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    if a.json:
        print(json.dumps({"ok": not fails, "fails": fails, "warns": warns,
                          "rows": rows, "report": out}, ensure_ascii=False, indent=1))
    else:
        print(text)
        print("报告 -> " + out)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
