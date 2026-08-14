---
name: diagnosing-anomalies
description: 指标异动归因与贡献度拆解。当用户问指标为什么上涨、下跌、异常波动、同比环比变化、监控告警原因诊断、贡献度、归因拆解时使用；contribute 工具完成加法/乘法/比率三类贡献度计算。
metadata:
  skill-series: super-data-analytics
  chinese-name: 异动归因
  mcp-server: sda
  mcp-tools:
    owns:
      - contribute
    uses:
      - sql_query
      - sql_schema
      - retrieve_search
      - chart
---

# diagnosing-anomalies（异动归因）

当业务指标出现上涨、下跌或异常波动时，回答"为什么变了、谁贡献的"。通过 `sda` MCP 服务的 `contribute` 工具做贡献度拆解（加法 / 乘法 LMDI / 比率三法），配合 `sql_query` 取两期数据、`retrieve_search` 对齐口径。核心纪律：**先确认异动是真的，再解释为什么；贡献度是差值分解，不是因果证明**。

## 何时使用 / 何时不用

**用**：
- 用户问异动原因："GMV 为什么跌了"、"昨天 DAU 突增"、"转化率同比降了 2pp"。
- 需要贡献度拆解："各渠道对增长的贡献"、"哪个因子拉动了变化"。
- 监控告警后的根因排查。

**不用**：
- 只要具体数据值、不问原因 → querying-data 直接取数。
- 评估实验/策略效果（AB、DID、ROI）→ evaluating-impact。
- 预测未来走势 → predicting-trends。

## 决策流程

1. **复现**：先 `retrieve_search` 拿受治理口径，再 `sql_query` 取当前期与基线期数据。**两期口径必须一致**（同过滤条件、同粒度、同完整度），否则归因无意义。
2. **确认异动成立**：算出绝对变化、相对变化；排除数据延迟/补数/截断、埋点或 ETL 变更、未完整周期、节假日/同期不可比。是数据问题就先修数据或将其量化为候选原因，不要把脏数据下钻结果当业务根因。
3. **按指标结构选 method**：
   - **加法型**（收入、订单数、DAU 等可按维度加合的绝对量）→ `add`：各维度差值直接分解。
   - **乘法型**（GMV=流量×转化×客单等连乘结构；漏斗环节转化率也属此类）→ `multiply`：LMDI/log 拆解。
   - **比率型**（转化率、成功率、投诉率等 P/Q 指标按分组拆）→ `ratio`：组内/结构/交叉三分。比率指标**不能**直接用 add 拆差值。
4. **调 `contribute` 计算**，输出 `{summary, rows, checks}`。
5. **下钻**：对贡献绝对值最大的维度递归再拆（每层保留可解释比例）；比率型留意辛普森悖论（各组都变好但总体变差 = 结构变化）。
6. **事件验证**：把 Top 贡献项与同期运营活动、改版、发布记录、投放变化互相印证——时间吻合不等于因果。
7. **结论表达**："X 维度贡献了总变化的 Y%" + 方向（同向解释/反向抵消）+ 置信度（已验证/较可能/待验证）+ 未解释残差。

## 工具契约

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `contribute` | `method: "add"\|"multiply"\|"ratio"` 必填；`payload: dict` 必填，结构随 method：**add** `{baseline_total: float=0, current_total: float=0, items: [{name?: str（缺省 `item_N`）, baseline: float 必填, current: float 必填}]}`（items 非空数组必填）；**multiply** `{factors: [{name?: str（缺省 `factor_N`）, baseline: float 必填且 >0, current: float 必填且 >0}]}`（factors 非空必填，总体=各因子连乘自动得出）；**ratio** `{groups: [{name?: str（缺省 `group_N`）, baseline_numerator: float, baseline_denominator: float>0, current_numerator: float, current_denominator: float>0}]}`（groups 非空必填，四数字字段均必填，总体率值自动加总得出）。数字字段传 bool 或非数字会校验报错 | `{summary, rows, checks}`：summary 含 `baseline_total/current_total/delta/relative_change`（relative_change 基线为 0 时 null）；rows 每行含 `contribution_value`（贡献量）、`contribution_share`（贡献率 Vi/ΔY，可超 100% 或为负）、`relative_contribution`（相对贡献 Vi/Y0）、`direction`（同向解释/反向抵消/无明显贡献/总变化接近0方向不解释），multiply 另有 `factor_ratio/log_delta/log_contribution_share`，ratio 另有 `baseline_rate/current_rate/baseline_weight/current_weight/within_contribution/mix_contribution/interaction_contribution`；checks 含 `sum_contribution/residual/warnings`。**先看 checks**：residual≈0 且 warnings 空才可信，再按 contribution_value 绝对值排序解读 |

## 调用示例

转化率（下单数/访客数）按渠道两期对比。调 `contribute`：

```json
{
  "method": "ratio",
  "payload": {
    "groups": [
      {"name": "自然流量", "baseline_numerator": 800, "baseline_denominator": 3000, "current_numerator": 950, "current_denominator": 3500},
      {"name": "广告投放", "baseline_numerator": 300, "baseline_denominator": 2000, "current_numerator": 400, "current_denominator": 2500}
    ]
  }
}
```

返回摘要：`summary.delta` 为总体转化率变化；rows 中自然流量的 `within_contribution`（自身率值变化）、`mix_contribution`（占比结构变化）、`interaction_contribution`、`contribution_value` 与 `direction`；`checks.residual` 应≈0（非 0 说明分组不互斥或分母不完整）。下一步：对 `contribution_value` 绝对值最大的组用 `sql_query` 递归下钻（如再按端/人群拆），或调 `chart` 画贡献瀑布。

## 陷阱与注意

- **两期口径必须一致**：过滤条件、粒度、完整度任一不同则归因失真；口径拿不准先 `retrieve_search` 对齐，字段拿不准先 `sql_schema`。
- **比率指标不能直接用 add**：拆分子分母各自的差值不等于率值变化的分解，必须用 `ratio`。
- **multiply 拒绝 0/负值**：log 拆解要求全部因子为正；有 0 值需业务认可的平滑处理或换方法。
- **checks 不过先修数据**：residual 显著非 0 或有 warnings，说明分项不互斥/不完整或方法选错，先补全分组再解读，不要硬讲结论。例外：multiply 在总体对数变化≈0 时（各因子一涨一跌相抵），贡献置 0、residual=总变化且必带 warning——这是方法的边界情形，不是数据错误。
- **贡献度 ≠ 因果**："贡献最大"要写成"已验证/较可能/待验证"，需独立证据（实验、事件、发布记录）才能说根因。
- 报告数字要给基数和影响量，不要只给百分比；贡献率（占 ΔY）与相对贡献（占 Y0）不要混用。
- 贡献值合计约等于总变化（残差≈0）时也应说明未解释部分与置信度，长尾维度不必穷尽下钻。

## 深入参考

- [references/attribution-methods.md](references/attribution-methods.md) —— 七种归因方法的适用场景、数据要求与选择判据；哪些由 `contribute` 支撑、哪些需配合 `sql_query` 手工分析。
