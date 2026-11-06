# WishOS Protocol v0.1

> **协议 vs 实现**：本文件是**协议**（规范性）；`wishos-core` 是它的**参考实现**（v0.3.x）。
> 协议版本与实现版本分离：`WishOS Protocol v0.1` ≠ `wishos-core 0.3.0`。

WishOS 是一个**面向个人 agent 的工作法框架**：它定义「愿望如何变成可验收的工作、工作如何留下可复用的知识、
知识如何被度量与进化」，而**不提供**领域能力。框架 = 角色 + 产物 + 门禁 + 数据布局 + 扩展规则。

---

## 1. 规范用语

- **MUST / MUST NOT**：遵守才可称「WishOS 兼容」
- **SHOULD**：默认遵守，偏离需在实现 README 写明理由
- **MAY**：可选

## 2. 角色（Role Contracts）

| 角色 | 职责 | MUST NOT |
|:--|:--|:--|
| **Wish**（入口） | 把一句自然语言愿望编译为 Ticket（目标/验收/预算/风险/上下文） | 不填参数的愿望不得开工；无 `acceptance` 不接单 |
| **Router** | 编译与派发；一子任务一 Worker；汇总 Worker 三行交回 | MUST NOT 自己执行具体任务 |
| **Worker** | 单任务执行，交回「结果 / 判据对照 / 靠什么错在哪」三行 | 不互相通信；大结果必须落盘只回摘要（>8 KB 或 >200 行） |
| **Capture** | 成功写结论卡、失败/踩坑写经验卡；可证伪门禁 | 同一结论重复建卡（应合并 `merged_from`） |
| **Recall** | 召回「卡片→链→愿望→产出」；唯一写 = 命中记账 | 不修改卡片内容；不出本机 |
| **Calibrate** | 决策当场写 `p`，结局出现后补 `y`；算 Brier/ECE | `p`/`y` 不得互相引用；`y` 不得来自自评 |
| **Watchdog** | 只读巡检：去重/陈旧/待校准/回退率/注意力/断链/成本 | MUST NOT 修改任何生产件 |
| **Evolve** | 同 `pattern_key` 复用 ≥3 次 + 外部证据 + 人批，才允许新增能力 | MUST NOT 自动安装第三方插件 |
| **Enter** | 把「进入 X」解析为图谱节点并注入 1 跳邻居；只读定位 | MUST NOT 猜歧义节点（>1 候选必须问人） |

## 3. 产物与 Schema（规范性）

全部产物置于**数据根**下（见 §5）。JSON Schema 见 `schemas/`：

| 产物 | 落点 | Schema |
|:--|:--|:--|
| Ticket | `brain/tickets/<YYYYMMDD-HHMM>-<slug>.json` | `schemas/ticket.schema.json` |
| 卡片（结论/经验） | `brain/cards/<类型>/c-<YYYYMMDD>-<slug>.md` | `schemas/card.schema.json` |
| 校准对 | `brain/calibration/pairs.jsonl`（一行一对） | `schemas/calibration.schema.json` |
| 召回记账 | `brain/recall/<YYYYMMDD>.jsonl`（一行一条，含 0 命中） | `schemas/recall.schema.json` |
| 图谱节点 | `brain/nodes/<type>/<id>.md` | `schemas/node.schema.json` |
| 产出件 | `outputs/<ticket_id>/…` | 无 schema（MUST 在 Ticket `result_artifacts` 登记路径） |

**可选产物（MAY）**：`brain/chains/`（推理链）、`brain/attention/<date>.jsonl`（唤起人记账）、`brain/focus.json`（焦点栈）、
`outputs/check-<YYYYMMDD>.md`（巡检报告，四节：读数/异常/建议/需人决定）、`outputs/closure-<YYYYMMDD>.md`（收工记录）。

## 4. 门禁（Gates）

| # | 门禁 | 判据 | 强制级 |
|:-:|:--|:--|:--|
| G1 | **Tier-0 四条** | ①不可逆外部动作须人确认 ②敏感数据不出本机 ③自学产物必带可证伪判据 ④不绕过宿主安全 | MUST |
| G2 | **验收** | Ticket 的 `acceptance` 每条可复跑/可观测；「看过了」不算 | MUST |
| G3 | **可证伪** | 卡片 `falsifiable` 非空，且写的是「什么情况下算错」 | MUST |
| G4 | **校准分离** | `p` 写入早于 `y`；`y` 来自体系外；禁止自评闭环 | MUST |
| G5 | **进化闸** | 同 `pattern_key` ≥3 次 + evidence + 人批 | MUST |
| G6 | **只读巡检** | Watchdog 不改生产件；要改只能出提案 | MUST |
| G7 | **大结果落盘** | Worker 结果 >8 KB 或 >200 行 ⇒ 落 `outputs/` 只回摘要 + 路径 | SHOULD |

> 门禁是**判据**，不是自动执行器：参考实现用技能正文 + 校验工具体现；实现方 SHOULD 提供可跑的校验入口。

## 5. 数据布局（规范性）

```text
<workspace>/wishos/            # 数据根（$WISHOS_ROOT）
├── brain/
│   ├── cards/{context,pattern,decision,solution}/
│   ├── tickets/
│   ├── calibration/pairs.jsonl
│   ├── recall/<YYYYMMDD>.jsonl
│   ├── nodes/{project,event,claim,evidence,inference,conclusion,card,ticket,artifact,session}/
│   ├── chains/ · attention/
│   └── focus.json             # 可选（焦点栈）
├── outputs/<ticket_id>/       # 产出件；巡检/收工报告可直接放 outputs/
└── _tmp/                      # 一次性件
```

- **MUST**：数据根与实现解耦——插件/包本身**不创建**数据根；首次使用按需创建。
- **MUST**：技能/文档中的相对路径（如 `brain/cards/…`）一律**相对数据根**，不得相对会话工作目录。

## 6. 扩展规则（Extension Contract）

实现方 MAY 增加领域技能/工具，但 MUST 遵守：

1. **新技能**：frontmatter `name` 与目录名一致、`description` 含触发词；默认由 `Evolve` 审批后加入（G5）。
2. **新产物**：不得复用已有产物 ID 空间；新增 schema MUST 随实现发布。
3. **新角色**：如引入新角色（如「审核」），MUST 说明其与 Router/Capture 的边界，且不得绕过 Tier-0。
4. **不追加硬门禁**：新增约束默认 SHOULD（引导），除非作者显式升为 MUST 并在 README 声明。

## 7. 采纳档位（Adoption Profiles）

框架支持**部分采纳**（这是框架与应用的差别）：

| 档 | 内容 | 适用 |
|:--|:--|:--|
| **L1 最小闭环** | `w-wish` + `w-router` + `w-capture` + `w-recall` | 只想把「愿望→验收→经验卡→下次先查」跑起来 |
| **L2 标准** | L1 + `w-calibrate` + `w-watchdog` | 还要「可校准 + 可观测」 |
| **L3 完整** | L2 + `w-evolve` + `w-enter` + 图谱/链/焦点栈 | 要长期演化与可导航的第二大脑 |

> 参考实现 `wishos-core` 默认全量装载 8 技能；**允许**按 §6 增删（实现方 MUST 在 README 说明裁剪影响）。

## 8. 合规性声明（Compliance）

一个实现称为「WishOS Protocol v0.1 兼容」需满足：

1. 提供 §2 全部角色的执行体（技能/工具/文档任一形态），并公开其契约；
2. 产物符合 §3 schema（允许附加字段；不允许缺失 MUST 字段）；
3. 数据布局符合 §5（`$WISHOS_ROOT` 可配置，相对路径相对数据根）；
4. 门禁 §4 的 MUST 项有可观测判据（脚本/评审清单任一）；
5. 声明所采纳的档位（§7）与本实现相对协议的偏差。

## 9. 版本与演进

- 协议版本：`vMAJOR.MINOR`；删除/改义 MUST 项 ⇒ MAJOR 升版；新增可选产物/角色 ⇒ MINOR。
- 实现版本独立演进；实现 MUST 在 README 标注「对应协议版本」。
- 本协议缺失的语义，以参考实现的 README 为**临时解释**，下次协议修订 MUST 收敛回协议。

---

*WishOS Protocol v0.1 · 2026-11-06 · 规范性文件；实现：`wishos-core 0.3.x`*
