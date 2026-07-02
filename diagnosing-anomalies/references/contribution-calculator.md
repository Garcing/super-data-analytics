# 贡献度计算器

使用 `scripts/contribution.py` 计算加法型、乘法型和比率型贡献度。脚本输出稳定 JSON，便于继续生成表格、图表或报告。

## 通用命令

```bash
python diagnosing-anomalies/scripts/contribution.py add <input.json>
python diagnosing-anomalies/scripts/contribution.py multiply <input.json>
python diagnosing-anomalies/scripts/contribution.py ratio <input.json>
```

## 输出字段

```text
ok：是否成功
method：计算方法
summary.baseline_total：基准期总体值
summary.current_total：当前期总体值
summary.delta：总体变化量 ΔY
summary.relative_change：总体相对变化 ΔY / Y0
rows[].contribution_value：贡献量 Vi
rows[].contribution_share：贡献率 Ci = Vi / ΔY
rows[].relative_contribution：相对贡献 Ri = Vi / Y0
rows[].direction：同向解释 / 反向抵消 / 无明显贡献
checks.sum_contribution：贡献量加总
checks.residual：残差
checks.warnings：口径或加总风险提示
```

`contribution_share` 和 `relative_contribution` 不可混用。前者回答“解释了总变化的多少”，后者回答“让大盘相对基准变化了多少”。

## 加法型输入

适用于 `Y = Σ Xi`。

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
- 若 `checks.residual` 不为 0，说明分项加总无法解释总体变化。

## 乘法型输入

适用于 `Y = Π Xi`。脚本会自动用所有因子相乘得到总体值。

```json
{
  "factors": [
    {"name": "UV", "baseline": 1000, "current": 900},
    {"name": "CVR", "baseline": 0.1, "current": 0.12},
    {"name": "AOV", "baseline": 100, "current": 125}
  ]
}
```

要求：

- 所有 `baseline` 和 `current` 必须大于 0。
- 零值或负值不能直接做 log 拆解，需要换方法或先做业务认可的平滑处理。

额外字段：

```text
rows[].factor_ratio：因子当前值 / 基准值
rows[].log_delta：因子对数变化
rows[].log_contribution_share：因子解释总体对数变化的比例
```

## 比率型输入

适用于 `Y = P / Q`，例如转化率、支付成功率、投诉率。

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

额外字段：

```text
rows[].baseline_rate：分组基准率
rows[].current_rate：分组当前率
rows[].baseline_weight：分组基准分母占比
rows[].current_weight：分组当前分母占比
rows[].within_contribution：组内贡献
rows[].mix_contribution：结构贡献
rows[].interaction_contribution：交叉贡献
```

解释：

- `within_contribution` 为正，表示分组自身率值改善拉动总体。
- `mix_contribution` 为负，常表示低于大盘基准率的分组占比上升，或高于大盘基准率的分组占比下降。
- `interaction_contribution` 处理率值和占比同时变化的共同影响。

## 使用边界

- 脚本不负责取数、不判断指标口径是否正确。
- 脚本不证明因果，只量化贡献。
- 若样本量过小、分组不互斥、分母缺失，结果只能作为线索。
- Shapley、马尔可夫链、泰勒展开、定基代替暂不脚本化，避免通用脚本被误用。
