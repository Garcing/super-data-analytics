# 业务动作和 ROI 评估

用于发券、补贴、Push、大促、投放、产品上线等业务动作复盘。它回答“投入产出是否划算”和“指标变化是否支持继续做”，但单独的 ROI 不证明因果。

## 适用条件

- 有明确动作、时间窗口和影响人群。
- 至少能拿到收益和成本。
- 最好同时有前后对比、可比周期、分层指标或护栏指标。

如果有随机对照组，优先读取 [`ab-testing.md`](ab-testing.md)。如果有非随机对照组和干预前后数据，优先读取 [`did.md`](did.md)。

## 原理

### ROI

```text
net_benefit = benefit - cost
roi = net_benefit / cost
```

如果有毛利率：

```text
margin_adjusted_benefit = benefit * gross_margin_rate
margin_adjusted_roi = (margin_adjusted_benefit - cost) / cost
```

如果已经有增量毛利：

```text
incremental_margin_roi = (incremental_margin - cost) / cost
```

最终必须说明 ROI 使用的是收入、毛利、贡献毛利还是净利润口径。

### 业务动作评估

ROI 之外，还要看：

- 前后变化：动作后是否改善。
- 可比周期：同比、环比、同星期、同活动节奏是否可比。
- 漏斗节点：曝光、触达、点击、转化、支付、复购在哪里变化。
- 分层效果：不同渠道、人群、地区、版本是否表现一致。
- 护栏指标：留存、投诉、退款、卸载、性能、收入质量是否受损。

## 常见动作

### 发券和补贴

关注发券数、领取数、使用数、核销率、补贴成本、被券带动的订单和 GMV、毛利和净收益、原本会购买用户的蚕食、券后复购和价格敏感风险。

### Push 和消息

关注发送、送达、打开、点击、转化、次日留存、退订、投诉、卸载、频控和疲劳。不要只因为点击上升就判断长期有效。

### 产品上线

关注曝光和使用率、漏斗转化、北极星指标、留存和收入质量、性能、投诉、退款、客服等护栏，并按新老用户、渠道、设备、版本分层。

### 大促和投放

关注收入、毛利、投放或补贴成本、库存、履约、获客质量、复购、CAC、回本周期和饱和风险。

## 脚本调用

```bash
python evaluating-impact/scripts/impact.py <input.json>
```

## 输入 JSON：`roi`

```json
{
  "analysis_type": "roi",
  "benefit": 1200000,
  "cost": 300000,
  "gross_margin_rate": 0.4
}
```

也可以传入已经估算好的增量毛利：

```json
{
  "analysis_type": "roi",
  "benefit": 1200000,
  "cost": 300000,
  "incremental_margin": 450000
}
```

要求：

- `cost` 必须大于 0。
- `benefit` 应说明是总收益还是增量收益。
- `gross_margin_rate` 必须在 0 到 1 之间。

## 输出重点：`roi`

```text
benefit：收益
cost：成本
net_benefit：收益 - 成本
roi：净收益 / 成本
profitable：净收益是否为正
margin_adjusted_benefit：毛利口径收益
margin_adjusted_roi：毛利口径 ROI
incremental_margin_roi：增量毛利口径 ROI
```

## 输入 JSON：`sample_size_rate`

业务动作进入正式 A/B 前，可粗略估算二项率实验样本量：

```json
{
  "analysis_type": "sample_size_rate",
  "baseline_rate": 0.1,
  "minimum_detectable_effect": 0.02,
  "alpha": 0.05,
  "power": 0.8
}
```

输出：

```text
sample_size_per_group：每组建议样本量
warnings：样本量估算限制
```

## 解读边界

- ROI 为正不等于动作创造了增量，可能包含自然增长或原本会购买的人群。
- 收入口径 ROI 往往高估效果；高补贴、高退款、低毛利场景必须看毛利或贡献毛利。
- 如果护栏指标明显变差，即使短期 ROI 为正，也不应直接建议加码。
- 只有前后对比时，结论应写成方向性；若要更强因果，需要随机实验或 DID。
