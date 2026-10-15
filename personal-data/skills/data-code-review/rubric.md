# Data Code Review Rubric — single source of truth

Loaded by BOTH the `data-code-review` skill and the `data-code-reviewer` agent. Edit here only;
never fork a second checklist. (Review-quality history: the two copies drifted within 20 days
of the 2026-06-16 catalog wiring — that is why this file exists.)

## Grading

| Grade | Meaning |
|---|---|
| **Blocker** | Will produce wrong results, fail to run, or create a security/data-quality problem. Must be fixed before use. |
| **Warning** | Likely to cause problems at scale, with edge-case data, or in production. Should fix before shipping. |
| **Suggestion** | Style, readability, or performance improvement. Take it or leave it. |

Rules: only genuine functional errors may be Blockers; style is always a Suggestion (user's
standing code rules). Every finding carries a grade, a location (`file:line`, CTE name, function),
why it matters, and a concrete fix. Never soften a Blocker to a Warning. No praise padding.

**Verdict** (both components use the same labels): `approve` (zero Blockers, zero material
Warnings) / `approve-with-warnings` (zero Blockers) / `block` (any Blocker).

## 1. Correctness pass (Blockers if wrong)

- Join grain: can any join fan out rows and inflate downstream aggregates? Show the concrete
  scenario ("a donor with 3 contributions produces 3 rows in this CTE, inflating SUM 3×")
- Aggregations at the right grain, before vs. after joins
- CASE branches covering all rows incl. NULLs; NULL handling in filters and join keys
  (`!=` silently excluding NULLs)
- Date boundaries inclusive vs. exclusive (BETWEEN vs >=/<); partial-period leakage
- Implicit INNER JOIN silently dropping rows; division-by-zero; window frame defaults
- Window PARTITION BY / ORDER BY correct for the intended calculation

## 2. Redshift dialect pass (Blockers if wrong)

- `dateadd`/`datediff` positional units — no Postgres `interval` math, no `now()`
- `listagg ... within group` not `string_agg`; `json_extract_path_text` not `->`/`->>`
- `median` / `percentile_cont` / `listagg` cannot share a query with ANY `count(distinct …)`
  (runtime ERROR), and only one inverse-distribution ordering per query — Blocker; fix with
  separate passes joined back, or long format
- No `unnest()` on tables; no `generate_series` joined to user tables (leader-node only)
- No LATERAL; `qualify` only when certain, else window-in-subquery
- No `ON CONFLICT`, `SERIAL`, native `JSONB`/`UUID`, `CITEXT`
- No correlated subqueries in SELECT — rewrite as JOIN/CTE
- `SELECT *`: Warning in ad-hoc analysis, Blocker in a materialized model

## 3. ActBlue domain pass

Resolve what the code CLAIMS to compute against the semantic catalog
(`~/.claude/actblue-semantic-catalog/bin/catalog metric|filter|table|join <x>`) and flag drift;
read `~/.claude/actblue-data-dictionary.md` for nuance ("Hard rules", "Refunds, chargebacks,
disputes", "Known bugs, traps & deprecations" — locate sections by heading text, never by number).

**Precedence (do not invert this):** the prose dictionary's `[validated]` facts OUTRANK the
catalog — the catalog is a regenerated projection and may be stale. Divergence from the catalog
that is backed by a dictionary `[validated]` fact is JUSTIFIED: grade it a Suggestion to fix the
catalog entry, never a Blocker. Catalog divergence is a Blocker only when the dictionary agrees
with the catalog or is silent.

- Counting key: contributions = `count(distinct contribution_sequence)`; flag `contribution_id`
  counts presented as "contributions"
- Tips excluded where the metric requires it (not for published sitewide toplines, which
  include tips). `is_tip` is never NULL in joined_lineitems; on raw `indigo_aurora` a bare
  `is_tip = false` drops tips-unknown rows. Internal entities excluded via `is_actblue_entity is
  true` where relevant — flag any hardcoded 33605/26969 list as stale
- Canonical real-donations filter present, or its absence justified
- ACH analysis gated on `paid_at >= '2026-04-20'` (legacy-ACH trap)
- Cents vs dollars (`extended_lineitems.amount` is cents; `istip` there is a string)
- Refund convention matched to purpose: live (`is_paid`) vs published
  (`refund_id is null or refunded_<period> > paid_<period>`)
- Timezone: indigo timestamps are US Eastern wall-clock — ANY conversion of them is a Blocker:
  `convert_timezone(…)` in 2- or 3-arg form (2-arg assumes a UTC source), `at time zone`, or
  `dateadd(hour, ±4/5, …)` offsets. Mixpanel `time` IS epoch UTC
- Literal enum values and columns: check `catalog dimension <x>` / `catalog table <x>` — values
  are case-sensitive (e.g. `entity_disbursement_type` is 'Conduit' / 'Merchant Account'; a
  lowercase filter returns 0 rows), and columns marked LOOKML-DERIVED don't exist in the warehouse
- Unfiltered Spectrum scans on `production_*` tables (Warning; Blocker in anything recurring)
- Demographic joins via `md5(lower(email))`

## 4. dbt pass

- `ref()` for all model references (no hardcoded `schema.table`) — Blocker
- `source()` for all raw sources — Blocker (`indigo_cdc` exists as a source NAME only)
- `{{ config(...) }}` present/correct for materialization — Warning if missing
- Jinja balanced and valid — Blocker if malformed; follows project conventions

## 5. Python (data/analytics) pass

- Logic correct for all input shapes (empty DataFrame, single row, NaN-heavy column) — Blocker
- merge/join `how=` preserving/dropping rows as intended; groupby at the right grain — Blocker
- Timezone-aware datetime handling where needed; index-alignment traps
- Hardcoded credentials/secrets — Blocker
- Performance (Warnings): `iterrows` → vectorize; `apply` where native ops exist; unchunked
  large reads; merge chains better done in SQL
- Visualization (Suggestions): titles/axis labels/units, figure sizing, accessible palettes

## 6. LookML pass

- Heavy logic or anything that must be GROUP BY-able → dimension, not a table calc — Blocker
  if a calc can't support the stated use
- Expression syntax: `case()` has NO else (last positional arg is fallback); `date(y,m,d)`
  3-arg; `diff_days()`/`add_days()` not date arithmetic; `pivot_index(${m}, i)` never
  `${m}[Yes]`; `min()`/`max()` are column-wise — `if()` for scalar compares
- `sql:` blocks are Redshift — apply pass 2 to them
- Joins/fan-out (Blocker): every view in a joined explore declares `primary_key: yes`; each
  join's `relationship:` matches the real cardinality (check the grain in the catalog /
  dictionary); measures on the "one" side of a fanning join must be symmetric-aggregate safe
  (PK present, or `sum_distinct`/`average_distinct` with `sql_distinct_key`)
- Table-calc Totals: the Totals/Row Totals cell re-applies the calc to the totals row, it does
  not sum the column — a nonlinear calc (cap, ratio, `if`) shows a silently wrong total. Blocker
  if that total is consumed; fix with a LookML measure or custom dimension + Aggregate→Sum
- New explore joins carry a `fields:` allowlist — Warning
- Business filters at the viz/filter level, not baked into calcs/dimensions (user preference)

## 7. Style pass (Suggestions only)

`~/analytics/.sqlfluff` house style: lowercase, leading commas, 4-space indent, max line 160,
descriptive CTE names.
- Unindented CTE bodies — Suggestion. `indented_ctes = False` keeps CTE names at column 0, but
  the body inside the parentheses is indented 4 spaces.
- CTE sprawl — Suggestion (Warning if it forces repeated scans of a large/Spectrum table): separate
  CTEs per metric or per segment over the same source/grain that could be one pass with flags or
  conditional aggregates, or `_by_segment` CTEs joined back instead of splitting in the final select.
- Unnecessary aliasing — table aliases or column renames where SQL doesn't require one (required:
  derived tables, self-joins/same table twice, name collisions, computed columns) — Suggestion.
  Any alias that is used: `as`, ≥4 chars.
- Verbose inline comments (restating the code, banners, narration) — Suggestion. Keep only short
  comments on the non-obvious why.
