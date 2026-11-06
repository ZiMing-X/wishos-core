---
name: w-capture
description: 把一次愿望的结果写成知识卡：成功写结论卡，失败/踩坑写经验卡（含护栏），入库前做可证伪校验（T0-3）。触发词：记下来、存卡、捕获、沉淀、capture、经验、教训。
version: v0.3.0
updated: 2026-11-06
tags: [wishos, kernel, memory, card]
lifecycle: active
---

# w-capture · 写卡

## 一 · 两种卡（同一目录约定）

### 1) 结论卡（成功时写）

```markdown
---
id: c-YYYYMMDD-<slug>
statement: <一句话结论>
evidence: [<文件/命令/读数>]
confidence: <0.0-1.0>
falsifiable: <什么情况下这条算错>
source: <本次愿望 ticket_id 或外部来源>
status: draft | verified | retired
pattern_key: <动词-对象，如 readme-sync；旧卡可空>
chain_id: <可选，推理链 ID>
updated: <系统墙钟>
---

<正文：为什么、怎么来的、边界>
```

### 2) 经验卡（失败/回退/踩坑必须写）

```markdown
---
id: c-YYYYMMDD-<slug>
type: experience
statement: <一句话：这次学到什么>
trigger: <什么情境下会再遇到>
action: <下次先做什么>
guardrail: <失败时：先避免什么；成功时可为空>
outcome: success | failure | partial
pattern_key: <动词-对象，与同类卡同一个 key>
evidence: [...]
confidence: <0.0-1.0>
falsifiable: <什么情况下这条经验算错>
source: <ticket_id>
status: draft | verified | retired
updated: <系统墙钟>
---
```

## 二 · 收卡门禁（唯一硬校验，来自 T0-3）

- 两种卡同一门禁：`statement` / `falsifiable` / `evidence` 任一为空 ⇒ **拒收**
- `confidence` 必须是决策当时的值，不许事后补
- 失败/回退的愿望 ⇒ 默认写经验卡；`guardrail` 写不出具体的，说明这次还没学到东西，回退去补
- 同一结论重复卡 ⇒ 合并到原卡并记 `merged_from`；同一模式复用同一个 `pattern_key`

## 三 · 落点

- 结论卡：`<workspace>/wishos/brain/cards\<类型>\<id>.md`（类型：context / pattern / decision / solution）
- 经验卡：`<workspace>/wishos/brain/cards\pattern\<id>.md`（`type: experience`）
- 旧卡无 `pattern_key` 不追补；新卡必带——`w-evolve` 的"≥3 次"判据靠它算

## 四 · evidence 写法（C3 · 2026-11-06 新增）

- `evidence` **只写路径 / 命令 / 读数**，不贴大段内容；大结果先落 `<workspace>/wishos/outputs\`，卡里只引路径
- 单条 evidence 建议 **≤200 字符**；多件证据用路径列表（对应 Ticket 的 `result_artifacts`）
- 卡正文同理：只写「为什么 / 怎么来的 / 边界」，**不复述产物全文**（复述会随卡一起被后续召回注入）
- 卡片里的"读数"是**当次实测值 + 取数命令**，不是历史抄件
