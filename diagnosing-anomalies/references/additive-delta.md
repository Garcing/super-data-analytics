# 加法型拆解：Delta 法

用于 `Y = ΣXi` 或 `Y = Σ(ai * Xi)` 的指标，例如收入、订单数、DAU、工单数。目标是量化每个分项让总体变化了多少。

## 原理

```text
ΔY = Y1 - Y0
Vi = Xi1 - Xi0
Ci = Vi / ΔY
Ri = Vi / Y0
```

一般线性形式：

```text
Y = Σ(ai * Xi)
Vi = ai * (Xi1 - Xi0)
```

口径：

- `Vi`：贡献量，单位与指标一致。
- `Ci`：贡献率，解释总变化由谁贡献，可超过 100% 或为负。
- `Ri`：相对贡献，解释该分项让大盘较基准变化了多少。

## 脚本调用

```bash
python diagnosing-anomalies/scripts/contribution.py add <input.json>
```

## 输入 JSON

```json
{
  "baseline_total": 100,
  "current_total": 130,
  "items": [
    {"name": "自然流量", "baseline": 40, "current": 70},
    {"name": "广告投放", "baseline": 50, "current": 55},
    {"name": "社交裂变", "baseline": 10, "current": 5}
  ]
}
```

要求：

- `items` 应互斥且完整。
- 若价格、权重、汇率等系数也变化，不要强行按加法拆，应改用乘法或定基替代。

## 输出重点

```text
summary.delta：总体变化 ΔY
summary.relative_change：总体相对变化 ΔY / Y0
rows[].contribution_value：贡献量 Vi
rows[].contribution_share：贡献率 Ci
rows[].relative_contribution：相对贡献 Ri
checks.residual：分项贡献未解释的残差
```

如果 `checks.residual` 不为 0，先检查分项是否漏项、重复或不互斥。
