---
name: w-watchdog
description: WishOS 每日巡检：去重、标陈旧、召回复用率、挑待校准断言、查回退率与注意力支出、成本读数；只报告不动生产件。触发词：体检、巡检、watchdog、看看系统怎么样、召回率、成本巡检。
version: v0.3.0
updated: 2026-11-06
tags: [wishos, kernel, watchdog, observability]
lifecycle: active
---

# w-watchdog · 巡检

## 一 · 每天做什么（只读）

1. 卡片：重复 / 失效 / **从未召回**（按 `brain/recall/*.jsonl` 里是否出现过该 card_id 判）
2. 待校准：有 p 无 y 的老断言（>30 天标红）
3. 愿望：近 7 天回退率、平均人工介入次数
4. 注意力：昨日唤起次数 vs 基线
5. 产出断链：报告引用的文件是否都在
6. 召回：覆盖率 = 被命中过的卡 / 全部卡；列 0 命中的前 5 张（旧卡无 `pattern_key` 单列）
7. **成本（C1 · 2026-11-06 新增）**：报告「成本」节，数字一律取
   `python tools/_wishos_cost_report.py`（可选；工作区自备） 的**当次输出**（只读 `~/.dsh/sessions`
   的 usage 事件，按日/按会话汇总 tokens · 调用 · 缓存 · 重试 · 标题）。
   - 建节命令：`python tools/_wishos_cost_report.py --days 7`（可选；工作区自备）
   - 🔴 引用时必须带 **「窗口 + 口径」** 两行（口径不同数字不可比）；`--caliber plan`
     只用于对齐 2026-11-06 规划基线 1,597,106,763，日常巡检用默认 `full`
   - 脚本退码非 0 ⇒ 写「成本：未接线（退码 N）」，**不臆造读数**、不手抄历史数字

> 数据源：`brain/recall/<date>.jsonl`（`w-recall` 写）。日志缺失时按"未接线"报告，不臆造读数。
> 成本数据源：`~/.dsh/sessions`（DSH 会话转录，只读）· 由 `_wishos_cost_report.py` 读取；
> 该脚本 `--selfcheck` 为本节读数的自证入口（退码 0 = 解析/窗口/回退口径全过）。

## 二 · 输出

`<workspace>/wishos/outputs\check-<YYYYMMDD>.md`，结构固定：
`读数（含「成本」节） / 异常 / 建议 / 需人决定`（**只建议，不自动改生产件**）

「成本」节至少含：窗口行、口径行、tokens/调用/均值/缓存命中、重试与标题数、会话 Top 数。

## 三 · 边界

- 不改生产件；要改 ⇒ 生成提案交人
- 不做自评闭环（不许自己给自己发"通过"）
- 成本读数只读：**不因读数删卡 / 砍会话 / 改预算**；判读交人（承 C1 门禁「只读、不动生产件」）
