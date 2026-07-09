# 比率型拆解：组间组内拆解

用于 `Y = P / Q` 的指标，例如转化率、支付成功率、投诉率、退款率。重点是区分“分组自身表现变化”和“分组结构变化”。

## 原理

把总体拆成互斥分组：

```text
Yi0 = Pi0 / Qi0
Yi1 = Pi1 / Qi1
wi0 = Qi0 / Q0
wi1 = Qi1 / Q1
Y0 = Σ(wi0 * Yi0)
Y1 = Σ(wi1 * Yi1)
ΔY = Y1 - Y0
```

默认使用基期权重拆解：

```text
组内贡献 Wi = wi0 * (Yi1 - Yi0)
结构贡献 Bi = (wi1 - wi0) * (Yi0 - Y0)
交叉贡献 Ii = (wi1 - wi0) * (Yi1 - Yi0)
总贡献 Vi = Wi + Bi + Ii
Ci = Vi / ΔY
Ri = Vi / Y0
```

## 脚本调用

```bash
python diagnosing-anomalies/scripts/contribution.py ratio <input.json>
```

## 输入 JSON

```json
{
  "groups": [
    {
      "name": "男性",
      "baseline_numerator": 800,
      "baseline_denominator": 3000,
      "current_numerator": 950,
      "current_denominator": 3500
    },
    {
      "name": "女性",
      "baseline_numerator": 300,
      "baseline_denominator": 2000,
      "current_numerator": 400,
      "current_denominator": 2500
    }
  ]
}
```

要求：

- 分组必须互斥且分母完整。
- 分母必须大于 0。
- 不要只用“分组率值变化 / 总体率值变化”计算贡献，容易误判辛普森悖论。

## 输出重点

```text
rows[].baseline_rate / current_rate：分组率值
rows[].baseline_weight / current_weight：分组分母占比
rows[].within_contribution：组内表现贡献
rows[].mix_contribution：结构贡献
rows[].interaction_contribution：交叉贡献
rows[].contribution_value：分组总贡献
checks.residual：未解释残差
```

解读：

- 组内贡献为正，表示分组自身率值改善。
- 结构贡献为负，常表示低于大盘的分组占比上升，或高于大盘的分组占比下降。
- 若所有分组都变好但总体变差，优先解释结构变化。
