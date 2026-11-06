---
name: w-wish
description: WishOS 愿望入口。编译前先召回同类经验，再把一段自然语言愿望编译成可执行 Ticket（目标/验收/预算/风险/上下文），落 brain/tickets/ 后交给 w-router 派发。触发词：许愿、愿望、我想要、帮我做个、我想要一个、wish。
version: v0.2.0
updated: 2026-11-05
tags: [wishos, kernel, entrance]
lifecycle: active
---

# w-wish · 愿望入口

> WishOS 的唯一入口。用户**不填参数、不选技能**，只说一句愿望。

## 一 · 编译步骤

0. **召回**（默认动作，不阻断）：先按 `w-recall` 查同类卡片/经验卡（≤5 条），把命中的 `card_id` 和一句教训写进 Ticket 的 `context`；0 命中直接往下走，不为此追问人
1. 抽取：`intent`（要什么结果）/ `acceptance`（怎么算成了）/ `budget`（时间/步数/花费上限）/ `risk`（是否含不可逆动作）
2. 判 Tier-0：命中 T0-1（不可逆外部动作）⇒ 先 `ask_user_question` 确认，再往下
3. 生成 Ticket（`brain/tickets/<YYYYMMDD-HHMM>-<slug>.json`）：

```json
{
  "id": "T-...", "wish": "<原话>", "intent": "...", "acceptance": ["..."],
  "context": {"cards": ["c-..."], "lessons": ["<一句教训；无则空>"]},
  "plan": [{"id": "s1", "task": "...", "acceptance": ["..."], "depends_on": []}],
  "budget": {"minutes": 0, "steps": 0}, "risk": {"tier0": []},
  "status": "idle", "created_at": "...", "worker": null
}
```

   - `context`：召回结果；空也留字段（`{"cards": [], "lessons": []}`）
   - `plan`：**单目标可省**；多目标/有依赖才列，一个子任务一个 Worker（交给 `w-router`）

4. 交 `w-router`：由它决定派几个 Worker、用哪些技能/工具
5. 收口：结果 + 卡片（`w-capture`）一次写完——成功写结论卡；失败/回退/踩坑写**经验卡**（含护栏）

## 二 · 反模式

- 不要向用户要参数清单（"懒人三件套"是反向需求）
- 不要在没有 acceptance 的情况下开工：**没有判据的愿望不接**
- 不要跳过 Tier-0 检查
- 不要跳过召回直接开工：同坑要复发时，先看 `context.lessons` 里有没有护栏
- 不要把失败写成"下次注意"：写不出可检索的护栏，说明这次还没学到东西
