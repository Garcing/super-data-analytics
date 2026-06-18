# fetching-data-via-sql Design

Date: 2026-05-10

## Summary

Node.js skill for querying Hologres (PostgreSQL-compatible) databases. Follows the same pattern as `fetching-data-via-powerbi`: single-file library + CLI, file-driven workflow, cache auto-deletion.

## File Structure

```
fetching-data-via-sql/
  .env                        # HOLOGRES_HOST / PORT / DATABASE / USER / PASSWORD
  .gitignore                  # node_modules/, .env, cache/
  package.json                # name: sql-query, type: module, dep: pg
  sql-query.js                # Single file: HologresClient class + CLI
  SKILL.md                    # Skill definition for AI agent
  cache/                      # .sql request files, auto-deleted after execution
  templates/
    style.sql                 # SQL writing style guide (to be created)
  references/
    get_table_schema.sql      # Existing: table schema extraction query
  tests/
    sql-query.test.js         # Unit tests
```

## CLI Commands

| Command | Purpose |
|---------|---------|
| `node sql-query.js test-connection` | Verify database connectivity |
| `node sql-query.js schema <tableName> [--schema <schemaName>]` | Get table structure (wraps get_table_schema.sql) |
| `node sql-query.js query --file <path> [--keep] [--save <output>]` | Execute .sql file |

### query Command Flags

- `--file <path>` (required): Path to the .sql file to execute
- `--keep`: Preserve the .sql file in cache/ after execution. Without this flag, files inside cache/ are auto-deleted
- `--save <output>`: Save query results to file. Format determined by extension:
  - `.xlsx` → Excel (requires `xlsx` dependency)
  - `.csv` → CSV
  - `.json` → JSON
  - Omitting `--save` outputs JSON to stdout only

### schema Command

Wraps `references/get_table_schema.sql`, replacing `'schema_name'` and `'table_name'` placeholders. Outputs structured JSON with columns: 序号, 字段名, 数据类型, 默认值, 是否允许为空, 是否为主键, 字段注释.

## HologresClient Class

```js
class HologresClient {
  constructor()        // Read .env, create pg.Pool
  async testConnection()                    // Test connectivity
  async getTableSchema(tableName, schema?)  // Wrap get_table_schema.sql
  async query(sql)                          // Execute SQL, return { columns, rows }
  async close()                             // Close pool
}
```

All methods are async. Constructor reads `HOLOGRES_HOST`, `HOLOGRES_PORT`, `HOLOGRES_DATABASE`, `HOLOGRES_USER`, `HOLOGRES_PASSWORD` from environment (loaded via .env file walker, same pattern as via-powerbi).

## .env Configuration

```env
HOLOGRES_HOST=xxx.hologres.aliyuncs.com
HOLOGRES_PORT=80
HOLOGRES_DATABASE=your_db
HOLOGRES_USER=access_id
HOLOGRES_PASSWORD=access_key
```

## Dependencies

- `pg` — PostgreSQL driver (connects to Hologres via PostgreSQL protocol)
- `xlsx` — Excel file generation (needed only when `--save xxx.xlsx` is used)

## Cache Behavior

- SQL files placed in `cache/` are deleted after successful query execution
- `--keep` flag prevents deletion
- Files outside `cache/` are never auto-deleted
- Naming convention: `request-YYYYMMDD-HHMMSS-<random>.sql`

## SKILL.md Workflow

1. **Schema discovery**: `node sql-query.js schema <table>` to understand table structure
2. **SQL generation**: AI writes SQL based on table schema + user need, saves to `cache/`
3. **Execution**: `node sql-query.js query --file cache/xxx.sql [--save output.xlsx]`
4. Results default to stdout JSON; `--save` persists to file

## Constraints

- Only Hologres/PostgreSQL supported initially; other databases added as needed
- Tables must be pre-provided to the skill — no auto-discovery of relevant tables
- Single-file architecture matching via-powerbi pattern
