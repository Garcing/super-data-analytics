# 乘法型拆解：LMDI / log 拆解

用于 `Y = ΠXi` 的指标，例如 `GMV = UV * CVR * AOV`、`PV = UV * 人均PV`。漏斗链路也可先转成多个转化率因子的乘积后使用本方法。

## 原理

```text
ln(Y) = Σln(Xi)
Δln(Y) = ln(Y1) - ln(Y0)
Δln(Xi) = ln(Xi1) - ln(Xi0)
Ci_log = Δln(Xi) / Δln(Y)
```

如需还原为原指标单位，用对数平均权重：

```text
L(Y1, Y0) = (Y1 - Y0) / (ln(Y1) - ln(Y0))
Vi ≈ L(Y1, Y0) * Δln(Xi)
Ci = Vi / ΔY
Ri = Vi / Y0
```

## 脚本调用

```bash
python diagnosing-anomalies/scripts/contribution.py multiply <input.json>
```

## 输入 JSON

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
- 零值、负值或跨量级剧烈变化会让 log 结果不稳定，需要换方法或做业务认可的平滑处理。

## 输出重点

```text
rows[].factor_ratio：因子当前值 / 基准值
rows[].log_delta：因子对数变化
rows[].log_contribution_share：因子解释总体对数变化的比例
rows[].contribution_value：还原到原指标单位的近似贡献量
checks.residual：LMDI 还原残差
```

解读时优先说业务链路：例如“GMV 增长主要由 AOV 和 CVR 拉动，UV 下滑抵消了一部分增长”。
