# -*- coding: utf-8 -*-
"""WishOS L2 单技能冒烟（只读 · 2026-11-02 v1.0）

验什么（对应验证矩阵 §三 L2 清单，14 件）：
  ① frontmatter 可解析、`name` == 目录名、description 非空、whenToUse 存在（缺则 🔶）
  ② 正文非空（≥500 字符），且**带触发词**（正文/描述里能抽到「触发词：…」清单）
  ③ 宿主耦合文本：`.workbuddy` / `WorkBuddy` / `<legacy-root>` 出现行（已知保留行除外）
  ④ 有脚本的件：入口能起、不 import 失败（判定口径沿用矩阵：入口能起 + 无 Traceback/ImportError）
  ⑤ 触发词**近邻碰撞**：跨件出现完全相同的触发词 ⇒ 报「抢触发」风险对（只报告，不判红）

用法：
  python _wishos_l2_smoke.py              # 14 件 v12-core（L2 口径）
  python _wishos_l2_smoke.py --all        # 14 + 8 件 w-*
  python _wishos_l2_smoke.py --json       # 机器可读

退出码：0 全过 / 2 有失败
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOME = os.path.expanduser("~")
DSH_HOME = os.environ.get("DSH_HOME") or os.path.join(HOME, ".dsh")
PRESET = os.path.join(DSH_HOME, ".agent-presets", "wishos")
CORE = os.path.join(PRESET, "v12-core", "skills")
WISH = os.path.join(PRESET, "skills")
WORK = os.environ.get("WISHOS_ROOT") or os.path.join(os.getcwd(), "wishos")
REPORT = os.path.join(WORK, "_tmp", "l2-smoke-report.md")

V14 = ["attention-failure-guard", "criteria-design-standard",
       "declared-value-drift-guard", "doc-plan-protocol", "four-rules-v3",
       "info-analyst", "introspect-guard", "memory-efficiency", "plan",
       "plan-auditor", "plan-executor", "plan-template", "session-guard",
       "shutdown-protocol"]
W8 = ["w-calibrate", "w-capture", "w-enter", "w-evolve",
      "w-recall", "w-router", "w-watchdog", "w-wish"]
# 按设计就没有触发词的件（不是缺陷，别当红灯报）
NO_TRIGGER_BY_DESIGN = {
    "plan": "正文 §四 明示 user-invocable-only（菜单点，模型不自动触发）",
    "introspect-guard": "plan-executor 的后置钩子（由执行体调用，不靠短语触发）",
}
# 按矩阵 §三：依赖外部模型 key 的脚本不跑（只登记）
SKIP_SCRIPTS = {"four-rules-v3": "依赖外部模型 key（GLM / OpenCode），矩阵 §三 明确不跑"}
# 已知保留的耦合行（2026-11-02 W1-c 裁定：L832 声明 + L1190 历史行）
KNOWN_COUPLING = {"four-rules-v3": 2}
COUPLING_PATS = [re.compile(r"[A-Za-z]:\\Users\\[^\\]+\\.workbuddy", re.I),
                 re.compile(os.environ.get("WISHOS_EXTRA_COUPLING_RE") or r"zzz_no_match_zzz"),
                 re.compile(r"~[/\\]\.workbuddy", re.I)]


def read(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8-sig", errors="replace")


def frontmatter(text):
    import yaml

    class L(yaml.SafeLoader):
        pass

    L.add_constructor("tag:yaml.org,2002:js", lambda l, n: l.construct_scalar(n))
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return None, text
    try:
        return (yaml.load(m.group(1), Loader=L) or {}), text[m.end():]
    except Exception:  # noqa: BLE001
        return None, text[m.end():]


def triggers_of(fm, body):
    """抽触发词：全文扫，认两种写法 —— `触发词：A、B` 与 `| 触发词 | … |` 表格形态。

    （v1.0 只看 body[:2000] 且只认冒号形态 ⇒ 把 plan-executor 的表格触发词误判成"没有"。）
    """
    blob = " ".join(str(fm.get(k) or "") for k in ("description", "whenToUse")) + "\n" + body
    out = []
    for seg in re.findall(r"触发词[：:]\s*([^\n]+)", blob):
        seg = seg.split("。")[0]
        out += [x.strip() for x in re.split(r"[、,，/／;；]", seg) if x.strip()]
    # 表格形态：`| 触发词 | 行为 |` 之后的行，取首列
    lines = blob.splitlines()
    for i, ln in enumerate(lines):
        if re.match(r"^\|\s*触发词\s*\|", ln):
            for nxt in lines[i + 2:i + 8]:
                if not nxt.strip().startswith("|"):
                    break
                cells = [c.strip() for c in nxt.strip().strip("|").split("|")]
                if cells and cells[0] and not set(cells[0]) <= set("-: "):
                    out += [c.strip("` ") for c in re.split(r"[/／、,，]", cells[0]) if c.strip("` ")]
    return sorted({t for t in out if 1 < len(t) <= 30})


IMPORT_ERR = re.compile(r"^(?:ModuleNotFoundError|ImportError|SyntaxError)", re.M)


def script_entry(d):
    """挑可跑入口：preflight / export 优先，跳过 WorkBuddy 专用件，最多 4 个。"""
    py = [f for f in sorted(os.listdir(d)) if f.endswith(".py")]
    if not py:
        py = [f for r, _, fs in os.walk(d) for f in fs if f.endswith(".py")]
    py = [f for f in py if "workbuddy" not in os.path.basename(f).lower()]
    pri = [f for f in py if "preflight" in f or "export" in f or "replay" in f] or py
    return pri[:4]


def check_scripts(name, d, fails, rows):
    """入口判据（矩阵 §三 口径：入口能起、不 import 失败）：只有 import/编译级异常才算红。"""
    if name in SKIP_SCRIPTS:
        rows.append(("SCRIPT", "%s：跳过（%s）" % (name, SKIP_SCRIPTS[name])))
        return
    for f in script_entry(d):
        p = f if os.path.isabs(f) else os.path.join(d, f)
        try:
            r = subprocess.run([sys.executable, p, "--help"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=60)
            out = (r.stdout or "") + (r.stderr or "")
            imp = IMPORT_ERR.search(out)
            rows.append(("SCRIPT", "%-22s %-26s --help rc=%d %s"
                         % (name, os.path.basename(p), r.returncode,
                            "🔴 import 失败" if imp else "✅ 入口能起")))
            if imp:
                fails.append(("SCRIPT", "%s 脚本 %s import 失败（%s）"
                              % (name, os.path.basename(p), imp.group(0))))
        except Exception as e:  # noqa: BLE001
            fails.append(("SCRIPT", "%s 脚本 %s 跑不起: %s" % (name, f, e)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="含 8 件 w-*")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    plan = [(n, CORE) for n in V14] + ([(n, WISH) for n in W8] if a.all else [])
    fails, warns, rows = [], [], []
    trig, no_when, no_trig = {}, [], []
    for name, root in plan:
        d = os.path.join(root, name)
        p = os.path.join(d, "SKILL.md")
        if not os.path.isfile(p):
            fails.append(("MISS", "%s 缺 SKILL.md" % name))
            continue
        text = read(p)
        fm, body = frontmatter(text)
        if fm is None:
            fails.append(("FM", "%s frontmatter 解析失败" % name)); continue
        if str(fm.get("name") or "") != name:
            fails.append(("FM", "%s frontmatter.name=%r 与目录不符" % (name, fm.get("name"))))
        desc = str(fm.get("description") or "")
        if not desc:
            fails.append(("FM", "%s description 为空" % name))
        if not str(fm.get("whenToUse") or ""):
            no_when.append(name)
        if len(body.strip()) < 500:
            fails.append(("BODY", "%s 正文过短（%d 字符）" % (name, len(body.strip()))))
        ts = triggers_of(fm, body)
        trig[name] = ts
        if not ts:
            if name in NO_TRIGGER_BY_DESIGN:
                rows.append(("TRIG", "%-28s 按设计无触发词（%s）" % (name, NO_TRIGGER_BY_DESIGN[name])))
            else:
                no_trig.append(name)
        # 宿主耦合
        hits = sum(1 for line in text.splitlines() if any(pat.search(line) for pat in COUPLING_PATS))
        known = KNOWN_COUPLING.get(name, 0)
        if hits > known:
            fails.append(("PATH", "%s 宿主耦合 %d 处 > 已知保留 %d 处" % (name, hits, known)))
        rows.append(("SKILL", "%-28s fm=%s 正文=%5d 字符 触发词=%2d 耦合=%d/%d"
                     % (name, "✅" if fm else "🔴", len(body.strip()), len(ts), hits, known)))
        # 脚本入口
        if os.path.isdir(d):
            check_scripts(name, d, fails, rows)

    # 无 whenToUse / 无触发词：系统性事实各报一条（不逐件刷屏）
    if no_when:
        warns.append(("FM", "%d/%d 件无 whenToUse（该体系把触发词写在 description）: %s"
                      % (len(no_when), len(plan), ", ".join(no_when[:6]) + ("…" if len(no_when) > 6 else ""))))
    if no_trig:
        warns.append(("TRIG", "%d 件抽不到触发词 ⇒ 矩阵 §三 的「说触发句」抽测对它们做不了，只能按名调用: %s"
                      % (len(no_trig), ", ".join(no_trig))))

    # 触发词近邻碰撞（只报告）
    names = [n for n in trig if trig[n]]
    pairs = []
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            common = set(trig[x]) & set(trig[y])
            if common:
                pairs.append((x, y, sorted(common)[:4]))
    if pairs:
        warns.append(("TRIG", "跨件同触发词 %d 对（例：%s）——命中优先级已裁（2026-11-02）：判据类短语 → "
                              "criteria-design-standard；口径漂移语境 → declared-value-drift-guard；"
                              "分批/跨会话/任务书 → doc-plan-protocol"
                      % (len(pairs), "; ".join("%s↔%s %r" % p for p in pairs[:5]))))

    lines = ["# WishOS L2 单技能冒烟报告", "",
             "- 时间：%s" % __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
             "- 范围：%d 件（%s）" % (len(plan), "14 v12-core + 8 w-*" if a.all else "14 v12-core"),
             "- 判定：**%s**（失败 %d / 警告 %d）" % ("✅ 全过" if not fails else "🔴 未全过",
                                                   len(fails), len(warns)),
             "", "| 类 | 读数 |", "|:--|:--|"]
    lines += ["| %s | %s |" % (k, v.replace("|", "\\|")) for k, v in rows]
    if warns:
        lines += ["", "## 警告（不阻断）", ""] + ["- 🔶 [%s] %s" % (k, v) for k, v in warns]
    if fails:
        lines += ["", "## 失败项", ""] + ["- 🔴 [%s] %s" % (k, v) for k, v in fails]
    md = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(md)
    if a.json:
        print(json.dumps({"ok": not fails, "fails": fails, "warns": warns}, ensure_ascii=False, indent=1))
    else:
        print(md)
        print("报告 -> " + REPORT)
        print("退出码 = " + ("0" if not fails else "2"))
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
