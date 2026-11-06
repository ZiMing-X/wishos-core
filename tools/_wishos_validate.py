#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_wishos_validate.py — WishOS Protocol v0.1 产物校验（标准库实现 · 只读）

按包内 `schemas/*.json`（JSON Schema draft 2020-12 子集）校验数据根下的 5 类产物：
  tickets/*.json → ticket · cards/**/*.md(frontmatter) → card ·
  calibration/pairs.jsonl → calibration · recall/*.jsonl → recall ·
  nodes/**/*.md(frontmatter) → node

用法
    python tools/_wishos_validate.py --root <数据根>
    python tools/_wishos_validate.py --root <数据根> --json
退出码：0 = 全过（无产物也算过）；2 = 有不合规；3 = 数据根不可读
只读：不写任何文件。
支持的关键字：type / required / properties / items / enum / const / pattern /
minLength / minItems / minimum / maximum / oneOf / additionalProperties
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PKG = Path(__file__).resolve().parent.parent
SCHEMAS = PKG / "schemas"


# ── YAML 子集（frontmatter 用：标量 / 块列表 / 一层嵌套映射 / 行内 JSON 数组）────
def _scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    low = v.lower()
    if low in ("null", "~", ""):
        return None
    if low in ("true", "false"):
        return low == "true"
    try:
        return json.loads(v) if v[:1] in "[{" else (float(v) if "." in v else int(v))
    except Exception:
        return v


def mini_yaml(text: str) -> dict:
    """极简 YAML 子集：标量 / 块列表 / 一层嵌套映射（按缩进递归）。"""
    items: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        items.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))

    def parse_block(start: int, indent: int):
        if start >= len(items) or items[start][0] < indent:
            return None, start
        i = start
        if items[i][1].startswith("- "):
            arr = []
            while i < len(items) and items[i][0] == indent and items[i][1].startswith("- "):
                arr.append(_scalar(items[i][1][2:]))
                i += 1
            return arr, i
        obj: dict = {}
        while i < len(items) and items[i][0] == indent and not items[i][1].startswith("- "):
            line = items[i][1]
            if ":" not in line:
                i += 1
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v != "":
                obj[k] = _scalar(v)
                i += 1
                continue
            if i + 1 < len(items) and items[i + 1][0] > indent:
                sub, nxt = parse_block(i + 1, items[i + 1][0])
            else:
                sub, nxt = None, i + 1
            obj[k] = sub
            i = nxt
        return obj, i

    parsed, _ = parse_block(0, 0)
    return parsed if isinstance(parsed, dict) else {}


def frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    try:
        return mini_yaml(m.group(1))
    except Exception:
        return None


# ── JSON Schema 子集校验 ─────────────────────────────────────────────────────
def _type_ok(value, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    return True


def validate(value, schema: dict, path: str = "$") -> list[str]:
    errs: list[str] = []
    if not isinstance(schema, dict):
        return errs
    if "oneOf" in schema:
        branches = schema["oneOf"]
        if not any(not validate(value, b, path) for b in branches):
            errs.append(f"{path}: 不匹配 oneOf 任一分支")
        else:
            return errs
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: 应为常量 {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: 取值 {value!r} 不在枚举 {schema['enum']}")
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(value, x) for x in types):
            errs.append(f"{path}: 类型应 {types}，实为 {type(value).__name__}")
            return errs
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errs.append(f"{path}: 缺必填字段 {req!r}")
        props = schema.get("properties") or {}
        for k, sub in props.items():
            if k in value:
                errs.extend(validate(value[k], sub, f"{path}.{k}"))
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(props)
            if extra:
                errs.append(f"{path}: 多余字段 {sorted(extra)}")
    elif isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(f"{path}: 至少 {schema['minItems']} 项")
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(value):
                errs.extend(validate(item, items, f"{path}[{i}]"))
    elif isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(f"{path}: 长度应 ≥{schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: 不匹配 pattern {schema['pattern']}")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: 应 ≥{schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: 应 ≤{schema['maximum']}")
    return errs


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def check(root: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []

    def add(kind: str, file: str, ptr: str, errs: list[str]) -> None:
        rows.append({"kind": kind, "file": file, "pointer": ptr, "errors": errs})
        for e in errs:
            errors.append(f"{kind} {file} {e}")

    tk = load_schema("ticket.schema.json")
    for f in sorted((root / "brain" / "tickets").glob("*.json")):
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            add("ticket", f.name, "json", [f"非法 JSON: {e}"])
            continue
        add("ticket", f.name, "$", validate(v, tk))

    ck = load_schema("card.schema.json")
    for f in sorted((root / "brain" / "cards").rglob("*.md")):
        fm = frontmatter(f)
        if fm is None:
            add("card", str(f.relative_to(root)), "frontmatter", ["无 frontmatter"])
            continue
        add("card", str(f.relative_to(root)), "$", validate(fm, ck))

    cal = load_schema("calibration.schema.json")
    p = root / "brain" / "calibration" / "pairs.jsonl"
    if p.is_file():
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                v = json.loads(line)
            except Exception as e:  # noqa: BLE001
                add("calibration", "pairs.jsonl", f"L{i}", [f"非法 JSON: {e}"])
                continue
            add("calibration", "pairs.jsonl", f"L{i}", validate(v, cal))

    rc = load_schema("recall.schema.json")
    for f in sorted((root / "brain" / "recall").glob("*.jsonl")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                v = json.loads(line)
            except Exception as e:  # noqa: BLE001
                add("recall", f.name, f"L{i}", [f"非法 JSON: {e}"])
                continue
            add("recall", f.name, f"L{i}", validate(v, rc))

    nd = load_schema("node.schema.json")
    for f in sorted((root / "brain" / "nodes").rglob("*.md")):
        fm = frontmatter(f)
        if fm is None:
            add("node", str(f.relative_to(root)), "frontmatter", ["无 frontmatter"])
            continue
        add("node", str(f.relative_to(root)), "$", validate(fm, nd))
    return rows, errors


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="WishOS Protocol 产物校验（只读）")
    ap.add_argument("--root", help="数据根（默认 $WISHOS_ROOT 或 $PWD/wishos）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root) if args.root else Path(os.environ.get("WISHOS_ROOT") or (Path.cwd() / "wishos"))
    if not root.is_dir():
        print(f"🔴 退码 3：数据根不可读 {root}", file=sys.stderr)
        return 3
    rows, errors = check(root)
    per_kind: dict[str, dict] = {}
    for r in rows:
        d = per_kind.setdefault(r["kind"], {"files": 0, "bad": 0})
        d["files"] += 1
        if r["errors"]:
            d["bad"] += 1
    rc = 0 if not errors else 2
    if args.json:
        print(json.dumps({"root": str(root), "per_kind": per_kind, "rows": rows,
                          "errors": errors, "rc": rc}, ensure_ascii=False, indent=1))
        return rc
    print(f"_wishos_validate.py —— WishOS Protocol v0.1 产物校验 · root={root}")
    for kind, d in per_kind.items():
        print(f"  {kind}: 文件/行 {d['files']} · 不合规 {d['bad']}")
    if errors:
        print("\n不合规明细（前 20）：")
        for e in errors[:20]:
            print("  🔴", e)
        print(f"\n🔴 有不合规项（rc=2）")
    else:
        print("\n✅ 全部符合 schema（rc=0）")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
