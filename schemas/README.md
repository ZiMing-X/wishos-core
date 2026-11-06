# schemas/ — WishOS Protocol v0.1 产物 schema

规范性文件（JSON Schema draft 2020-12）。实现方 MAY 附加字段；**不得缺失** `required` 字段。

| 文件 | 产物 | 落点 |
|:--|:--|:--|
| `ticket.schema.json` | Ticket | `brain/tickets/<YYYYMMDD-HHMM>-<slug>.json` |
| `card.schema.json` | 结论卡 / 经验卡（`oneOf`） | `brain/cards/<类型>/c-<YYYYMMDD>-<slug>.md`（frontmatter） |
| `calibration.schema.json` | 校准对（一行） | `brain/calibration/pairs.jsonl` |
| `recall.schema.json` | 召回记账（一行） | `brain/recall/<YYYYMMDD>.jsonl` |
| `node.schema.json` | 图谱节点 | `brain/nodes/<type>/<id>.md`（frontmatter） |

## 校验

```sh
python tools/_wishos_validate.py --root <数据根>        # 逐文件按 schema 校验，rc 0/2
python tools/_wishos_validate.py --root <数据根> --json
```

- 校验器是**标准库实现**（不引入 jsonschema 依赖），支持 `type / required / enum / const / pattern / minLength / minItems / minimum / maximum / items / properties / oneOf / additionalProperties`。
- Markdown 产物（卡/节点）校验其 **frontmatter**；JSONL 产物逐行校验。
- schema 只约束**结构**，内容判据（可证伪、证据存在等）由技能/巡检负责。

## 版本

随实现发布；协议升版时 schema 同步升版（`$id` 固定，字段增删按 §9 的 MAJOR/MINOR 规则）。
