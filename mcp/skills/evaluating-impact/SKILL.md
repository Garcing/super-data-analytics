---
name: evaluating-impact
description: 效果评估与实验检验。当用户问 AB 实验/实验结果显不显著、新功能/活动/发券/投放有没有效果、能不能推全量、DID 试点增量、ROI 值不值、要不要加码时使用；impact 工具完成 AB 比率/均值检验、DID、ROI 与样本量估算五类计算。
metadata:
  skill-series: super-data-analytics
  chinese-name: 效果评估
  mcp-server: sda
  mcp-tools:
    owns:
      - impact
    uses:
      - sql_query
      - sql_schema
      - retrieve_search
---

# evaluating-impact（效果评估）

回答"做的事到底有没有用、值不值、要不要推全量"。通过 `sda` MCP 服务的 `impact` 工具做确定性计算（AB 比率/均值检验、DID、ROI、样本量估算），配合 `sql_query` 取实验与成本数据、`retrieve_search` 对齐口径。核心纪律：**先确认评估对象与决策目标，再选方法；不显著≠没效果，统计显著≠业务值得**；结论必须标注强度（强因果/较可信依赖假设/仅方向性/无法判断）。

## 何时使用 / 何时不用

**用**：
- A/B 实验结果解读：显不显著、样本量够不够、能不能全量。
- 城市试点、分批上线等非随机干预：DID 双重差分。
- 发券、补贴、Push、投放、大促的 ROI 与业务动作复盘。

**不用**：
- 问指标为什么涨跌 → diagnosing-anomalies。
- 问未来走势/目标 → predicting-trends。
- 只要数据不问效果 → querying-data。

## 决策流程

1. **明确评估问题**：动作是什么、时间窗口、人群（实验/对照）、主指标+护栏指标、成本、要支持的决策（全量/停止/加码/继续观察）。缺失会改变结论时先追问。
2. **复现口径**：`retrieve_search` 拿指标定义，`sql_query` 取数；确认指标分子分母、分流/曝光口径、观察窗口完整、成本收益同口径、无同期干扰活动。
3. **按数据条件路由方法**：
   - 有随机分流 → AB 类（`ab_rate` 率值 / `ab_mean` 均值）。
   - 无随机但有处理组+对照组+干预前后数据 → `did`。
   - 只有收益和成本 → `roi`（不证明因果，只判投入产出）。
   - 只有处理组前后数据 → 前后/同环比对比，结论只能写方向性；要更强证据需补对照。
4. **实验前置检查**（AB 类）：随机分流是否真随机；两组样本比例是否符合预期（SRM 校验，比例失衡则结果不可信）；样本量是否够（不够先跑 `sample_size_rate` 估）；主指标是否事先定义（防事后挑指标）；是否提前停止。
5. **调 `impact` 计算**，按 analysis_type 读对应输出。
6. **护栏指标检查**：留存、投诉、退款、性能、收入质量是否变差；主指标涨但护栏跌不建议全量。
7. **决策建议框架**：显著且效果量达到业务最小可接受水平、护栏稳定 → 推全量；不显著 → 先看样本量/MDE 是否根本检不出该量级（可能是功效不足，不是"没效果"），再定继续实验/扩样本/停止；ROI 为正还要看增量口径与护栏再谈加码。

## 工具契约

`impact` 入参：`analysis_type` 必填（`ab_rate` | `ab_mean` | `did` | `roi` | `sample_size_rate`）；`payload?: dict` 可选——**payload 内字段会被平铺到顶层再校验**，所以字段直接按各类型的顶层字段名写在 payload 里（不要嵌套成 `{params: {...}}`）。各类型 payload 与返回：

| analysis_type | payload 字段 | 返回关键字段与解读 |
|---|---|---|
| `ab_rate` | `control: {n>0, success: 0..n}` 必填、`treatment` 同构必填、`alpha?`（默认 0.05，双尾） | `control_rate`/`treatment_rate`、`absolute_lift`/`relative_lift`（control_rate 为 0 时 relative_lift 为 null）、`p_value`（双样本比例 z 检验）、`significant`（p<alpha）、`confidence_interval`（绝对提升的近似 CI，**区间不含 0 且量级够业务门槛才建议全量**）、`control_rate_ci`/`treatment_rate_ci`（Wilson CI，小样本/率值近 0/1 时比正态近似稳） |
| `ab_mean` | `control: {n>1, mean, stddev>=0}` 必填、`treatment` 同构必填、`alpha?` | `control_mean`/`treatment_mean`、`mean_difference`/`relative_difference`（control_mean 为 0 时 relative_difference 为 null）、`cohens_d`（标准化效果量，判"显著但够不够大"）、`p_value`、`significant`、`confidence_interval`；warnings 必含"正态近似，小样本/重尾建议专项检验"——两组聚合口径必须一致（都按用户/都按订单） |
| `did` | `treatment_before`/`treatment_after`/`control_before`/`control_after` 四数必填，同口径同可比窗口 | `treatment_change`/`control_change`、`did_effect`（双重差分增量）、`relative_did_effect`（除以 treatment_before，为 0 时 null）；warnings 必含"不自动证明平行趋势"——**平行趋势不成立则结果不可信**，需先用事件研究/多期前置数据检查干预前两组走势 |
| `roi` | `benefit`、`cost>0` 必填；`gross_margin_rate?`（0..1）；`incremental_margin?`（已估好的增量毛利） | `net_benefit`、`roi`（=净收益/成本）、`profitable`；传 gross_margin_rate 另出 `margin_adjusted_*` 毛利口径三件套；传 incremental_margin 另出 `incremental_margin_roi`/`incremental_margin_profitable`。**benefit 必须说清是总收入还是因果增量**——收入口径 ROI 常高估 |
| `sample_size_rate` | `baseline_rate`（开区间 0<x<1，取 0 或 1 会校验拒绝）、`minimum_detectable_effect`（>0 且 baseline+MDE<1）必填；`alpha?`、`power?`（默认 0.8） | `sample_size_per_group`（每组建议样本量，近似估算）；实际实验还要考虑分流、触达率、周期性 |

## 调用示例

新按钮 AB 实验：对照组 10000 曝光 1200 转化，实验组 10000 曝光 1350。调 `impact`：

```json
{
  "analysis_type": "ab_rate",
  "payload": {
    "alpha": 0.05,
    "control": {"n": 10000, "success": 1200},
    "treatment": {"n": 10000, "success": 1350}
  }
}
```

返回摘要：`absolute_lift`≈0.015、`relative_lift`≈0.125、`p_value`<0.05、`significant: true`、`confidence_interval` 不含 0。下一步：先做 SRM 校验（两组 n 比例是否符合分流比），再查护栏指标（退货率、投诉、留存），量级达到业务最小可接受效果才建议全量。

试点城市 DID：处理组 GMV 100→130，对照城市 80→90。`analysis_type: "did"`，payload 平铺四个数字；返回 `did_effect`=20、`relative_did_effect`=0.2。下一步：取干预前多期数据验证平行趋势（可用 `sql_query` 拉周级序列目测/分组对比），不平行则降级为方向性结论。

## 陷阱与注意

- **不显著≠没效果**：可能是样本量不足、指标噪声大、真实效果小于 MDE。先回看 `sample_size_rate` 的预设 power/MDE，再决定扩样本还是停止。
- **多重比较**：同时看多个指标时单指标"显著"要打折（5 个独立指标下 p<0.05 期望出现 0.25 个假阳性）；主指标必须事先定义。
- **SRM**：两组样本比例明显偏离分流比（如 1:1 却拿到 1.05:1）说明分流被污染，任何显著性结论作废。
- **DID 平行趋势**：干预前两组走势分叉则 did_effect 不可信；只有一个前置周期时结论强度必须降级。
- **ROI 增量口径**：benefit 是自然增长+蚕食+因果增量的混合；收入口径高估、高补贴/高退款场景必须看毛利或增量毛利口径。
- **payload 是平铺的**：字段直接写 `{"benefit": ..., "cost": ...}`，不要再嵌一层；字段名/结构错会直接 ValidationError。
- **统计显著≠业务显著**：巨大样本下 0.01pp 提升也显著；上线决策看效果量+置信区间下界+护栏，不只看 p 值。

## 深入参考

- [references/experiment-design.md](references/experiment-design.md) —— AB 实验设计（假设/指标分层/样本量与 MDE/SRM）、DID（平行趋势/对照选择/事件研究）、ROI 与业务行动决策框架的展开方法卡。
