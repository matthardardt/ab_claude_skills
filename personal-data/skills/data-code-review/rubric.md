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
- No `unnest()` on tables; no `generate_series` joined to user tables (leader-node only)
- No LATERAL; `qualify` only when certain, else window-in-subquery
- No `ON CONFLICT`, `SERIAL`, native `JSONB`/`UUID`, `CITEXT`
- No correlated subqueries in SELECT — rewrite as JOIN/CTE
- `SELECT *`: Warning in ad-hoc analysis, Blocker in a materialized model

## 3. ActBlue domain pass

Resolve what the code CLAIMS to compute against the semantic catalog
(`~/.claude/actblue-semantic-catalog/bin/catalog metric|filter|table|join <x>`) and flag drift;
read `~/.claude/actblue-data-dictionary.md` for nuance (§ hard rules, refund conventions,
known traps — locate sections by heading text, not only by number).

**Precedence (do not invert this):** the prose dictionary's `[validated]` facts OUTRANK the
catalog — the catalog is a regenerated projection and may be stale. Divergence from the catalog
that is backed by a dictionary `[validated]` fact is JUSTIFIED: grade it a Suggestion to fix the
catalog entry, never a Blocker. Catalog divergence is a Blocker only when the dictionary agrees
with the catalog or is silent.

- Counting key: contributions = `count(distinct contribution_sequence)`; flag `contribution_id`
  counts presented as "contributions"
- Tips excluded where the metric requires it — and note `is_tip` is NULLable: bare
  `is_tip = false` drops tips-unknown rows; `(is_tip is false or is_tip is null)` when they
  should count. Internal tip entities 33605/26969 excluded where relevant
- Canonical real-donations filter present, or its absence justified
- ACH analysis gated on `paid_at >= '2026-04-20'` (legacy-ACH trap)
- Cents vs dollars (`extended_lineitems.amount` is cents; `istip` there is a string)
- Refund convention matched to purpose: live (`is_paid`) vs published
  (`refund_id is null or refunded_<period> > paid_<period>`)
- Timezone: indigo timestamps are US Eastern wall-clock — any `convert_timezone('UTC', …)`
  on them is a Blocker; Mixpanel `time` IS epoch UTC
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
- New explore joins carry a `fields:` allowlist — Warning
- Business filters at the viz/filter level, not baked into calcs/dimensions (user preference)

## 7. Style pass (Suggestions only)

`~/analytics/.sqlfluff` house style: lowercase, leading commas, explicit aliases ≥4 chars,
4-space indent, CTEs not indented, max line 160, descriptive CTE names.
