# A/B 实验检验

用于随机分流条件下判断处理是否带来指标变化。A/B 实验不只看 p 值，还要同时看效果量、业务显著性、护栏指标和上线风险。

## 适用条件

- 用户、设备、订单或其他实验单元被随机分到实验组和对照组。
- 两组在实验期间只应因为处理不同而产生系统性差异。
- 主指标和观察窗口已经定义清楚。
- 有足够样本量和事件数。

如果没有随机分流，但有处理组/对照组和干预前后数据，优先读取 [`did.md`](did.md)。如果只有前后变化或 ROI，读取 [`roi-and-business-actions.md`](roi-and-business-actions.md)。

## 原理

### 比率指标

适合点击率、转化率、核销率、留存率等二项率指标。

```text
control_rate = control_success / control_n
treatment_rate = treatment_success / treatment_n
absolute_lift = treatment_rate - control_rate
relative_lift = absolute_lift / control_rate
```

脚本使用双样本比例 z-test 计算 p 值，给出差值的近似置信区间，并用 Wilson 方法给出实验组和对照组各自率值的置信区间。Wilson CI 在样本较小或率值接近 0/1 时比普通正态近似更稳。

### 均值指标

适合客单价、人均收入、人均时长、人均次数等均值指标。

```text
mean_difference = treatment_mean - control_mean
relative_difference = mean_difference / control_mean
```

脚本使用正态近似计算 p 值和均值差置信区间，并输出 Cohen's d 作为标准化效果量。Cohen's d 表示实验组和对照组均值相差多少个合并标准差，用来辅助判断“显著但是否足够大”。小样本、极端重尾或强偏态指标需要专项检验，不要只依赖聚合均值。

## 分析前检查

- 实验组和对照组是否随机分配。
- 分流比例是否符合预期，是否存在 SRM。
- 用户是否可能跨组污染。
- 主指标是否提前定义，是否存在事后挑指标。
- 观察窗口是否完整，是否提前停止。
- 样本量、成功数或事件数是否足够。
- 护栏指标是否覆盖留存、收入质量、投诉、退款、性能等关键风险。

## 脚本调用

```bash
python evaluating-impact/scripts/impact.py <input.json>
```

### 输入 JSON：`ab_rate`

```json
{
  "analysis_type": "ab_rate",
  "alpha": 0.05,
  "control": {"n": 10000, "success": 1200},
  "treatment": {"n": 10000, "success": 1350}
}
```

要求：

- 
` 必须大于 0。
- `success` 不能小于 0，也不能大于 
`。
- `alpha` 默认 0.05。

### 输出重点：`ab_rate`

```text
control_rate：对照组率值
treatment_rate：实验组率值
absolute_lift：绝对提升
relative_lift：相对提升
p_value：双样本比例检验 p 值
confidence_interval：绝对提升的近似置信区间
control_rate_ci / treatment_rate_ci：两组率值各自的 Wilson 置信区间
significant：是否在 alpha 阈值下显著
```

### 输入 JSON：`ab_mean`

```json
{
  "analysis_type": "ab_mean",
  "alpha": 0.05,
  "control": {"n": 500, "mean": 10.0, "stddev": 4.0},
  "treatment": {"n": 520, "mean": 10.8, "stddev": 4.2}
}
```

要求：

- `n` 必须大于 1。
- `stddev` 不能小于 0。
- 均值口径必须一致，例如都按用户、订单或会话聚合。

### 输出重点：`ab_mean`

```text
control_mean / treatment_mean：两组均值
mean_difference：均值差
relative_difference：相对差异
cohens_d：Cohen's d 标准化效果量
p_value：均值差检验 p 值
confidence_interval：均值差的近似置信区间
warnings：正态近似、小样本和重尾风险提示
```

## 解读边界

- 显著不等于值得上线：还要看提升幅度是否达到业务最小可接受效果。
- 不显著不等于没有效果：可能是样本量不足、指标噪声大、真实效果较小或周期太短。
- 主指标提升但护栏变差时，不要直接建议全量。
- 业务急着上线时，应给出选项：继续实验、扩大样本、低风险人群灰度、基于护栏小流量放量、或停止。
- Achieved power 不作为默认输出：它通常是 p 值的另一种表达，容易被误读成“实验质量证明”。业务决策更推荐看预设 power、样本量、MDE、效果量和置信区间。
- CUPED 可用于有用户级实验前协变量的高价值实验，用来降低方差；第一版 `impact.py` 不实现 CUPED，遇到这类需求应做专项明细数据分析。






