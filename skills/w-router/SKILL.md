---
name: w-router
description: WishOS 路由层纪律：派发前三问、按 plan 拆子任务、Worker 交回三行；只派发不执行；只把「需要人」的事上报；沉默优先。触发词：路由、派发、router、谁来干、拆任务。
version: v0.3.0
updated: 2026-11-06
tags: [wishos, kernel, router, attention]
lifecycle: active
---

# w-router · 路由与注意力

## 一 · 固定分工

| 层 | 职责 | 禁止 |
|:--|:--|:--|
| Router（本技能所在层） | 编译 Ticket、派发 Worker、汇总 | **不得自己执行具体任务** |
| Worker（subagent / 独立会话） | 单任务执行、产出交付物 | 不互相通信；上下文隔离 |

## 二 · Ticket 状态机（唯一判定：它在等什么）

`person`（等人）→ `working` → `idle` → `done`；异常态 `blocked` / `failed`。
**只有 `person` / `blocked` / `failed` / `done` 允许打扰人**；`working` / `idle` 一律不出现。

## 三 · 注意力预算

- 每次唤起人 = 一次记账（记 `brain/attention/<date>.jsonl`：时间、事由、是否必需）
- 同一愿望对同一人的唤起 **≤2 次**；超过则挂起并说明
- 沉默是默认值：**没有需要人决定的事，就不说话**

## 四 · 派发

- **派发前三问**（答案写进 `ticket.route.reason`，不另设门禁）：
  1) 在能力/工具边界内吗？
  2) 对结果多确信（p=0.0~1.0）？
  3) 策略：直接做 / 借经验（召回命中的 card_id）/ 问人？
- **单目标**：一个 Ticket 一个 Worker；重试用新 Assignment
- **多目标/有依赖**：按 `ticket.plan` 一个子任务派一个 Worker，子任务的 `acceptance` 原样交给 Worker
- Worker 用 `subagent` / `subagent_fork`，或开独立会话；`cwd` 指到 `<workspace>/wishos/`
- 高风险（T0-1）愿望：派发前先问人
- 拆不清 = 还没拆清：补不出子任务 `acceptance` 就先问人，不硬派

## 五 · Worker 交回契约（三行，不多写）

1. **结果**：做了什么、落点在哪
2. **判据对照**：逐条对 `acceptance`，过 / 没过
3. **靠什么 / 错在哪**：命中的 card_id（无则写"无"）；失败再补一句"护栏候选"

### 大结果落盘（C3 · 2026-11-06 新增）

结果 **>8KB 或 >200 行**（全量日志 / 大 JSON / 长表格 / 工具大段回显）⇒ **先落路径，只回摘要**：

- 落点：`<workspace>/wishos/outputs\<ticket_id>\<name>`；Ticket 增 `result_artifacts: [<path>...]`（有落盘才写）
- 交回三行的「结果」行写：**摘要 ≤20 行 + 路径**；摘要须能独立判读（带关键读数），禁止只写"详见文件"
- 🔴 不要把全文贴进上下文：上下文里每多 1 万字符，后续**每一次**调用都要重发（成本按轮次复利）
- 阈值是引导值（建议口径），不阻断交付；确实需要全文时说明理由

Router 汇总后交 `w-capture`：成功写结论卡；失败/踩坑写经验卡。Worker 不直接写卡。

## 六 · 反模式

- 不要用"看过了"当验收：每条 acceptance 要有可复跑的读数
- 不要把失败藏进"已完成"：失败要进经验卡，那是下一次的护栏
