---
name: predicting-trends
description: 业务趋势预测与目标制定。当用户问下个月/下季度指标预计多少、按当前趋势会怎样、目标定多少合适、月底能不能达成目标等需要预测未来值的问题时使用；forecast 工具完成时序预测 + 回测 + 置信带。
metadata:
  skill-series: super-data-analytics
  chinese-name: 趋势预测
  mcp-server: sda
  mcp-tools:
    owns:
      - forecast
    uses:
      - sql_query
      - sql_schema
      - chart
---

# predicting-trends（趋势预测）

回答"未来会怎样"：下月 GMV 预计多少、目标定多少、按当前趋势能否达成。通过 `sda` MCP 服务的 `forecast` 工具做轻量时序预测（8 个可解释模型 + auto_baseline 自动选型），自动回测给出误差与置信带。核心纪律：**先确认历史序列可用，再外推；预测值不是目标值；结果必须带区间和置信度，不报伪精确单点**。

## 何时使用 / 何时不用

**用**：
- 用户问未来值："下个月订单量预计多少"、"Q4 收入趋势会怎样"。
- 目标制定："下月目标定多少合适"（三档：保守/基准/挑战，详见 references/target-setting.md）。
- 达成判断："月底能不能完成目标"（用 `target` 入参算缺口）。
- 资源预估："按当前趋势需要多少库存/人力"。

**不用**：
- 问过去为什么变 → diagnosing-anomalies（先归因再预测；两类问题并存时先排查异常和数据质量）。
- 只要历史数据值 → querying-data 直接取数。
- 评估策略效果（AB/DID/ROI）→ evaluating-impact。

## 决策流程

1. **预测适用性三查**（任一不过就不要硬预测，改场景分析或说明不可靠）：
   - **历史点数够吗**：至少 2 点（校验下限），<6 点内核会出 warning 置 low confidence；建议 ≥6 点再外推，horizon 不超过历史长度的合理比例。
   - **有无结构断点**：改版、改口径、大促、价格调整之后，断点前的历史不能直接外推——只用断点后数据，或做分段/场景预测。
   - **季节性明显吗**：主导且历史 ≥2 个完整周期 → `seasonal_naive` + `season_length`；否则简单基线即可。
2. **取历史序列**：`sql_query` 按目标粒度聚合出 `date + value` 序列（受治理指标先经 retrieving-context 对齐口径）。**最新周期必须完整**——未结束的月/周不能当完整点用。
3. **构造 payload 调 `forecast`**：字段照下方契约；拿不准模型就用 `auto_baseline`（回测比选）。
4. **解读顺序**：先看 `warnings`（数据量不足/结构断点要带入结论，不能隐藏）→ 再看 `backtest`（`mape` ≤8% 高可信、≤20% 中等、>20% 低）→ 结论用**置信带表达**："预计 X（区间 lower–upper），置信度 high/medium/low"，区间是启发式业务范围不是严格统计置信区间。
5. **可视化**：配 `chart` 画历史 + 预测（预测段可用 lower/upper 画带）。

## 工具契约

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `forecast` | `payload: dict` 必填：`metric: str` 必填（指标名，仅展示用）；`grain: "day"\|"week"\|"month"\|"quarter"` 必填；`horizon: int` 必填（正整数，预测周期数）；`model: str` 必填，枚举 `naive`/`seasonal_naive`/`moving_average`/`weighted_moving_average`/`exponential_smoothing`/`holt_linear`/`linear_trend`/`log_linear_trend`/`auto_baseline`；`series: [{date: "YYYY-MM-DD", value: number}]` 必填（≥2 行，无重复日期，可乱序会自动排序，value 有限数值）；`season_length?: int`（默认 0，seasonal_naive 必传且需 ≥2 个完整周期）；`target?: number`（达成判断用，算预测合计与目标缺口）；`options?: dict`（模型参数：`window` 移动平均窗口、`alpha`/`beta` 平滑系数、`holdout` 回测留出期数（默认 min(3, max(1, len//4))，上限 len/2）、`allow_log_trend` 默认 true）。`log_linear_trend` 要求全值 >0；`holt_linear` 需 ≥3 点 | `{metric, model, model_reason, forecast, summary, backtest, confidence, assumptions, warnings}`：forecast 为 `[{date, value, lower, upper}]`（点值 + 启发式区间带）；summary 含 `forecast_total`（horizon 合计）、`last_actual`、`change_vs_last_actual`（首期预测对最近实际的相对变化）、`target_gap`（传了 target 才有，预测合计 − 目标）；backtest 含 `holdout/mae/mape/rmse`（历史 <4 点时 holdout=0 且指标为 null）；confidence 为 `high/medium/low`（有 warning 必 low；无 mape 可算时 medium）。**先看 warnings，再用 mape 判可信度，结论报区间不报裸单点** |

## 调用示例

月度收入预测未来 3 个月，拿不准模型用 `auto_baseline`。调 `forecast`：

```json
{
  "payload": {
    "metric": "月度 GMV",
    "grain": "month",
    "horizon": 3,
    "model": "auto_baseline",
    "series": [
      {"date": "2025-09-01", "value": 830000}, {"date": "2025-10-01", "value": 860000},
      {"date": "2025-11-01", "value": 895000}, {"date": "2025-12-01", "value": 910000},
      {"date": "2026-01-01", "value": 935000}, {"date": "2026-02-01", "value": 960000},
      {"date": "2026-03-01", "value": 985000}, {"date": "2026-04-01", "value": 1010000},
      {"date": "2026-05-01", "value": 1042000}, {"date": "2026-06-01", "value": 1068000},
      {"date": "2026-07-01", "value": 1095000}, {"date": "2026-08-01", "value": 1123000}
    ]
  }
}
```

返回摘要：`model` 为回测比选出的基线（`model_reason` 说明选型依据），`forecast` 3 行各含点值与 lower/upper，`backtest.mape` 给可信度标尺，`confidence` 为整体分级。下一步：结论写成"预计 9 月 GMV 约 X，合理区间 lower–upper，置信度 N"；调 `chart` 画 12 个月历史 + 3 个月预测带；用于目标制定则按 references/target-setting.md 出三档建议。

## 陷阱与注意

- **数据点不足不要硬预测**：<6 点内核置 warning 且 confidence 必为 low；只有 2-3 个点预测未来一年，应直接说明历史不足、改场景分析。
- **结构断点**：口径变更、改版、大促前后模式不同，断点前历史不能外推——截断到断点后重跑，或分场景给结论。
- **最新周期不完整**：进行中的月/周不能当完整点（拉 SQL 时用 `date_trunc` + 已完成周期过滤，或先折算）。
- **区间不是保证**：lower/upper 是残差启发式带宽（不随 horizon 展宽，但实际不确定性随 horizon 增大），长 horizon 结论要显式说"越远越不准"。
- **活动增长 ≠ 趋势**：把大促/投放带来的短期增长外推成长期趋势是最常见错误。
- **目标 ≠ 预测**：目标是业务决策，预测只是基准之一；三档目标与达成 run rate 判断见 [references/target-setting.md](references/target-setting.md)。
- `seasonal_naive` 需 `season_length` 且 ≥2 个完整周期；`log_linear_trend` 拒绝 0/负值；`holt_linear` 需 ≥3 点——这些不满足内核直接报错，不是静默降级。
- 低置信度预测不要用过度小数位包装；warnings 必须带入最终回答。

## 深入参考

- [references/target-setting.md](references/target-setting.md) —— 目标制定方法论：三档目标与预测区间/点值的映射、达成判断 run rate 计算、目标推荐的考量因素。
