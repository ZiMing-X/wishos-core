---
name: w-recall
description: 第二大脑召回。先查本地卡片库（brain/cards + FTS），再沿推理链跳转（卡片→链→愿望→产出）；只读卡片，唯一写是 brain/recall/ 命中记账；不出本机。触发词：找一下、以前、继续上次、查知识库、检索、recall。
version: v0.2.0
updated: 2026-11-05
tags: [wishos, kernel, memory, recall]
lifecycle: active
---

# w-recall · 召回

## 一 · 查询顺序（便宜的先查）

1. `brain/cards/` 文件名与 frontmatter 关键词
2. FTS（SQLite）全文本命中
3. 链式跳转：卡片 `chain_id` → `brain/chains/` → `wish_id` → `brain/tickets/`
4. 产出：`outputs/`

> FTS 未建时（W4 前）跳过第 2 步，用 1/3/4 即可——**别假装有库**。

## 二 · 链式召回的硬要求

每个对象都必须带 ID，注入时**带下一跳 ID**：
```
卡(card_id) → 链(chain_id) → 愿望(ticket_id) → 产出(artifact_path)
```

## 三 · Inline / Spill

- 近期会用到的整段：内联
- 其余：只给引用（路径 + 一句摘要），需要时再读
- 🔴 不把整库塞进上下文；召回结果默认 ≤5 条

## 四 · 边界

不修改卡片/链/票据内容（唯一的写是 `brain/recall/` 记账）；**不出外部 API**（T0-2）。

## 五 · 命中记账（唯一的写）

每次召回（含 0 命中）追加一行到 `<workspace>/wishos/brain/recall\<YYYYMMDD>.jsonl`：

```json
{"ts": "...", "query": "<原话/主题>", "hits": ["c-..."], "via": "w-wish|manual"}
```

- `hits` 记 card_id；0 命中记 `[]`——**空命中也是数据**，`w-watchdog` 用它算召回覆盖率
- 只记"查到了什么"；"用没用"由 `w-router` 交回的"靠什么知识"三行体现，最终进卡片正文
- 日志目录不存在时创建；写日志失败不中断召回
