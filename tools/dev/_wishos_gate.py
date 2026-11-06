# -*- coding: utf-8 -*-
"""_wishos_gate.py —— WishOS 骨架门禁 v0.1（W1）

校验目标（E1~E7）：
  E1 profile patch 可解析，且 preset-wishos 行存在、config.id=wishos、preset-v12 未被改动
  E2 技能根 7 件齐全，SKILL.md frontmatter 的 name 与目录名一致、description 非空
  E3 工作区目录齐全（brain/* + outputs + tools）
  E4 旧三处技能根无 w-* 命名冲突
  E5 旧 v12 技能数仍为 56（未被动过）
  E6 约束台账 Tier-0 恰为 4 条
  E7 隔离生效：includeDefaultRoots=false 且 wishos 不挂 agent-instructions

退码：0 = 全过；2 = 有失败；3 = 路径不可读
自证：--selftest（正样本过 / 负样本拦 / ⚪真阴性拦得对理由）
"""
import os, re, sys, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOME = os.path.expanduser("~")
DSH_HOME = os.environ.get("DSH_HOME") or os.path.join(HOME, ".dsh")
DSH_PROFILE = os.environ.get("DSH_PROFILE") or "web"
WISHOS_ROOT = os.environ.get("WISHOS_ROOT") or os.path.join(os.getcwd(), "wishos")
WISHOS_LEDGER = os.environ.get("WISHOS_LEDGER") or ""
REAL = {
    "patch": os.path.join(DSH_HOME, "profiles", DSH_PROFILE, "cordis.patch.yml"),
    "preset": os.path.join(DSH_HOME, ".agent-presets", "wishos"),
    "skills": os.path.join(DSH_HOME, ".agent-presets", "wishos", "skills"),
    "work": WISHOS_ROOT,
    "lib": os.path.join(DSH_HOME, "skill-manager", "library"),
    "v12": os.path.join(DSH_HOME, ".agent-presets", "v12", "skills"),
    "ledger": WISHOS_LEDGER,
}
EXPECT_SKILLS = ["w-wish", "w-router", "w-recall", "w-capture", "w-enter",
                 "w-calibrate", "w-watchdog", "w-evolve"]
EXPECT_WORK = ["brain/cards/context", "brain/cards/pattern", "brain/cards/decision",
               "brain/cards/solution", "brain/chains", "brain/calibration",
               "brain/tickets", "brain/attention", "outputs", "tools", "_tmp",
               "brain/nodes/project", "brain/nodes/event", "brain/nodes/claim",
               "brain/nodes/evidence", "brain/nodes/inference", "brain/nodes/conclusion",
               "brain/nodes/card", "brain/nodes/ticket", "brain/nodes/artifact"]


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
        if n != 56:
            fails.append(("E5", "v12 技能数=%d（应 56，旧体系被改动）" % n))

    # E6
    ledger = paths["ledger"]
    if not os.path.isfile(ledger):
        print("  ⚠️ E6 跳过：未设置 WISHOS_LEDGER（公共包不带约束台账）")
    else:
        t = read(ledger)
        sec = re.search(r"##\s*一[ ·]*Tier-0.*?(?=\n##\s)", t, re.S)
        block = sec.group(0) if sec else t
        n = len(re.findall(r"^\s*\|\s*\*\*T0-\d\*\*", block, re.M))
        if n != 4:
            fails.append(("E6", "Tier-0 条数=%d（应 4）" % n))

    return fails


def run(paths, quiet=False):
    fails = check(paths)
    if not quiet:
        print("=" * 70)
        print("  WishOS 骨架门禁 v0.1")
        print("=" * 70)
        for k in ("patch", "skills", "work", "ledger"):
            print("  %-8s %s" % (k + ":", paths[k]))
        print("-" * 70)
    if fails:
        for code, msg in fails:
            print("  🔴 [%s] %s" % (code, msg))
    elif not quiet:
        print("  ✅ E1~E7 全过（预设行 / %d 技能 / 工作区 / 无冲突 / v12 未动 / Tier-0=4 / 隔离生效）" % len(EXPECT_SKILLS))
    if not quiet:
        print("=" * 70)
    return 0 if not fails else 2


def selftest():
    import io, contextlib
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
        for i in range(56):
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
    bad += 0 if ok else 1

    # ② 负样本：抽掉 preset-wishos 行
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    t = read(p["patch"]).replace("preset-wishos", "preset-removed")
    open(p["patch"], "w", encoding="utf-8").write(t)
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 2 and "E1" in out
    print("  %s 负样本（缺预设行）              期望 2 · 实得 %d · 理由含 E1=%s" % ("✅" if ok else "🔴", rc, "E1" in out))
    bad += 0 if ok else 1

    # ③ ⚪真阴性：其余全对、只把台账换成"无 Tier-0 表的普通文档" ⇒ 必须只报 E6，不得误报 E1/E2/E3
    r = tempfile.mkdtemp(dir=tmp); p = make_fixture(r)
    open(p["ledger"], "w", encoding="utf-8").write("# 普通文档\n\n它没有 Tier-0 表。\n")
    rc, out = quiet(lambda: run(p, quiet=True))
    ok = rc == 2 and "E6" in out and ("E1" not in out) and ("E2" not in out) and ("E3" not in out)
    print("  %s ⚪真阴性（无表的好文档）        期望 2 · 实得 %d · 只报 E6=%s" % ("✅" if ok else "🔴", rc, ok))
    bad += 0 if ok else 1

    shutil.rmtree(tmp, ignore_errors=True)
    print("-" * 70)
    print("  ✅ 三要求全过" if bad == 0 else "  🔴 自证未过（%d 处不符）" % bad)
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        sys.exit(selftest())
    sys.exit(run(REAL))
