---
name: code-draft
description: >-
  Data-stack code generation for the ActBlue data team. Takes a business requirement and writes
  production-ready code ARTIFACTS in the right language — Python (pandas/matplotlib/sklearn), dbt
  models, analysis scripts, or multi-language combinations. Validates all SQL against Redshift syntax
  rules before presenting. Use when someone says: "write code for X", "create a Python script that
  does X", "build a dbt model for X", "I need code that does X", "generate code for this", "help me
  code X", "write an analysis script". Chain with data-code-review for a review pass before use.
  Do NOT use for writing a standalone SQL query to pull or analyze warehouse data ("write a query",
  "build me a query", "SQL to find X") — use analyze, which owns read/analysis SQL, grounds in the
  real warehouse schema, and executes against the warehouse. Do NOT use for non-data coding (Rails, TypeScript, infrastructure) — use
  actblue-engineering. Do NOT use when the user has code already and wants review only — use
  data-code-review.
metadata:
  actblue_permissions:
    mcp_tools: []
    reads:
      - filesystem:working-directory
      - filesystem:~/analytics
      - filesystem:~/looker-reporting-db
      - filesystem:~/.claude/actblue-data-dictionary.md
      - filesystem:~/.claude/actblue-data-dictionary-sources
      - filesystem:~/.claude/actblue-semantic-catalog
    writes:
      - filesystem:working-directory
    forbidden:
      - resource: filesystem-outside-working-directory
        action: write
      - resource: warehouse
        action: any (drafting only — execution belongs to analyze)
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
- **ActBlue semantics**: before writing warehouse-touching code, resolve exact definitions from the
  semantic catalog — `~/.claude/actblue-semantic-catalog/bin/catalog metric|table|join|filter|column <x>`
  (structured). Metric SQL you emit MUST match `catalog metric <name>`, and required filters come from
  `catalog filter <name>`. Read `~/.claude/actblue-data-dictionary.md` for narrative/nuance (grains,
  counting keys, ET timestamps, refund conventions, fees, traps); deep extracts in
  `~/.claude/actblue-data-dictionary-sources/`

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
| Standalone read/analysis query | **STOP — hand off to `/analyze`** (it grounds in real schema and executes). Redshift SQL appears in this skill only embedded inside a Python/dbt artifact |
| Recurring transformation, model | dbt model |
| Statistical analysis, ML, visualization | Python |
| Complex multi-step pipeline | Python + SQL combo |
| Looker dimension/measure/explore | LookML (check ~/looker-reporting-db first) |

### Step 3: Write the Code

Write complete, runnable code. Never truncate or abbreviate. If output approaches length limits,
build it in numbered parts the user can assemble.

**For Redshift SQL:**
- Structure with CTEs for readability, but as few as possible: one pass per source/grain, related
  metrics as flags/conditional aggregates in the same CTE, segment splits in the final select; a new
  CTE only for a real grain change or reuse
- CTE names flush at column 0, CTE bodies indented 4 spaces inside the parentheses
- Name CTEs descriptively (what they represent, not `cte1`, `temp`, `final`)
- Add `LIMIT` on exploratory queries; remove for production
- Never `SELECT *` in production — enumerate columns
- No aliasing unless SQL requires it (derived tables, self-joins/same table twice, name collisions,
  computed columns); otherwise reference tables by name and keep column names as-is. When required: `as`, ≥4 chars
- Inline comments: as short as possible, only where needed (non-obvious join logic or business-rule
  assumption). No restating the code, no banners

**For Python:**
- Import only what's used
- Use pandas for data manipulation; avoid row-iteration loops over DataFrames (`iterrows` → vectorized ops)
- For charts: matplotlib or plotly; include `fig.savefig()` or `fig.show()`
- For Redshift connections: use `psycopg2` or `sqlalchemy` with env var credentials (`os.environ`)
- Never hardcode credentials or connection strings
- Inline comments: as short as possible, only where needed; no restating the code

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

- The skill MAY write requested artifact files inside the working directory (that IS the
  deliverable); it MUST NOT write outside the working directory, execute queries or generated
  code, create database objects, or modify any external system
- Every table, column, and join key in emitted warehouse SQL MUST resolve from
  `catalog table|column|join`, the dictionary-sources column extracts, or `~/analytics`; if
  unresolvable, the skill MUST mark it `/* UNVERIFIED: confirm table/column */` and list it
  under Assumptions — silently invented schema is not acceptable. On catalog-vs-dictionary
  conflict, the dictionary's `[validated]` fact wins
- The skill MUST validate all SQL against Redshift syntax rules before presenting and MUST call out the validation result in a single line beneath every SQL block
- The skill MUST NOT truncate or abbreviate code output — if output approaches length limits, the skill MUST split it into numbered parts the user can assemble without modification
- The skill MUST NOT modify or refactor existing code the user provides unless explicitly asked
- The skill MUST NOT call any MCP tool
- If the user requests running generated code, executing a query, or committing, the skill MUST stop and obtain explicit user confirmation before proceeding
- Generated artifacts are ActBlue work product destined for `actblue/*` repos or local use: the skill MUST NOT push them to any personal repository (`matthardardt/*`) or any destination outside the ActBlue ecosystem, and MUST NOT run `git push` to ANY remote without the user's express, confirmed permission in the current conversation
