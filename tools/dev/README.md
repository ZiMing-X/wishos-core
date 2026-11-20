# tools/dev — 作者侧「完整环境」校验工具（不随公共自检）

> ⚠️ 这里的 4 个工具是 **作者完整环境**（21 可加载技能 = 8 `w-*` + 13 v12-core、v12 预设 42 件、约束台账、`_beacon.py` bcode 解码器、手写 profile 补丁行）的判据。
> 公共安装者**不要**把它们当自检判定——环境不全时它们会**系统性假红**（这是实测结论，不是配置问题）。
> 公共自检请用上一层：`tools/_wishos_selfcheck.py`（包 + 数据面）与 `tools/_wishos_cost_report.py`（成本读数）。

| 工具 | 依赖的完整环境 | 用途 |
|:--|:--|:--|
| `_wishos_gate.py` | profile 里的 `preset-wishos` 补丁行、v12 预设 42 件、约束台账（`WISHOS_LEDGER` 或 `$WISHOS_PROJECT/docs/…`）、`_beacon.py` 解码器 | 骨架门禁 E1~E8 + E10（13 项自证） |
| `_wishos_verify.py` | 21 件可加载技能、v12-core 目录、profile 补丁双技能根、真实会话转录 | L0 磁盘 + L1 会话面验证 |
| `_wishos_l2_smoke.py` | v12-core 14 件（默认范围；**旧代口径**，未随 T5/T6 对齐 ⇒ 现盘（13 件）必然红，属已知） | L2 技能冒烟 |
| `_wishos_l3_e2e.py` | `outputs/check-*.md`、`outputs/closure-*.md`、brain 票据/卡片/节点 | L3 端到端判据 |

**路径环境变量**（与公共工具一致，便于在作者机上跑）：

```sh
DSH_HOME=<~/.dsh>                     # cost_report / l2_smoke 读；gate / verify 走 $HOME/.dsh（l3 完全不碰 .dsh）
WISHOS_ROOT=<工作区>/wishos            # gate · verify · l2 · l3
WISHOS_PROJECT=<项目根>                # gate（约束台账默认根）· verify（自证取样）
WISHOS_LEDGER=<约束台账路径>           # gate；不设则取 $WISHOS_PROJECT/docs/V12-WishOS-约束台账-v1.0-2026-11-02.md
WISHOS_BEACON=<.../_beacon.py>        # gate 的 bcode 解码器；查找优先级 同目录 > WISHOS_BEACON > $WISHOS_ROOT/tools
WISHOS_EXTRA_COUPLING_RE=<额外耦合正则>   # l2_smoke 可选
```

> ⚠️ **默认值会假红**：`WISHOS_ROOT` / `WISHOS_PROJECT` 不设时默认取 `cwd`（`cwd/wishos` 与 `cwd/docs/…`）；不在正确 cwd 又不设变量 ⇒ E3/E6/E8 成批红（实测：包根无 env 起跑 = **22 红 rc=2**，不崩）。这是"更严"，不是"更松"。
> 解码器缺失时两种退码语义不同：`--selftest` 返 **rc=3**（自证不可跑），正式跑返 **rc=2**（E8 红）。

**作者机实测（2026-11-06，wishos-core 0.2.0 打包前）**：

```text
gate     rc=0
verify   rc=0（--auto）
l2       rc=0（--all）
l3       rc=0（--latest / --closure / --unclosed）
```

**作者机实测（2026-11-20，T6 把 gate 整版对齐到生产树代后）**：

```text
gate --selftest  rc=0（13/13）· gate rc=0（E1~E8+E10 全过）
verify --selftest rc=0（9/9）· l3 --selfcheck rc=0（10/10）
```

> 这些工具保留了作者环境的 2 处「已知耦合行」判据（见 `_wishos_verify.py` 的 PATHS 行）；换环境必须先改判据，否则红项无意义。
