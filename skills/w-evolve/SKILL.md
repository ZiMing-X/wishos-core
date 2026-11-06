---
name: w-evolve
description: 能力提取：同一模式复用 ≥3 次才允许长出新技能/新工具；产出待批提案。触发词：进化、长能力、新模式、evolve。
version: v0.1.0
updated: 2026-11-02
tags: [wishos, kernel, evolution]
lifecycle: active
---

# w-evolve · 能力提取

## 一 · 长能力的门坎（唯一判据）

同一模式（`pattern_key`）在 `brain/cards/` 中出现 **≥3 次**，且：
- 每次都有 evidence
- 复用带来可测收益（时间/步骤/错误率下降其一）

⇒ 才允许提交"新技能/新工具"提案。

## 二 · 提案格式

```markdown
## 提案 E-<YYYYMMDD>-<slug>
- 模式：<pattern_key>（出现 N 次：卡1/卡2/卡3）
- 收益读数：<前后对比>
- 拟新增：<技能名 w-* 或工具路径>
- 风险：<Tier-0 是否涉及>
- 待批：是/否（人）
```

## 三 · 反模式

- 一次就长技能 ⇒ 拒
- 无外部证据 ⇒ 拒
- 自动安装第三方插件 ⇒ 拒（须人批）
