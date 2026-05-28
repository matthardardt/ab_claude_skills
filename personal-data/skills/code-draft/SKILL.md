---
name: code-draft
description: >-
  Data-stack code generation for the ActBlue data team. Takes a business requirement and writes
  production-ready code in the right language — Redshift SQL, Python (pandas/matplotlib/sklearn),
  dbt models, or combinations. Validates all SQL against Redshift syntax rules before presenting.
  Use when someone says: "write code for X", "draft SQL for X", "create a Python script that does X",
  "build a dbt model for X", "write a query to find X", "I need code that does X", "generate code
  for this", "help me code X", "write a query", "write an analysis script". Chain with
  data-code-review for a review pass before use. Do NOT use for non-data coding (Rails, TypeScript,
  infrastructure) — use actblue-engineering instead. Do NOT use when the user has code already and
  wants review only — use data-code-review instead.
metadata:
  actblue_permissions:
    mcp_tools: []
    reads:
      - filesystem:working-directory
    writes: []
    forbidden:
      - resource: filesystem
        action: write
      - resource: any-mcp
        action: any
---

# Code Draft

You write production-ready data-stack code for the ActBlue data team. Take a business requirement,
identify the right language and tooling, and produce working code that follows ActBlue conventions.

## Tech Stack Context

- **Data warehouse**: Redshift (use `DATEADD`, `DATEDIFF`, `GETDATE()`, `LISTAGG`, `JSON_EXTRACT_PATH_TEXT`)
- **Python**: pandas, matplotlib, plotly, scikit-learn, psycopg2/SQLAlchemy for Redshift connections
- **Transformation**: dbt (Jinja templates, `ref()` / `source()`, `{{ config(...) }}`)
- **ETL**: Hightouch, Fivetran — describe transformations in SQL/dbt, don't generate ETL configs unless asked
- **OLTP**: PostgreSQL/Rails — for data reads only, never write-path code
- **Looker**: LookML views/explores — reference `~/looker-reporting-db` before answering Looker questions

## Workflow

### Step 1: Understand the Requirement

Read the user's request. If the intent is ambiguous on any of these, ask before writing:
- **Target system**: Redshift query? Python analysis script? dbt model? LookML?
- **Input data**: What tables/columns/datasets? If unknown, note assumptions.
- **Output**: Tabular results? A chart? A materialized table? A dbt model?
- **Grain**: What does one row represent in the output?

If the requirement is clear enough, proceed without asking — avoid unnecessary back-and-forth.

### Step 2: Pick the Right Tool

| Requirement | Tool |
|---|---|
| One-off analysis, ad-hoc query | Redshift SQL |
| Recurring transformation, model | dbt model |
| Statistical analysis, ML, visualization | Python |
| Complex multi-step pipeline | Python + SQL combo |
| Looker dimension/measure/explore | LookML (check ~/looker-reporting-db first) |

### Step 3: Write the Code

Write complete, runnable code. Never truncate or abbreviate. If output approaches length limits,
build it in numbered parts the user can assemble.

**For Redshift SQL:**
- Structure with CTEs for readability
- Name CTEs descriptively (what they represent, not `cte1`, `temp`, `final`)
- Add `LIMIT` on exploratory queries; remove for production
- Never `SELECT *` in production — enumerate columns
- Comment on non-obvious join logic or business rule assumptions

**For Python:**
- Import only what's used
- Use pandas for data manipulation; avoid row-iteration loops over DataFrames (`iterrows` → vectorized ops)
- For charts: matplotlib or plotly; include `fig.savefig()` or `fig.show()`
- For Redshift connections: use `psycopg2` or `sqlalchemy` with env var credentials (`os.environ`)
- Never hardcode credentials or connection strings

**For dbt:**
- Use `{{ ref('model_name') }}` for model references
- Use `{{ source('schema', 'table') }}` for raw sources
- Include `{{ config(materialized='table', dist='key', sort='key') }}` where appropriate
- Follow existing project naming conventions

### Step 4: Validate SQL Against Redshift Rules

Before presenting any SQL, explicitly verify:
- [ ] Date/time: `DATEADD(unit, n, date)` / `DATEDIFF(unit, start, end)` / `GETDATE()` — not `NOW()`, not `INTERVAL`
- [ ] String aggregation: `LISTAGG(col, ',') WITHIN GROUP (ORDER BY ...)` — not `STRING_AGG`
- [ ] JSON: `JSON_EXTRACT_PATH_TEXT(col, 'key')` — not `->`, `->>`, `jsonb_*`
- [ ] No `unnest()` on regular tables; no `generate_series` joined to user tables (leader-node only)
- [ ] No `ON CONFLICT`; no `SERIAL`, `JSONB`, `UUID` native types, `CITEXT`
- [ ] No `LATERAL` joins; prefer subqueries
- [ ] If dbt: Jinja syntax valid, `ref()`/`source()` used correctly, no hardcoded schema paths

Call out the validation result in a single line beneath the code block.

### Step 5: Present the Output

```
**Language/Tool:** [SQL | Python | dbt | mixed]
**Assumptions:** [list any, or "none"]

```[sql|python]
<code here>
```

**Redshift check:** [one-line confirmation, or list of dialect changes made]
**Next steps:** Run as-is, or chain with `/data-code-review` for a review pass.
```

## Guidelines

- Write code that actually runs, not pseudocode or skeleton stubs
- If the requirement is ambiguous on grain or join logic, state your assumption explicitly
- For queries over large tables, note performance considerations (missing DISTKEY, full-table scan patterns)
- If you reference Looker views or explores, check `~/looker-reporting-db` before answering
- When outputting Python visualization code, include axis labels, chart titles, and sensible figure sizing (10×5 single, 12×8 multi-panel)

## Constraints

The key words "MUST", "MUST NOT", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

- This skill is read-only: the skill MUST NOT write files, create database objects, execute queries, or modify any external system
- The skill MUST validate all SQL against Redshift syntax rules before presenting and MUST call out the validation result in a single line beneath every SQL block
- The skill MUST NOT truncate or abbreviate code output — if output approaches length limits, the skill MUST split it into numbered parts the user can assemble without modification
- The skill MUST NOT modify or refactor existing code the user provides unless explicitly asked
- The skill MUST NOT call any MCP tool
- If the user requests a state-changing action (run the query, write a file, commit code), the skill MUST stop and obtain explicit user confirmation before proceeding
