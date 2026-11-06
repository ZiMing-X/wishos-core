# wishos-core

> **WishOS Core** —— 给 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（`dsh`）用的
> **许愿式第二大脑**预设插件：装一次，得到一个带人格、四条硬约束、隔离工具面与 8 个 `w-*` 技能的 agent preset。

[![npm](https://img.shields.io/npm/v/wishos-core)](https://www.npmjs.com/package/wishos-core)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

## 这是什么（框架定位）

**WishOS 是一个工作法框架，`wishos-core` 是它的参考实现。** 协议见 [`PROTOCOL.md`](PROTOCOL.md)，产物 schema 见 [`schemas/`](schemas/)。

| 框架自带 | 需要你填充 |
|:--|:--|
| 角色契约（Wish/Router/Worker/Capture/Recall/Calibrate/Watchdog/Evolve/Enter） | 你的真实愿望、项目与知识内容 |
| 产物 schema（Ticket/卡片/校准/召回/节点，见 `schemas/`） | 数据本身（卡片库、图谱、校准的 y） |
| 门禁判据（Tier-0、验收、可证伪、p/y 分离、进化闸、只读巡检） | 外部系统集成、备份、调度（`tool-schedule` 在型但无常驻任务） |
| 数据布局约定（`<workspace>/wishos/`）＋ 隔离预设 | 索引（FTS/向量）、英文内容、组织级规范 |

**采纳档位**（框架支持部分采纳，详见 `PROTOCOL.md` §7）：

| 档 | 内容 |
|:--|:--|
| **L1 最小闭环** | `w-wish` + `w-router` + `w-capture` + `w-recall` |
| **L2 标准** | L1 + `w-calibrate` + `w-watchdog` |
| **L3 完整（本包默认）** | L2 + `w-evolve` + `w-enter` + 图谱/链/焦点栈 |

## 版本

| 项 | 当前值 |
|:--|:--|
| **包版本** | **0.3.0**（2026-11-06 · 公开发布候选，未发布） |
| **协议版本** | **WishOS Protocol v0.1**（见 `PROTOCOL.md`）
| **实测宿主** | **dsh 0.2.1-rc.2**（Windows） |
| 兼容声明 | `engines.dsh`: `>=0.2.1-rc.2 <0.2.2-0 \|\| >=0.2.2-rc.1 <0.3.0-0`（其余版本未实测） |
| 体系版本 | WishOS v0.1（8 个 `w-*` 技能 v0.1.0~v0.3.0） |

## 它做什么

安装后，包里三样东西同时生效：

1. **注册一个 agent preset（id `wishos`）**：纯数据行，内容 =
   - **persona**：WishOS 身份（许愿驱动、引导模式、沉默优先）；
   - **四条 Tier-0 硬事实**：不可逆外部动作要人确认 / 敏感数据不出本机 / 自学产物必带可证伪判据 / 不绕过宿主安全；
   - **工具面**：shell、文件、搜索、jobs、goal、todo、schedule、ask-user、web、subagent/workflow、compaction 等；
   - **隔离三件**：不挂 `agent-instructions`、`includeDefaultRoots:false`、不动其他预设。
2. **把技能根指向包内**：`customSkillDirs` 用官方 `createRequire(baseUrl)` idiom 解析**本包** `skills/`，
   8 个 `w-*` 随包分发，不写用户全局技能目录。
3. **注册只读自检工具** `wishos_core_health`：核对预设是否在名册且无 `broken`、技能根是否解析到、8 个 SKILL.md 是否齐全。

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
dsh plugin --profile <profile> add wishos-core
```

- 本地目录安装同样可行：插件管理器的 `install_bundle` 传本包绝对路径（HMR 生效，无需重启）。
- 装完可在 **Plugins** 页看到本包，并在 agent preset 名册里看到 `wishos`。
- 让任意会话使用它：把该会话的 agent preset 切到 **WishOS**。
- ⚠️ **同 id 冲突**：本包注册的 preset id 固定为 `wishos`。如果你的 profile 里已有同 id 的预设（例如手写的 `preset-wishos` 行），请先移除或改名，否则名册会出现两条同 id 记录。

## 数据目录（唯一约定 · 插件不创建）

**数据根 = 会话工作目录下的 `wishos/`**（preset 的 persona 里也写死了这条约定，所有技能按它解析相对路径）：

```text
<workspace>/wishos/
├── brain/{cards,tickets,nodes,chains,recall,calibration,attention}/
├── outputs/
└── _tmp/
```

- 技能里的 `brain/cards/…`、`outputs/…` 一律**相对数据根**，不相对会话工作目录 → 不会把 `brain/` 丢进你的项目根。
- 目录在**首次使用时按需创建**（插件本身不写盘），也可先 `mkdir -p <workspace>/wishos/brain/<子目录>`。
- 换工作区 = 换第二大脑（每个工作区一份独立数据）。

## 自检

装好后让 agent 调用 `wishos_core_health`（只读、不传参）。判定项：

1. preset `wishos` 在名册且无 `broken`；
2. `!!js` 探针解析出的技能根存在，且包含 8 个期望目录；
3. 包内 8 个 `SKILL.md` 均在盘。

## 自带工具（自证 · `tools/`）

包里自带**两个公共工具**（只读，不依赖作者环境），另附作者侧完整环境工具（`tools/dev/`，公共用户不要用来判定）：

| 工具 | 作用 | 用法 |
|:--|:--|:--|
| `tools/_wishos_selfcheck.py` | **公共自检**：包完整性（patch/8 技能/manifest）+ 数据面（卡片 frontmatter、票据 JSON、校准/召回 jsonl 合法性） | `python tools/_wishos_selfcheck.py` |
| `tools/_wishos_cost_report.py` | **成本读数**：只读 `~/.dsh/sessions` usage，按日/会话汇总 tokens·调用·缓存·重试，带 `--selfcheck` | `python tools/_wishos_cost_report.py --days 7` |
| `tools/_wishos_validate.py` | **协议校验**：按 `schemas/` 校验 Ticket / 卡片 / 校准 / 召回 / 节点 | `python tools/_wishos_validate.py --root <数据根>` |

> `tools/dev/` 里的 `gate / verify / l2 / l3` 是**作者完整环境**（22 技能 / v12-core / 台账 / 巡检报告）的判据；
> 环境不全时会系统性假红，**不要**拿它们当公共自检。见 `tools/dev/README.md`。

**路径通过环境变量解析**（默认值 = 本机通用约定）：

```sh
# 可选；不设时：DSH_HOME=~/.dsh · DSH_PROFILE=web · WISHOS_ROOT=$PWD/wishos
export DSH_HOME="$HOME/.dsh"
export DSH_PROFILE=web
export WISHOS_ROOT="$PWD/wishos"          # 数据根（brain/、outputs/、_tmp/ 所在）
```

> Python ≥3.14（或 `pip install zstandard`）用于读 DSH 会话转录；其余工具仅用标准库。
> 两个公共工具**只读**；`tools/dev/` 里之外无任何写盘动作（`verify --update-baseline` 只写 `WISHOS_ROOT/baseline/`）。

## 平台与依赖

- **Windows / macOS / Linux 均可**：preset 按 `process.platform` 条件装载 —— Windows 启 `tool-pwsh`，其余平台启 `tool-bash`（两者都来自官方宿主安装，无额外依赖）。
- **无 npm 运行时依赖**：21 个官方行全部由宿主安装提供；插件本身只读文件系统。
- **可选**：`w-watchdog` 的成本读数可直接用包内 `tools/_wishos_cost_report.py`；不装 Python 或不用时技能会写「成本：未接线」，不臆造读数。
- 语言：8 个技能正文为中文；persona 为英文。

## 兼容性

- `engines.dsh`：`>=0.2.1-rc.2 <0.2.2-0 || >=0.2.2-rc.1 <0.3.0-0`（在 `dsh 0.2.1-rc.2` 实测）
- 预发布版本需显式分支（承 `awesome-dsh-plugin` 的 peer/engines 约定）
- **卸载**：`plugin_manager` 的 `remove_bundle` / 插件管理页移除 —— preset 与工具随之注销

## 边界与安全

- 本包**只读宿主状态**；唯一注册面是 preset 行、技能根与自检工具。
- **隔离是设计**：`includeDefaultRoots:false` ⇒ WishOS 预设会话**看不到你 profile 里的其他技能**（避免不同体系的规则互相打架）。
  若要在 WishOS 会话里保留你自己的技能：在 profile patch 中用**同 id** 覆盖 `skill-filesystem` 的 `customSkillDirs`
  （匹配覆盖会整块替换 config，需把本包的包内技能根一并抄上）。
- 不采集、不上传任何数据；**敏感数据不出本机**（Tier-0 第 2 条由 persona 约束，代码不做网络请求）。
- 第三方代码风险自担：安装前可通读本包（`plugin.v3.js` 约 120 行、`cordis.patch.yml` 为纯数据行）。

## 开发

```sh
node --check plugin.v3.js      # 插件语法
npm pack --dry-run             # 打包清单（dry-run，不发布）
```

改完技能后请同步 `skills.manifest.json`（自检工具按它核对包内 8 个技能）。

## 许可

Apache-2.0，见 [LICENSE](LICENSE)。

> WishOS 是 `ZiMing-X` 的独立项目，与 DeepSeek 官方无隶属关系。
