# tools/dev — 作者侧「完整环境」校验工具（不随公共自检）

> ⚠️ 这里的 4 个工具是 **作者完整环境**（22 技能 = 8 `w-*` + 14 v12-core、v12 预设、约束台账、巡检报告、手写 profile 补丁行）的判据。
> 公共安装者**不要**把它们当自检判定——环境不全时它们会**系统性假红**（这是实测结论，不是配置问题）。
> 公共自检请用上一层：`tools/_wishos_selfcheck.py`（包 + 数据面）与 `tools/_wishos_cost_report.py`（成本读数）。

| 工具 | 依赖的完整环境 | 用途 |
|:--|:--|:--|
| `_wishos_gate.py` | profile 里的 `preset-wishos` 补丁行、v12 预设 56 件、可选约束台账 | 骨架门禁 E1~E7 |
| `_wishos_verify.py` | 22 件可加载技能、v12-core 目录、profile 补丁双技能根、真实会话转录 | L0 磁盘 + L1 会话面验证 |
| `_wishos_l2_smoke.py` | v12-core 14 件（默认范围） | L2 技能冒烟 |
| `_wishos_l3_e2e.py` | `outputs/check-*.md`、`outputs/closure-*.md`、brain 票据/卡片/节点 | L3 端到端判据 |

**路径环境变量**（与公共工具一致，便于在作者机上跑）：

```sh
DSH_HOME=<~/.dsh> · DSH_PROFILE=<web> · WISHOS_ROOT=<工作区>/wishos
WISHOS_LEDGER=<约束台账路径>        # 不设则 gate 跳过 E6
WISHOS_EXTRA_COUPLING_RE=<额外耦合正则>   # 可选
```

**作者机实测（2026-11-06，wishos-core 0.2.0 打包前）**：

```text
gate     rc=0
verify   rc=0（--auto）
l2       rc=0（--all）
l3       rc=0（--latest / --closure / --unclosed）
```

> 这些工具保留了作者环境的 2 处「已知耦合行」判据（见 `_wishos_verify.py` 的 PATHS 行）；换环境必须先改判据，否则红项无意义。
