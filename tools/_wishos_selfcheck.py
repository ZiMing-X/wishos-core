#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_wishos_selfcheck.py — WishOS Core 公共自检 v1.0（2026-11-06）

给**公共安装者**用的只读自检（不依赖作者的完整环境）：
  A. 包完整性：package.json / dsh.bundle.patch / patch 的 insert 行 / 8 个 w-* SKILL.md /
     skills.manifest.json 与盘上一致
  B. 数据面：WISHOS_ROOT 下 brain/{cards,tickets,calibration,recall} 等目录是否存在、
     卡片 frontmatter 是否齐（statement/evidence/falsifiable/source）、
     tickets/*.json 是否合法 JSON、calibration/recall 的 jsonl 是否每行合法
  C. 成本读数入口：提示调用同目录 `_wishos_cost_report.py --selfcheck`

用法
    python _wishos_selfcheck.py                       # 自动定位包根 + 数据根（$WISHOS_ROOT 或 $PWD/wishos）
    python _wishos_selfcheck.py --root <wishos 数据根>  # 指定数据根
    python _wishos_selfcheck.py --json
退出码：0 = 包检查全过（数据面只报读数/警告）；2 = 包检查失败；3 = 包根不可读
只读：不创建/不修改任何文件。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REQUIRED_CARD_KEYS = ("statement", "evidence", "falsifiable")
EXPECT_SKILLS = ["w-calibrate", "w-capture", "w-enter", "w-evolve",
                 "w-recall", "w-router", "w-watchdog", "w-wish"]
DATA_DIRS = ["brain/cards", "brain/tickets", "brain/recall", "brain/calibration",
             "brain/nodes", "brain/chains", "brain/attention", "outputs", "_tmp"]


def parse_frontmatter(text: str) -> dict | None:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    lines = m.group(1).splitlines()
    out: dict = {}
    for idx, line in enumerate(lines):
        if line.startswith((" ", "\t", "-")) or ":" not in line:
            continue
        k, v = line.split(":", 1)
        if not v.strip():
            # block value（YAML 列表/缩进块）：收集紧随的缩进行，非空即视为有内容
            block = []
            for nxt in lines[idx + 1:]:
                if nxt.startswith((" ", "\t")):
                    block.append(nxt.strip())
                else:
                    break
            v = " ".join(block)
        out[k.strip()] = v.strip()
    return out


def check_package(pkg: Path) -> list[dict]:
    items: list[dict] = []

    def ck(name: str, cond: bool, detail: str = "") -> None:
        items.append({"item": name, "ok": bool(cond), "detail": detail})

    pj_path = pkg / "package.json"
    pj = {}
    if pj_path.is_file():
        try:
            pj = json.loads(pj_path.read_text(encoding="utf-8"))
            ck("package.json 可解析", True, f"{pj.get('name')}@{pj.get('version')}")
        except Exception as e:  # noqa: BLE001
            ck("package.json 可解析", False, str(e))
    else:
        ck("package.json 存在", False, str(pj_path))
    ck("声明 dsh.bundle.patch", bool(((pj.get("dsh") or {}).get("bundle") or {}).get("patch")),
       str(((pj.get("dsh") or {}).get("bundle") or {}).get("patch")))
    patch = pkg / "cordis.patch.yml"
    ok_patch = patch.is_file() and "- insert:" in patch.read_text(encoding="utf-8")
    ck("patch 文件含 insert", ok_patch, str(patch.name))
    bad_skills = []
    for n in EXPECT_SKILLS:
        f = pkg / "skills" / n / "SKILL.md"
        fm = parse_frontmatter(f.read_text(encoding="utf-8")) if f.is_file() else None
        if fm is None or fm.get("name") != n or not str(fm.get("description", "")).strip():
            bad_skills.append(n)
    ck("8 个 w-* 技能齐全且 frontmatter 一致", not bad_skills, ", ".join(bad_skills) or "8/8")
    man = pkg / "skills.manifest.json"
    man_ok, man_detail = False, ""
    if man.is_file():
        try:
            data = json.loads(man.read_text(encoding="utf-8"))
            names = {s.get("dir") for s in data.get("skills") or []}
            man_ok = names == set(EXPECT_SKILLS)
            man_detail = f"manifest {len(names)} / 期望 {len(EXPECT_SKILLS)}"
        except Exception as e:  # noqa: BLE001
            man_detail = str(e)
    ck("skills.manifest 与盘一致", man_ok, man_detail)
    return items


def check_data(root: Path) -> dict:
    rep: dict = {"root": str(root), "dirs": {}, "cards": 0, "card_bad": [],
                 "tickets": 0, "ticket_bad": [], "calibration": 0, "calibration_bad": [],
                 "recall_logs": 0, "recall_bad": [], "warnings": []}
    if not root.is_dir():
        rep["warnings"].append(f"数据根不存在：{root}（首次使用时按需创建，见 README「数据目录」）")
        return rep
    for d in DATA_DIRS:
        rep["dirs"][d] = (root / d).is_dir()
    for f in (root / "brain" / "cards").rglob("*.md"):
        rep["cards"] += 1
        fm = parse_frontmatter(f.read_text(encoding="utf-8"))
        if fm is None or any(not str(fm.get(k, "")).strip() for k in REQUIRED_CARD_KEYS) \
                or not str(fm.get("source", "")).strip():
            rep["card_bad"].append(str(f.relative_to(root)))
    for f in (root / "brain" / "tickets").glob("*.json"):
        rep["tickets"] += 1
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            rep["ticket_bad"].append(f.name)
    cal = root / "brain" / "calibration" / "pairs.jsonl"
    if cal.is_file():
        for i, line in enumerate(cal.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            rep["calibration"] += 1
            try:
                d = json.loads(line)
                if not isinstance(d.get("p"), (int, float)) or "y" not in d:
                    rep["calibration_bad"].append(f"L{i}:缺 p/y")
            except Exception:  # noqa: BLE001
                rep["calibration_bad"].append(f"L{i}:非法 JSON")
    for f in (root / "brain" / "recall").glob("*.jsonl"):
        rep["recall_logs"] += 1
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except Exception:  # noqa: BLE001
                rep["recall_bad"].append(f"{f.name}:L{i}")
    return rep


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="WishOS Core 公共自检（只读）")
    ap.add_argument("--root", help="WishOS 数据根（默认 $WISHOS_ROOT 或 $PWD/wishos）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    pkg = Path(__file__).resolve().parent.parent
    if not (pkg / "package.json").is_file():
        print(f"🔴 退码 3：包根不可读（{pkg}）", file=sys.stderr)
        return 3
    pkg_items = check_package(pkg)
    root = Path(args.root) if args.root else Path(
        os.environ.get("WISHOS_ROOT") or (Path.cwd() / "wishos"))
    data = check_data(root)
    pkg_fail = [i for i in pkg_items if not i["ok"]]
    rc = 0 if not pkg_fail else 2
    if args.json:
        print(json.dumps({"package": str(pkg), "package_items": pkg_items,
                          "data": data, "rc": rc}, ensure_ascii=False, indent=1))
        return rc
    print(f"_wishos_selfcheck.py —— WishOS Core 公共自检 · 包根 {pkg}")
    for i in pkg_items:
        print(f"  {'✅' if i['ok'] else '🔴'} {i['item']}" + (f"  [{i['detail']}]" if i["detail"] else ""))
    print(f"\n数据根：{data['root']}")
    if data["warnings"]:
        for w in data["warnings"]:
            print(f"  🔶 {w}")
    else:
        missing = [d for d, ok in data["dirs"].items() if not ok]
        print(f"  目录：{len(data['dirs']) - len(missing)}/{len(data['dirs'])} 在"
              + (f"（缺：{', '.join(missing)}）" if missing else ""))
        print(f"  卡片 {data['cards']}（坏 {len(data['card_bad'])}） · 票据 {data['tickets']}（坏 {len(data['ticket_bad'])}）"
              f" · 校准 {data['calibration']}（坏 {len(data['calibration_bad'])}） · 召回日志 {data['recall_logs']}（坏 {len(data['recall_bad'])}）")
        for key in ("card_bad", "ticket_bad", "calibration_bad", "recall_bad"):
            for bad in data[key][:5]:
                print(f"  🔶 数据格式问题 [{key}] {bad}")
    print(f"\n成本读数：python {Path(__file__).resolve().parent / '_wishos_cost_report.py'} --selfcheck")
    print("✅ 包自检通过" if rc == 0 else "🔴 包自检未通过（rc=2）")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
