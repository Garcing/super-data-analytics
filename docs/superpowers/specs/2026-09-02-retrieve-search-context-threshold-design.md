# retrieve_search 高基数邻居控制设计

日期：2026-09-02

## 背景

`retrieve_search` 在完成向量、全文和精确匹配融合后，会为最终候选批量展开一跳图邻居。当前每个命中实体、每类邻居最多返回 20 条，超过上限时保留前 20 条并标记 `truncated=true`。

这一行为在高连接节点上会产生大量低价值上下文。例如检索“用户满意评分”时，第二候选“用户”维度组关联 49 个指标，返回其中 20 个指标的完整属性，显著放大响应，但这些指标并不是回答当前问题所必需的。

本设计以最小改动控制高基数邻居，不引入关系级策略、邻居属性投影或全局预算。

## 设计目标

- 保留低基数图邻居，继续支持指标到表、表关系和维度组等常见语义解析。
- 高基数邻居桶不返回任意样本，避免响应膨胀和误导模型。
- 允许调用方在只需要候选发现时完全关闭图上下文。
- 保持 18 个工具数量、工具名和顶层返回字段不变。
- 保持 `total` 和 `truncated` 的既有含义，并为主动省略提供明确原因。

## 非目标

第一阶段不实现以下能力：

- 不把邻居裁剪为只含 `key_field` 的身份卡片。
- 不给不同关系或关系方向配置不同展开策略。
- 不提供调用级 `context_limit` 或阈值参数。
- 不对邻居做语义相关性重排。
- 不提供无约束的 `context_mode="full"`；完整列举继续使用 `retrieve_cypher`。

## 公开工具参数

为 `retrieve_search` 增加可选参数：

```python
context_mode: Literal["auto", "none"] = "auto"
```

### `auto`

默认模式。融合候选后展开一跳邻居，并对每个“命中实体 + 邻居标签”桶应用服务端高基数阈值。

调用方省略 `context_mode` 时等同于 `auto`。

### `none`

不调用图邻居扩展。每个搜索结果仍保留 `context` 字段，但值为 `{}`。候选召回、融合排序、实体完整属性和 `retrieval` 证据均不受影响。

## 高基数阈值

服务端定义固定常量：

```python
CONTEXT_EXPANSION_THRESHOLD = 10
```

该阈值不作为 MCP 参数暴露，也不进入 `graph-config`。它是服务端响应保护规则，而不是业务查询条件。

阈值按每个“命中实体 + 邻居标签”桶独立应用：

- `total <= 10`：返回该桶全部邻居及完整业务属性。
- `total > 10`：返回空 `items`，保留真实 `total`，设置 `truncated=true` 和 `omitted_reason="high_cardinality"`。

高基数桶示例：

```json
{
  "指标": {
    "items": [],
    "total": 49,
    "truncated": true,
    "omitted_reason": "high_cardinality"
  }
}
```

不返回前三条、前十条或其他任意示例。调用方需要列举完整邻居时，先使用 `retrieve_schema` 确认关系，再用只读 `retrieve_cypher` 查询。

## 低基数桶与兼容性

低基数桶继续使用现有结构：

```json
{
  "表": {
    "items": [
      {"表名称": "semantic.fact_user_period_satisfaction", "中文表名": "用户期数评分事实表"}
    ],
    "total": 1,
    "truncated": false
  }
}
```

第一阶段不裁剪邻居属性，避免新增 `display_field` 配置或依赖字段名推断。

新增的 `omitted_reason` 只出现在主动省略的高基数桶中。已有调用方仍可仅依赖 `items`、`total` 和 `truncated`。

## 稳定排序

邻居查询应在 Cypher 层按邻居实体配置的 `key_field` 升序排序，再组装响应。稳定排序的目标是保证重复请求和测试输出顺序一致，不表示语义相关性。

不在 Python 层进行第二次相关性排序。高基数桶不会因为排序而保留部分邻居；超过阈值后仍统一返回 `items=[]`。

## 执行流程

`retrieve_search` 的流程保持为：

1. 校验问题、策略、目标标签和 `context_mode`。
2. 执行向量召回；hybrid 模式同时执行全文与精确匹配。
3. 使用现有 Weighted RRF 融合并截取最终候选。
4. `context_mode="none"` 时跳过图扩展，直接返回 `context={}`。
5. `context_mode="auto"` 时批量获取最终候选的一跳邻居。
6. 按邻居实体 `key_field` 稳定排序并计算每个桶的真实 `total`。
7. 对 `total <= 10` 的桶返回全部邻居；对 `total > 10` 的桶返回空 `items` 和省略原因。

图扩展仍发生在融合截断之后，不为落选候选查询邻居。

## 工具与文档契约

`retrieve_search` 工具说明需要明确：

- `context_mode="auto"` 是默认值，会展开受阈值控制的图邻居。
- `context_mode="none"` 不执行图邻居查询。
- 高基数桶返回 `items=[]`、真实 `total`、`truncated=true` 和 `omitted_reason="high_cardinality"`。
- 需要完整列举时使用 `retrieve_schema` 与只读 `retrieve_cypher`。

同步更新 `retrieving-context` Skill、Cypher 参考和 README 中相关的用户可见说明。工具总数保持 18。

## 测试要求

至少覆盖以下场景：

1. 邻居数为 0 时不产生空桶。
2. 邻居数为 10 时返回全部 10 条，`truncated=false`。
3. 邻居数为 11 时返回 `items=[]`、`total=11`、`truncated=true` 和正确的 `omitted_reason`。
4. 多个命中实体和多个邻居标签分别独立应用阈值。
5. 自环关系继续排除命中节点自身。
6. `context_mode="none"` 不调用邻居查询，所有结果的 `context` 均为 `{}`。
7. `context_mode` 非法值返回可操作的参数校验错误。
8. 邻居按目标实体 `key_field` 稳定排序。
9. MCP 输入 schema 和工具说明包含新的可选参数。
10. 现有 hybrid/vector 召回排序和 retrieval evidence 测试不回退。

## 验收标准

- 检索“用户满意评分”时，“用户”维度组的指标桶返回 `items=[]`、`total=49` 和高基数省略原因。
- 同一结果中不超过 10 条的表、表关系、维度组等邻居继续完整返回。
- `context_mode="none"` 返回相同候选排序，但不包含图邻居内容。
- 相同数据上的重复查询得到稳定的低基数邻居顺序。
- `python -m pytest -q`、`git diff --check` 通过。
- 工具列表仍为 18 个，检索 gold case 的 Recall@1、Recall@5 和 MRR@5 不下降。
