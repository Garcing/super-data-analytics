# SQL Query Source Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy SQL query flags with explicit `stdin`, `file`, and `inline` source routing, deterministic result artifacts, and safe SQL-file retention rules.

**Architecture:** Keep the existing single-file CLI, but separate argument parsing, SQL source loading, result-envelope construction, result persistence, and cache cleanup into exported functions that can be tested without a database. The CLI composes these functions and guarantees JSON-only stdout on success and stderr-only errors on failure.

**Tech Stack:** Node.js 18+, ESM, `node:test`, `pg`, optional `xlsx`

---

### Task 1: Define the new CLI contract with failing tests

**Files:**
- Modify: `querying-via-sql/scripts/sql-query.test.js`

- [ ] **Step 1: Replace legacy parser expectations with source-specific cases**

Add tests that call `parseQueryArgs()` with `--source stdin`, `--source file --sql-path`, and `--source inline --sql`, asserting normalized objects containing `source`, `sql`, `sqlPath`, `savePath`, `retainSql`, and `traceId`.

- [ ] **Step 2: Add validation tests**

Use `assert.throws()` for missing source values, source/argument conflicts, legacy `--file` and `--stdin`, multiline inline SQL, inline SQL over 500 characters, and unsafe trace IDs.

- [ ] **Step 3: Run the parser tests and verify RED**

Run:

```powershell
node --test querying-via-sql/scripts/sql-query.test.js
```

Expected: failures showing that `--source`, `--sql-path`, `--sql`, `--retain-sql`, and `--trace-id` are not implemented.

### Task 2: Implement source parsing and SQL loading

**Files:**
- Modify: `querying-via-sql/scripts/sql-query.js`
- Test: `querying-via-sql/scripts/sql-query.test.js`

- [ ] **Step 1: Implement strict argument parsing**

Parse the six new flags, reject unknown and duplicate flags, validate the source matrix, cap inline SQL at 500 characters, reject inline newlines, and validate trace IDs with `/^[A-Za-z0-9._-]+$/`.

- [ ] **Step 2: Implement source loading**

Keep UTF-8 stdin and file readers, add inline SQL loading, and expose one `readSqlSource(options, stream)` dispatcher.

- [ ] **Step 3: Run tests and verify GREEN**

Run the same `node --test` command. Expected: parser and source-reader tests pass.

### Task 3: Define result paths, envelopes, persistence, and cleanup with failing tests

**Files:**
- Modify: `querying-via-sql/scripts/sql-query.test.js`

- [ ] **Step 1: Add result-path and envelope tests**

Assert that omitted trace IDs become UUIDs, default paths are absolute paths under `querying-via-sql/.cache`, explicit save paths resolve from `process.cwd()`, and envelopes include `trace_id`, `source`, `result_path`, `row_count`, `columns`, and `rows`.

- [ ] **Step 2: Add persistence tests**

Use a temporary directory to verify JSON envelopes, CSV rows, directory creation, unsupported extensions, and cleanup decisions for internal cache files, retained files, external files, and failed executions.

- [ ] **Step 3: Run tests and verify RED**

Expected: failures for missing path, envelope, persistence, and cleanup helpers.

### Task 4: Implement result handling and integrate the CLI

**Files:**
- Modify: `querying-via-sql/scripts/sql-query.js`
- Test: `querying-via-sql/scripts/sql-query.test.js`

- [ ] **Step 1: Add result helpers**

Use `crypto.randomUUID()`, `mkdirSync(..., { recursive: true })`, absolute path normalization, and extension-based persistence. JSON writes the complete envelope; CSV and XLSX write tabular data.

- [ ] **Step 2: Add safe cleanup logic**

Delete a successful file source only when its resolved path is inside `querying-via-sql/.cache` and `--retain-sql` is absent. Never delete external or failed inputs.

- [ ] **Step 3: Integrate query execution**

Create the client after argument parsing, load SQL according to source, query, persist the result, emit exactly one JSON envelope to stdout, and close the client in `finally`. Remove `KEEP_SQL_FILE`, `KEEP_SQL_RESULT`, their helper, and legacy result-path logic.

- [ ] **Step 4: Run tests and verify GREEN**

Expected: all unit tests pass with no warnings.

### Task 5: Update the Agent routing contract and cache ignore rules

**Files:**
- Modify: `.gitignore`
- Modify: `querying-via-sql/SKILL.md`
- Modify: `querying-via-sql/README.md`

- [ ] **Step 1: Ignore runtime cache**

Add `querying-via-sql/.cache/` without deleting or modifying the legacy `cache/` contents.

- [ ] **Step 2: Document the breaking CLI**

Replace old examples with the three `--source` forms, document default result saving, custom formats, trace IDs, and internal/external file retention.

- [ ] **Step 3: Document the Agent routing table**

Require process-API stdin when available, file source for reviewable or Shell-only execution, quoted Bash heredoc when explicitly avoiding files, and inline only for short single-line SQL without Shell-sensitive or user-provided values. Explicitly prohibit double-quoted `echo` SQL.

### Task 6: Verify unit and live behavior

**Files:**
- No code changes expected

- [ ] **Step 1: Run the complete unit suite**

```powershell
node --test querying-via-sql/scripts/sql-query.test.js
```

Expected: all tests pass.

- [ ] **Step 2: Run inline integration**

```powershell
node querying-via-sql/scripts/sql-query.js query --source inline --sql "SELECT 1 AS test"
```

Expected: stdout is one JSON envelope and its `result_path` exists under `.cache`.

- [ ] **Step 3: Run stdin integration through a safe file pipe**

Use an existing SQL cache file with `Get-Content -LiteralPath <path> -Raw | node ... query --source stdin`. Expected: Chinese values survive and a result artifact is created.

- [ ] **Step 4: Run file cleanup integration**

Copy an existing test SQL into `.cache`, execute with `--source file --sql-path`, verify success and deletion; repeat with `--retain-sql` and verify retention. Verify an external SQL file remains.

- [ ] **Step 5: Inspect the final diff**

Run `git diff --check` and `git status --short`. Confirm no legacy cache or unrelated user files changed.
