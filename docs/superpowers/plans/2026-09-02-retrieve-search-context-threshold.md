# retrieve_search Context Threshold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound `retrieve_search` graph context by omitting all items from neighbor buckets larger than 10 and allow callers to disable graph expansion with `context_mode="none"`.

**Architecture:** Keep candidate retrieval and WRRF fusion unchanged. Apply the fixed threshold inside `Neo4jClient.fetch_graph_context_batch`, sort neighbors by each target entity's configured `key_field`, and gate the existing batch expansion in `search`. The MCP tool remains thin and forwards the new optional mode.

**Tech Stack:** Python 3.10+, Neo4j Python driver, FastMCP, Pydantic-generated tool schemas, pytest.

---

## File map

- Modify `sda_mcp/skills/retrieving_context.py`: threshold behavior, deterministic Cypher ordering, `context_mode` validation and expansion gating.
- Modify `sda_mcp/tools/retrieve_tools.py`: public `context_mode` parameter and tool description.
- Modify `tests/test_retrieving_context.py`: core boundary, ordering, mode validation and no-expansion tests.
- Modify `tests/test_server_tools.py`: MCP input-schema/default forwarding tests.
- Modify `skills/retrieving-context/SKILL.md`: workflow guidance for `auto` and `none`.
- Modify `skills/retrieving-context/references/cypher-guide.md`: high-cardinality bucket contract and deterministic ordering.
- Modify `README.md`: concise user-visible context-control description.

### Task 1: High-cardinality bucket behavior and stable ordering

**Files:**
- Modify: `tests/test_retrieving_context.py`
- Modify: `sda_mcp/skills/retrieving_context.py`

- [ ] **Step 1: Replace the old truncation test with threshold boundary tests**

Add tests asserting 10 neighbors are returned in full and 11 neighbors produce an empty high-cardinality bucket:

```python
def test_batch_context_at_threshold_returns_all(monkeypatch):
    records = [{"nodeId": "m1", "props": {"表名称": f"t{i}"}} for i in range(10)]
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
        {"表": {"key_field": "表名称"}},
    )
    assert ctx["m1"]["表"] == {
        "items": [{"表名称": f"t{i}"} for i in range(10)],
        "total": 10,
        "truncated": False,
    }


def test_batch_context_over_threshold_omits_items(monkeypatch):
    records = [{"nodeId": "m1", "props": {"表名称": f"t{i}"}} for i in range(11)]
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
        {"表": {"key_field": "表名称"}},
    )
    assert ctx["m1"]["表"] == {
        "items": [],
        "total": 11,
        "truncated": True,
        "omitted_reason": "high_cardinality",
    }
```

- [ ] **Step 2: Add a Cypher ordering assertion**

```python
def test_batch_context_orders_by_neighbor_key_field(monkeypatch):
    client, session = _make_client(monkeypatch)
    client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
        {"表": {"key_field": "表名称"}},
    )
    assert "ORDER BY other.`表名称`" in session.captured_cyphers[0]
```

- [ ] **Step 3: Run the focused tests and verify failure**

Run:

```powershell
python -m pytest tests/test_retrieving_context.py -k "batch_context" -q
```

Expected: failures because `fetch_graph_context_batch` does not accept entity config, still keeps the first 20 items, and emits no `ORDER BY`.

- [ ] **Step 4: Implement the fixed threshold and ordering**

Change the constant and method signature:

```python
CONTEXT_EXPANSION_THRESHOLD = 10

def fetch_graph_context_batch(
    self,
    hits: list[dict[str, Any]],
    relationships: list[dict],
    entities: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
```

Within `expand`, resolve and escape the target entity key, append a Cypher order clause, collect complete low-cardinality buckets, then replace overflowing items:

```python
other_key = entities.get(other_label, {}).get("key_field")
if not other_key:
    raise ValidationError(f"graph-config.entities.{other_label}.key_field 不能为空")
esc_other_key = other_key.replace("`", "``")
cypher = (
    f"MATCH (n){rel_pattern}(other:`{esc_other}`) "
    f"WHERE elementId(n) IN $nodeIds{self_exclude} "
    "RETURN elementId(n) AS nodeId, properties(other) AS props "
    f"ORDER BY other.`{esc_other_key}`"
)
```

After reading all records, normalize each bucket:

```python
for hit_context in contexts.values():
    for entry in hit_context.values():
        if entry["total"] > CONTEXT_EXPANSION_THRESHOLD:
            entry["items"] = []
            entry["truncated"] = True
            entry["omitted_reason"] = "high_cardinality"
```

During record iteration, append all cleaned properties; do not apply the old first-N truncation.

- [ ] **Step 5: Update all core call sites and existing test calls**

Pass `entities` from `search`:

```python
client.fetch_graph_context_batch(candidates, relationships, entities)
```

Update existing direct test calls with minimal entity configuration, for example:

```python
{"指标": {"key_field": "指标ID"}, "表": {"key_field": "表名称"}}
```

- [ ] **Step 6: Run focused tests and verify success**

Run:

```powershell
python -m pytest tests/test_retrieving_context.py -k "batch_context" -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit the core behavior**

```powershell
git add sda_mcp/skills/retrieving_context.py tests/test_retrieving_context.py
git commit -m "feat: bound retrieve search graph context"
```

### Task 2: Add `context_mode` to the core and MCP contract

**Files:**
- Modify: `tests/test_retrieving_context.py`
- Modify: `tests/test_server_tools.py`
- Modify: `sda_mcp/skills/retrieving_context.py`
- Modify: `sda_mcp/tools/retrieve_tools.py`

- [ ] **Step 1: Add failing core mode tests**

Add an invalid-mode test:

```python
def test_search_rejects_unknown_context_mode(monkeypatch):
    monkeypatch.setattr(r, "load_config", lambda: {"graph-config": GC})
    with pytest.raises(ValidationError, match="context_mode"):
        r.search("GMV", context_mode="full")
```

Extend the existing fake client with a counter and assert `none` skips expansion while preserving empty context:

```python
def test_search_context_none_skips_graph_expansion(monkeypatch):
    calls = []
    # Configure the existing search fakes, then make fetch append to calls.
    out = r.search("GMV", strategy="vector", context_mode="none")
    assert calls == []
    assert all(item["context"] == {} for item in out["results"])
```

- [ ] **Step 2: Add failing MCP schema and forwarding tests**

Assert the generated input schema exposes only the two supported values and defaults to `auto`:

```python
context_mode = _tools()["retrieve_search"].input_schema["properties"]["context_mode"]
assert context_mode["default"] == "auto"
assert set(context_mode["enum"]) == {"auto", "none"}
```

Update the mocked `_search` signature and assert the default forwarded value:

```python
lambda question, top_k=5, targets=None, strategy="vector", context_mode="auto": {
    "question": question, "strategy": strategy, "results": []
}
```

- [ ] **Step 3: Run focused tests and verify failure**

Run:

```powershell
python -m pytest tests/test_retrieving_context.py tests/test_server_tools.py -k "context_mode or retrieve_search" -q
```

Expected: failures because neither the core nor MCP tool accepts `context_mode`.

- [ ] **Step 4: Implement core validation and expansion gating**

Extend `search`:

```python
def search(
    question: str,
    top_k: int = 5,
    targets: list[str] | None = None,
    strategy: str = "hybrid",
    context_mode: str = "auto",
) -> dict[str, Any]:
    ...
    if context_mode not in ("auto", "none"):
        raise ValidationError("context_mode 必须是 auto|none")
```

Gate expansion without changing result shape:

```python
contexts = (
    client.fetch_graph_context_batch(candidates, relationships, entities)
    if context_mode == "auto" and relationships and candidates else {}
)
```

- [ ] **Step 5: Expose and forward the MCP parameter**

In `retrieve_tools.retrieve_search`, add:

```python
context_mode: Annotated[
    Literal["auto", "none"],
    Field(description="auto（默认）展开受高基数阈值控制的图邻居；none 不查询图邻居。"),
] = "auto",
```

Forward it to the core:

```python
return _search(
    question=question,
    top_k=top_k,
    targets=targets,
    strategy=strategy,
    context_mode=context_mode,
)
```

Update the docstring to describe the high-cardinality bucket shape and `retrieve_cypher` fallback.

- [ ] **Step 6: Run focused tests and verify success**

Run:

```powershell
python -m pytest tests/test_retrieving_context.py tests/test_server_tools.py -k "context_mode or retrieve_search" -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit the public contract**

```powershell
git add sda_mcp/skills/retrieving_context.py sda_mcp/tools/retrieve_tools.py tests/test_retrieving_context.py tests/test_server_tools.py
git commit -m "feat: add retrieve search context mode"
```

### Task 3: Synchronize workflow and user documentation

**Files:**
- Modify: `skills/retrieving-context/SKILL.md`
- Modify: `skills/retrieving-context/references/cypher-guide.md`
- Modify: `README.md`

- [ ] **Step 1: Update the retrieving workflow**

Document that default `auto` returns all neighbors only for buckets of at most 10, high-cardinality buckets are count-only, and `none` is appropriate when only candidate discovery is required.

- [ ] **Step 2: Replace the old “first 20” Cypher guidance**

Use this exact contract in `cypher-guide.md`:

```text
每命中、每类邻居标签总数不超过 10 时返回全部邻居；超过 10 时 items=[]、total 为真实总数、truncated=true，并返回 omitted_reason="high_cardinality"。
```

State that low-cardinality neighbors are ordered by their configured `key_field`, and complete traversal uses schema plus bounded read-only Cypher.

- [ ] **Step 3: Add concise README discoverability**

Extend the business semantic-layer capability description to mention controllable graph context and high-cardinality omission without duplicating the full workflow.

- [ ] **Step 4: Check documentation consistency**

Run:

```powershell
rg -n "20 个邻居|前 20|最多 20|context_mode|high_cardinality|超过 10" README.md skills/retrieving-context
```

Expected: no stale “return first 20 neighbors” description remains; the new mode and threshold contract appear in the intended files.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md skills/retrieving-context/SKILL.md skills/retrieving-context/references/cypher-guide.md
git commit -m "docs: explain bounded graph context retrieval"
```

### Task 4: Full verification and live read-only smoke test

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run the complete offline suite**

Run:

```powershell
python -m pytest -q
```

Expected: all offline tests pass; environment-gated integration tests remain skipped.

- [ ] **Step 2: Run whitespace and repository checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; status contains only intentional changes, or is clean after commits.

- [ ] **Step 3: Run offline retrieval-quality unit tests**

Run:

```powershell
python -m pytest tests/test_retrieval_quality.py -q
```

Expected: four unit tests pass and the live quality test is skipped when `SDA_INTEGRATION` is unset.

- [ ] **Step 4: Run the configured live retrieval-quality regression**

Run against the existing read-only Neo4j configuration:

```powershell
$env:SDA_INTEGRATION = "1"
python -m pytest tests/test_retrieval_quality.py::test_live_vector_and_hybrid_quality -q -s
Remove-Item Env:SDA_INTEGRATION
```

Expected: Recall@1, Recall@5 and MRR@5 remain at the current baseline because candidate ranking is unchanged.

- [ ] **Step 5: Run a local-code read-only behavioral smoke test**

Execute the modified local core against the configured Neo4j rather than the already-deployed MCP process, which will not contain the local change until a later deployment:

```powershell
python -c "from sda_mcp.skills.retrieving_context import search; a=search('用户满意评分'); b=search('用户满意评分', context_mode='none'); u=next(x for x in a['results'] if x['label']=='维度组' and x['properties'].get('维度组名称')=='用户'); bucket=u['context']['指标']; assert bucket=={'items': [], 'total': 49, 'truncated': True, 'omitted_reason': 'high_cardinality'}; assert all(x['context']=={} for x in b['results']); print('read-only smoke passed')"
```

Expected: `read-only smoke passed`. The command performs search only; it does not run sync, Cypher writes, report operations or paid image generation.
