---
name: w-calibrate
description: p/y 校准：决策当场声明 p，结局出现后补 y；算 Brier/ECE；硬约束 p/y 物理分离、防自评闭环。触发词：校准、置信度、预测、Brier、calibrate。
version: v0.1.0
updated: 2026-11-02
tags: [wishos, kernel, calibration]
lifecycle: active
---

# w-calibrate · 校准

## 一 · 硬约束（保留校准协议 H-1~H-5 语义）

| 编号 | 约束 |
|:--|:--|
| H-1 | p ∈ `probability_block`（事前）；y ∈ `calibration_pair`（事后）；不得互相引用 |
| H-2 | p 的写入时点必须早于 y |
| H-3 | 单向：校准对 → 校准器 → Brier/ECE → 更新 p 的权重，禁止反向 |
| H-4 | `interval = null` 不得阻断流程，标 `RAW_PLACEHOLDER` |
| H-5 | 别名只读（`confidence`/`probability` 不许写） |

## 二 · y 的铁律

**y 必须来自体系外**：禁用自评、同模型自评、交叉模型一致性。
合法来源：实际结局（系统读数 / 外部事实 / 人工确认）。

## 三 · 落点

`<workspace>/wishos/brain/calibration\pairs.jsonl`（一行一对）· `brier.json`（周算）
