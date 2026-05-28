---
name: write-query
description: >-
  Write an optimized SQL QUERY to pull or analyze data, grounded in the ActBlue data team's REAL
  warehouse tables/views. Default dialect Redshift. ALWAYS discovers actual table/column names from
  the local analytics repo before writing — never invents schema or leaves placeholder table names —
  and writes in the team's .sqlfluff style. Use when someone says: "write a query", "write/build me a
  query", "write SQL to find/pull X", "query our donations/contributions/refunds", "donation trends",
  "pull X from the warehouse", "a query to analyze X", "/write-query". This is the owner for
  read/analysis SQL (SELECT) against the warehouse. Do NOT use for generating Python scripts, dbt
  models, or multi-language code artifacts — use code-draft. Do NOT use to review existing code —
  use data-code-review.
metadata:
  actblue_permissions:
    mcp_tools: []
    reads:
      - filesystem:working-directory
      - filesystem:~/analytics
      - filesystem:~/looker-reporting-db
    writes: []
    forbidden:
      - resource: filesystem
        action: write
      - resource: any-mcp
        action: any
---

# /write-query - Write Optimized SQL

> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).

Write a SQL query from a natural language description, optimized for your specific SQL dialect and
following best practices. For the ActBlue data team the dialect is **Redshift** unless stated otherwise.

## Usage

```
/write-query <description of what data you need>
```

## Workflow

### 1. Understand the Request

Parse the user's description to identify:

- **Output columns**: What fields should the result include?
- **Filters**: What conditions limit the data (time ranges, segments, statuses)?
- **Aggregations**: Are there GROUP BY operations, counts, sums, averages?
- **Joins**: Does this require combining multiple tables?
- **Ordering**: How should results be sorted?
- **Limits**: Is there a top-N or sample requirement?

### 2. Determine SQL Dialect

Default to **Redshift** (Amazon) for ActBlue warehouse work. Only ask if the user signals a different
target. Other supported dialects, if asked:

- **PostgreSQL** (including Aurora, RDS, Supabase, Neon)
- **Snowflake**
- **BigQuery** (Google Cloud)
- **Redshift** (Amazon) — *default for ActBlue*
- **Databricks SQL**
- **MySQL** (including Aurora MySQL, PlanetScale)
- **SQL Server** (Microsoft)
- **DuckDB**
- **SQLite**
- **Other** (ask for specifics)

Remember the dialect for future queries in the same session.

### 3. Discover Schema — ground in the real ActBlue warehouse FIRST (do not invent tables)

Before writing any SQL, discover real table/column names from the team's local analytics repo at
**`/Users/mhardardt/analytics`** (GitHub `actblue/analytics`). It is NOT a dbt project — it's the
team's ad-hoc SQL repo — but its `.sql` files reference the real Redshift tables/views and show how
the team filters and queries them. For modeled Looker fields, also reference
**`/Users/mhardardt/looker-reporting-db`**.

```bash
# real tables/views used for a domain (donations, refunds, donors, ...)
cd ~/analytics && grep -rhioE '(from|join)[[:space:]]+[a-z0-9_."]+' --include='*.sql' . \
  | grep -ioE '[a-z0-9_]+\.[a-z0-9_]+' | sort | uniq -c | sort -rn

# real columns + canonical filters on a chosen table
cd ~/analytics && grep -rhioE '<table>\.[a-z0-9_]+' --include='*.sql' . | sort | uniq -c | sort -rn
```

Then read a representative `.sql` file that uses the chosen table to confirm columns and the team's
standard filter pattern. Only ask the user for table names if the domain genuinely isn't in the repo.

**Known canonical objects** (verify against the repo each time — schema drifts):

- `production_core_tables.joined_lineitems` — **transaction/payment grain** (one row per paid
  lineitem); best table for donation volume/$ trends. Cols: `paid_at`, `amount_dollars`, `is_paid`,
  `is_tip`, `is_refunded`, `refunded_at`, `refund_id`, `is_recurring`, `recurrence_number`,
  `contribution_sequence`, `donor_email`, `entity_id`, `cycle`, `contribution_id`, `payment_method`.
- `production_core_tables.agg_contributions` — one row per contribution (contribution-level detail).
- `production_base_indigo.base_indigo__contributions` / `base_indigo__first_time_donations` — base models.
- `production_core_views.joined_refunds` / `joined_bulk_refunds` — refund detail.
- Raw sources: `indigo_cdc.*` and `indigo_aurora.*` (`contributions`, `payment_sources`, `payment_transactions`).

**Canonical "real donations" filter:** `is_paid is true and is_tip is false and is_refunded is false`.
Variant that keeps donations valid-at-the-time even if later refunded:
`(is_refunded is false or refunded_at::date > <period_end>)`.

If a data warehouse MCP server is also connected, supplement the repo discovery with:

1. Search for relevant tables based on the user's description
2. Inspect column names, types, and relationships
3. Check for partitioning or clustering keys that affect performance
4. Look for pre-built views or materialized views that might simplify the query

### 4. Write the Query

Follow these best practices:

**Structure:**
- Use CTEs (WITH clauses) for readability when queries have multiple logical steps
- One CTE per logical transformation or data source
- Name CTEs descriptively (e.g., `daily_signups`, `active_users`, `revenue_by_product`)

**Performance:**
- Never use `SELECT *` in production queries -- specify only needed columns
- Filter early (push WHERE clauses as close to the base tables as possible)
- Use partition filters when available (especially date partitions)
- Prefer `EXISTS` over `IN` for subqueries with large result sets
- Use appropriate JOIN types (don't use LEFT JOIN when INNER JOIN is correct)
- Avoid correlated subqueries when a JOIN or window function works
- Be mindful of exploding joins (many-to-many)

**Readability:**
- Add comments explaining the "why" for non-obvious logic
- Use consistent indentation and formatting
- Alias tables with meaningful short names (not just `a`, `b`, `c`)
- Put each major clause on its own line

**Dialect-specific optimizations:**
- Apply dialect-specific syntax and functions (see `sql-queries` skill for details)
- Use dialect-appropriate date functions, string functions, and window syntax
- Note any dialect-specific performance features (e.g., Snowflake clustering, BigQuery partitioning)

**Redshift validation (default dialect — always check before presenting):**
- Dates: `dateadd(unit, n, date)` / `datediff(unit, a, b)` positional units, NOT Postgres `interval`
  math. Use `current_date` / `getdate()` / `sysdate`, not `now()`.
- JSON: `json_extract_path_text(col, 'key')` / `json_extract_array_element_text`; no `->`, `->>`, `#>`, `jsonb_*`.
- String agg: `listagg(col, ',') within group (order by ...)`, not `string_agg`.
- `generate_series` is leader-node only — won't join to user tables; use a numbers table / recursive CTE.
- Window functions in a CTE rather than relying on `qualify` when there's any doubt.
- DDL: respect `distkey` / `sortkey` / `encode` / `varchar(n)`; no `serial`, native `jsonb`/`uuid`, `citext`.
- If porting from another dialect, port explicitly and note what changed.

**House style** (from `/Users/mhardardt/analytics/.sqlfluff`): lowercase keywords/identifiers/functions/
types, **leading commas**, explicit table + column aliases (min length 4), 4-space indent, CTEs not
indented, `max_line_length = 160`.

### 5. Present the Query

Provide:

1. **The complete query** in a SQL code block with syntax highlighting
2. **Brief explanation** of what each CTE or section does
3. **A one-line Redshift-compliance note** confirming the syntax rules above were checked
4. **Performance notes** if relevant (expected cost, partition usage, potential bottlenecks)
5. **Modification suggestions** -- how to adjust for common variations (different time range, different granularity, additional filters, gross vs net-of-refunds)

### 6. Offer to Execute

If a data warehouse is connected, offer to run the query and analyze the results. If the user wants to
run it themselves, the query is ready to copy-paste. Offer to adapt it into a dbt model
(`ref()` / `source()` / `{{ config() }}`) if it's destined for the analytics repo.

## Examples

**Simple aggregation:**
```
/write-query Count of orders by status for the last 30 days
```

**Complex analysis:**
```
/write-query Cohort retention analysis -- group users by their signup month, then show what percentage are still active (had at least one event) at 1, 3, 6, and 12 months after signup
```

**Performance-critical:**
```
/write-query We have a 500M row events table partitioned by date. Find the top 100 users by event count in the last 7 days with their most recent event type.
```

## Tips

- Mention your SQL dialect upfront to get the right syntax immediately (defaults to Redshift)
- If you know the table names, include them -- otherwise the schema is discovered from `~/analytics`
- Specify if you need the query to be idempotent (safe to re-run) or one-time
- For recurring queries, mention if it should be parameterized for date ranges
