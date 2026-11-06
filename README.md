# wishos-core

> **WishOS Core** —— 给 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（`dsh`）用的
> **许愿式第二大脑工作法框架** · 参考实现（preset + 8 个 `w-*` 技能 + 协议 + schema + 自检工具）。

[![release](https://img.shields.io/github/v/release/ZiMing-X/wishos-core?label=release)](https://github.com/ZiMing-X/wishos-core/releases)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![protocol](https://img.shields.io/badge/protocol-v0.1-informational)](PROTOCOL.md)

> 🟡 **状态：experimental（影响力阶段）** · 是**框架/参考实现**，不是开箱即用的产品；**不承诺产出增益**。
> 中文 | [English](README.en.md) · 安装：`dsh plugin --profile <profile> add github:ZiMing-X/wishos-core`

## 适用版本与兼容性（先看这张表）

| 项 | 值 | 实测状态 |
|:--|:--|:--|
| **包版本** | **wishos-core 0.3.1** | ✅ 已发布（[repo](https://github.com/ZiMing-X/wishos-core) · [release](https://github.com/ZiMing-X/wishos-core/releases)） |
| **协议版本** | **WishOS Protocol v0.1**（[PROTOCOL.md](PROTOCOL.md)） | 规范性文件 |
| **DSH 宿主** | `>=0.2.1-rc.2 <0.2.2-0 \|\| >=0.2.2-rc.1 <0.3.0-0`（`engines.dsh`） | ✅ 实测 **dsh 0.2.1-rc.2**（Windows）；其余版本 ⚠️ 未实测 |
| Node.js | `>=22.19.0` | 承宿主要求 |
| Python（可选） | **≥3.14**（或 `pip install zstandard`） | 仅 `tools/_wishos_cost_report.py` 读会话转录时需要；不装则该技能写「未接线」 |
| 操作系统 | Windows / macOS / Linux | ✅ 预设按平台条件装载（Windows→pwsh，其余→bash）；Windows 实测 |
| 不适用 | 旧版 dsh（<0.2.1-rc.2）· 无 Python 且要用成本读数 · 需要 UI/自动执行器的场景 | — |

> 版本语义：`MAJOR.MINOR.PATCH`，**计划本体现冻结、改口径升版**；协议与实现版本独立（见 `PROTOCOL.md` §9）。

## 作用（它提供什么 / 不提供什么）

| ✅ 提供 | ❌ 不提供（需你填充） |
|:--|:--|
| **角色契约**（Wish/Router/Worker/Capture/Recall/Calibrate/Watchdog/Evolve/Enter）与它们之间的边界 | 领域能力（不会写代码/不会做业务），也不替代宿主自带工具 |
| **产物 schema**：Ticket / 卡片 / 校准 / 召回 / 节点（[`schemas/`](schemas/)，可机器校验） | 数据本身：愿望、项目、卡片库、图谱、校准的 `y` |
| **门禁判据**：Tier-0 四条、验收、可证伪、p/y 分离、3 次进化闸、只读巡检 | 自动化：**没有常驻调度/自动执行器**（`tool-schedule` 在型，但任务要你自己建） |
| **数据布局**：`<workspace>/wishos/` 单点约定 + 隔离预设 | 索引（FTS/向量）、外部系统集成、备份/迁移 |
| **自证工具**：公共自检 + schema 校验 + 成本读数（只读） | 英文技能正文（当前 8 技能为中文）、多用户/团队协作 |

**适合谁**：已经在用 DSH、想知道「愿望→验收→卡片→校准」怎么落成可审计流程的人；想按协议**部分采纳**（L1 最小闭环起步）的人。
**不适合谁**：想要「装完就提效」的一次性用户；需要 GUI 面板/自动执行的人；不接受中文技能正文的人。

## 采纳档位（框架支持部分采纳）

| 档 | 内容 | 适用 |
|:--|:--|:--|
| **L1 最小闭环** | `w-wish` + `w-router` + `w-capture` + `w-recall` | 先跑「愿望→验收→经验卡→下次先查」 |
| **L2 标准** | L1 + `w-calibrate` + `w-watchdog` | 还要「可校准 + 可观测」 |
| **L3 完整（本包默认）** | L2 + `w-evolve` + `w-enter` + 图谱/链/焦点栈 | 长期演化与可导航的第二大脑 |

> 裁剪方式：从 `skills/` 移除对应目录并同步 `skills.manifest.json`（协议 §6/§7）；完整环境校验工具在 `tools/dev/`。

## 它做什么（安装后生效的三件事）

1. **注册 agent preset（id `wishos`）**：persona（许愿驱动/引导/沉默优先）+ **Tier-0 四条**（不可逆外部动作要人确认 / 敏感数据不出本机 / 自学产物必带可证伪判据 / 不绕过宿主安全）+ 工具面（shell、fs、search、jobs、skill、goal、todo、schedule、ask-user、web、subagent/workflow、compaction）+ **隔离三件**（不挂 `agent-instructions`、`includeDefaultRoots:false`、不动其他预设）。
2. **技能根指向包内**：`customSkillDirs` 用官方 `createRequire(baseUrl)` idiom 解析本包 `skills/`，8 个技能随包分发，不写用户全局技能目录。
3. **注册只读自检工具** `wishos_core_health`：核对预设是否在名册且无 `broken`、技能根是否解析到、8 个 `SKILL.md` 是否齐全。

| 技能 | 作用 |
|:--|:--|
| `w-wish` | 愿望入口：把一句话编译成可执行 Ticket（目标/验收/预算/风险/上下文） |
| `w-router` | 派发纪律：只编译与派发、Worker 隔离、只上报「需要人」的事、大结果落盘只回摘要 |
| `w-recall` | 第二大脑召回：卡片 → 链 → 愿望 → 产出；唯一写是命中记账 |
| `w-capture` | 写卡：结论卡 / 经验卡（含护栏），可证伪门禁；evidence 只引路径 |
| `w-calibrate` | p/y 校准：p 事前、y 事后、Brier/ECE；y 必须来自体系外 |
| `w-watchdog` | 只读巡检：去重/陈旧/待校准/回退率/注意力/产出断链/成本读数 |
| `w-evolve` | 能力提取：同一模式复用 ≥3 次才允许新增技能/工具（提案交人批） |
| `w-enter` | 节点定位：把「进入 X」解析为图谱节点并注入 1 跳邻居 |

## 安装

```sh
# 从 GitHub 安装（当前未发 npm）
dsh plugin --profile <profile> add github:ZiMing-X/wishos-core
```

- 本地目录安装同样可行：插件管理器的 `install_bundle` 传本包绝对路径（HMR 生效，无需重启）。
- 装完可在 **Plugins** 页看到本包，并在 agent preset 名册里看到 `wishos`；把会话 preset 切到 **WishOS** 即生效。
- ⚠️ **同 id 冲突**：preset id 固定 `wishos`；若你的 profile 已有同 id 预设，先移除或改名，否则名册会出现两条同 id 记录。
- **卸载**：插件管理器移除本包（`remove_bundle`）—— preset 与工具随之注销。

## 数据目录（唯一约定 · 插件不创建）

**数据根 = 会话工作目录下的 `wishos/`**（persona 写死这条约定，技能里的相对路径都按它解析）：

```text
<workspace>/wishos/
├── brain/{cards,tickets,nodes,chains,recall,calibration,attention}/
├── outputs/
└── _tmp/
```

- `brain/cards/…` 等路径**相对数据根**，不相对会话工作目录 → 不会把 `brain/` 丢进你的项目根。
- 目录**首次使用时按需创建**（插件本身不写盘）；换工作区 = 换第二大脑（每个工作区一份独立数据）。

## 自检与工具（只读）

```sh
python tools/_wishos_selfcheck.py --root <workspace>/wishos   # 包完整性 + 数据面
python tools/_wishos_validate.py  --root <workspace>/wishos   # 按 schemas/ 校验 5 类产物
python tools/_wishos_cost_report.py --days 7                  # 成本读数（需 Python≥3.14）
```

| 工具 | 作用 |
|:--|:--|
| `tools/_wishos_selfcheck.py` | 包完整性（patch/8 技能/manifest）+ 数据面（卡片 frontmatter、票据 JSON、校准/召回 jsonl、目录齐否） |
| `tools/_wishos_validate.py` | JSON Schema 校验（ticket/card/calibration/recall/node），标准库实现 |
| `tools/_wishos_cost_report.py` | 只读 `~/.dsh/sessions` usage，按日/会话汇总 tokens·调用·缓存·重试；带 `--selfcheck` |

> **env**：`DSH_HOME`（默认 `~/.dsh`）· `DSH_PROFILE`（默认 `web`）· `WISHOS_ROOT`（默认 `$PWD/wishos`）。
> `tools/dev/` 是**作者完整环境**（22 技能 / v12-core / 台账 / 巡检）的判据，环境不全时会假红，**不要**当公共自检。

## 平台与依赖

- **Windows / macOS / Linux**：preset 按 `process.platform` 条件装载 `tool-pwsh` / `tool-bash`（都来自官方宿主安装）。
- **无 npm 运行时依赖**：21 个官方行全部由宿主提供；包本身只读文件系统、无网络请求。
- **语言**：8 个技能正文中文、persona 英文；英文 README 见 [README.en.md](README.en.md)。

## 边界与安全

- 只读宿主状态；唯一注册面 = preset 行 + 技能根 + 自检工具。
- **隔离是设计**：`includeDefaultRoots:false` ⇒ WishOS 会话看不到你 profile 的其他技能；要保留请同 id 覆盖 `customSkillDirs`。
- 不采集/不上传数据；敏感数据不出本机（Tier-0 第 2 条由 persona 约束，代码无网络请求）。
- 第三方代码风险自担；安装前可通读 `plugin.v3.js`（约 120 行）与 `cordis.patch.yml`（纯数据行）。

## 开发

```sh
node --check plugin.v3.js      # 插件语法
npm pack --dry-run             # 打包清单（dry-run，不发布）
python tools/_wishos_selfcheck.py --root <workspace>/wishos
```

改完技能后同步 `skills.manifest.json`（自检工具按它核对 8 个技能）。

## 许可

Apache-2.0，见 [LICENSE](LICENSE)。

> WishOS 是 `ZiMing-X` 的独立项目，与 DeepSeek 官方无隶属关系。
