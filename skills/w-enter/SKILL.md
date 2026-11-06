---
name: w-enter
description: 节点定位器。把「进入 X」解析为图谱节点并跳转：项目节点 / 事件节点 / 思维链节点（claim·evidence·inference·conclusion）/ 卡片 / Ticket / 产出。设定 focus、注入 1 跳邻居与链位、支持「回去」「看邻居」。触发词：进入、进入项目、跳到、定位、回到、回去、看邻居、enter。
version: v0.1.0
updated: 2026-11-02
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

1. 解析目标：`node_id` 精确 ＞ `title`/`alias` 精确 ＞ `tags` 关键词模糊
2. 歧义：候选 >1 ⇒ 用 `ask_user_question` 列前 5（**禁止猜**）；候选 =0 ⇒ 提议新建节点，**不擅自造**
3. 定焦点：写 `brain/focus.json`（`focus` + `stack` + `ts`）
4. 注入：节点本体 ＋ **1 跳**邻居（父/子/链前后/attached）＋ 链位（第 n / 共 m）
5. 回一句：`已定位：<title>（<type> · <ts> · 链 n/m）`
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
