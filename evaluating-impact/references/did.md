# 双重差分法 DID

用于没有随机实验，但存在处理组、对照组、干预前和干预后数据的场景。DID 估计的是处理组变化扣除对照组同期变化后的增量。

## 适用条件

- 有明确干预动作和干预时间。
- 有处理组和业务上可解释的对照组。
- 两组都有干预前和干预后数据。
- 干预前两组走势大致可比。

常见场景：

- 城市试点策略。
- 分区域活动。
- 渠道政策变化。
- 分批上线功能。
- 某类用户受到策略影响，另一类相近用户未受影响。

## 原理

四格结构：

| 组别 | 干预前 | 干预后 |
| --- | --- | --- |
| 处理组 | treatment_before | treatment_after |
| 对照组 | control_before | control_after |

计算：

```text
treatment_change = treatment_after - treatment_before
control_change = control_after - control_before
did_effect = treatment_change - control_change
relative_did_effect = did_effect / treatment_before
```

DID 的直觉是：处理组自己涨了多少不够，还要扣掉对照组同期自然涨跌。扣掉后剩下的部分，才更接近干预带来的增量。

## 分析前检查

- 处理组和对照组在干预前是否趋势接近。
- 两组业务结构是否相似，例如渠道、人群、城市等级、历史规模。
- 干预时间是否清楚，是否存在提前泄露或滞后生效。
- 同期是否有只影响某一组的活动、投放、价格、库存、竞品或数据口径变化。
- 是否存在用户迁移、污染或样本组成变化。

## 脚本调用

```bash
python evaluating-impact/scripts/impact.py <input.json>
```

## 输入 JSON：`did`

```json
{
  "analysis_type": "did",
  "treatment_before": 100,
  "treatment_after": 130,
  "control_before": 80,
  "control_after": 90
}
```

要求：

- 四个值必须是数值，且来自同一指标口径。
- 干预前后窗口应可比，例如同样天数、同样完整度、同样过滤条件。
- 如果是比率指标，优先用同口径聚合后的率值，并同时检查分子分母规模。

## 输出重点

```text
treatment_change：处理组变化
control_change：对照组变化
did_effect：双重差分效果
relative_did_effect：相对处理组基期的 DID 效果
warnings：平行趋势和业务可比性提示
```

## 解读边界

- `did_effect` 是计算结果，不自动证明因果；可信度取决于平行趋势和业务可比性。
- 只有一个干预前周期时，很难判断趋势是否平行，结论强度要降低。
- 如果干预前趋势已经明显分叉，不要把 DID 写成“较可信因果”。
- 如果同一时间处理组还有独立活动或事故，DID 可能混入其他影响。
- 第一版脚本只支持四格聚合 DID，不支持面板回归、分批干预或动态效应。
