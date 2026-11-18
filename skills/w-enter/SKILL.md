---
name: w-enter
description: 节点定位器。把「进入 X」解析为图谱节点并跳转：项目节点 / 事件节点 / 思维链节点（claim·evidence·inference·conclusion）/ 卡片 / Ticket / 产出。设定 focus、注入 1 跳邻居与链位、支持「回去」「看邻居」；v0.2 增降级/历史状态回显与 `default_entry` 重定向（协议 §四）。触发词：进入、进入项目、跳到、定位、回到、回去、看邻居、enter。
version: v0.2.0
updated: 2026-11-18
tags: [wishos, kernel, enter, graph]
lifecycle: active
---

# w-enter · 节点定位器

> 🔴 「进入项目 <名>」**不是打开目录**，是跳到知识图谱里的那个节点。
> 目录只是节点属性；焦点才是上下文。

## 一 · 统一节点（一切皆节点）

| type | 含义 | 例子 |
|:--|:--|:--|
| `project` | 子图根 | `demo` |
| `event` | 事件节点（带时间，可被锁定） | `2026-11-02 08:02 打包落盘` |
| `claim` / `evidence` / `inference` / `conclusion` | 思维链节点 | 「架构决策＝第二大脑」 |
| `card` | 知识卡 | `c-20261102-…` |
| `ticket` | 愿望 Ticket | `T-20261102-…` |
| `artifact` | 产出件 | `outputs/…md` |
| `session` | 会话锚点 | `session:<id>` |

节点文件：`brain/nodes/<type>/<id>.md`，frontmatter 必须含 `id / type / title / ts / edges`。
边：`parent / children / chain_prev / chain_next / supports / contradicts / derived_from / attached`。

## 二 · 进入算法（确定性 · 可复跑）

1. 解析目标（🔴 v0.2 P1 顺序：`node_id` 精确 ＞ `status/redirect` ＞ `title`/`alias` 精确 ＞ `tags` 关键词模糊）
   - 直接 `进入 <node_id>`：**永远有效**（含 `retired`）——定位标准底线，不因状态改 id
   - 命中 `demoted` / `historical`：**必须回显状态**：`已定位：<title>（<type> · 已降级/历史 · 原因 · 入口已改为 Z）`，并**问一次**是否跟随 `default_entry`
   - 按 `title`/`alias`/`tags` 模糊进入：**优先走 `default_entry`**；无则停在原节点
   - 解析链 `demoted → default_entry` 允许链式，**递归上限 3 跳**（防环；第 4 跳停并回显「链过长，已停在第 3 跳」）
2. 歧义：候选 >1 ⇒ 用 `ask_user_question` 列前 5（**禁止猜**）；候选 =0 ⇒ 提议新建节点，**不擅自造**
   🔴 **禁止静默跳转**：任何重定向必须在回显里写明「入口已改为 Z」，不得无提示改写入口
3. 定焦点：写 `brain/focus.json`（`focus` + `stack` + `ts`）
4. 注入：节点本体 ＋ **1 跳**邻居（父/子/链前后/attached）＋ 链位（第 n / 共 m）
5. 回一句：`已定位：<title>（<type> · <ts> · 链 n/m · 状态 active|demoted|historical|retired）`
6. 之后新知识/愿望/产出自动 `attached` 到 focus

## 三 · 快捷语义

| 你说 | 行为 |
|:--|:--|
| `进入项目 <名>` | 进入 project 节点；默认指向其**最新未闭合 event**，无则根 |
| `进入 <事件描述>` | 进入 event 节点 |
| `进入思维链 <主题>` | 进入该链 conclusion 节点，可 `上一步/下一步` |
| `回去` | focus 栈 pop |
| `看邻居` | 1 跳展开 |
| `看全链` | 拉整条 chain（走 w-recall） |

## 四 · 与旧的「项目锁定」做法的差异

| 旧 | 新 |
|:--|:--|
| 绑定项目根 + 写锁 | **绑定节点 + 跳转**（目录只是属性） |
| 一个会话一个项目 | 一个会话一条**焦点路径**（可回退） |
| 进入后再手动找资料 | 进入即注入 1 跳上下文 |

## 五 · 边界

- 不改节点内容（只读定位）；改动走 `w-capture` / 显式指令
- 不越权：候选歧义必须问人，不许"猜一个最像的"
- 数据只在本机（T0-2）
- `retired` 节点按 `id` 仍可进入（默认视图不显示 ≠ 不可达）；状态回显必须带原因与入口变更，**不得静默跳转**
- 节点状态语义（`active|demoted|historical|retired`）与迁移由 gate 校验（schema 只管形状）
