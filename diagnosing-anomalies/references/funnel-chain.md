# 漏斗链路拆解

用于注册、下单、支付、审批、线索转化等多阶段链路。目标是先找断点，再对断点做维度下钻。

## 原理

将整体转化率拆成连续环节的乘积：

```text
R = 支付 / 访客
R = (浏览 / 访客) * (加购 / 浏览) * (下单 / 加购) * (支付 / 下单)
```

每个环节转化率都可视为乘法因子，因此核心计算通常复用 [`multiplicative-lmdi.md`](multiplicative-lmdi.md)。

## 怎么计算

1. 先明确链路节点和去重口径。
2. 计算基准期、当前期每个节点人数和环节转化率。
3. 把环节转化率作为 `factors` 调用乘法脚本。
4. 找贡献最大的环节，再按端、渠道、版本、人群、区域下钻。

## 输入示例

```json
{
  "factors": [
    {"name": "浏览/访客", "baseline": 0.8, "current": 0.76},
    {"name": "加购/浏览", "baseline": 0.3, "current": 0.25},
    {"name": "下单/加购", "baseline": 0.5, "current": 0.52},
    {"name": "支付/下单", "baseline": 0.9, "current": 0.88}
  ]
}
```

调用：

```bash
python diagnosing-anomalies/scripts/contribution.py multiply <input.json>
```

## 输出解读

优先输出“哪个环节解释了最多变化”，再给业务动作。例如：加购率下降解释了整体转化下降的主要部分，下一步应检查商品页、价格、库存、推荐和活动入口。
