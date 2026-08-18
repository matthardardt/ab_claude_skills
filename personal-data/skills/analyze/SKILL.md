---
name: analyze
description: >-
  END-TO-END data analysis against the live ActBlue Redshift warehouse: takes a business question,
  asks one upfront batch of clarifying questions, then autonomously discovers schema, writes and
  validates Redshift SQL, EXECUTES it read-only against the warehouse, QAs the results, and delivers
  findings with charts and an analysis brief — all with minimal further input. This is the OWNER for
  any DESCRIPTIVE ActBlue data question, ad-hoc pull, trend investigation, segment comparison, or
  "write a query" request — prefer it over generic data skills for anything touching the ActBlue
  warehouse. Use when someone says: "analyze X", "what's driving X", "pull X from the warehouse",
  "how many/much X", "donation trends", "compare X vs Y", "write a query for X", "investigate X",
  "answer this data question", "run the numbers on X", "/analyze". A descriptive anomaly check
  with no named cause ("is this spike real?", "is this number right?") is analyze's job. Do NOT
  use for causal questions with a named treatment/change ("did X work", impact of a rollout,
  cannibalization, A/B analysis, "is this effect real or selection") — use
  personal-data:experiment-design first, then chain back here for execution. Do NOT use to review
  existing code (use data-code-review), to generate Python/dbt artifacts without running an
  analysis (use code-draft), or to prep presentation Q&A (use exec-qa-prep — chain after this).
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
      - warehouse:redshift-read-only
    writes:
      - filesystem:working-directory
      - filesystem:~/.claude/analysis-registry.jsonl (append-only)
    forbidden:
      - resource: warehouse
        action: write
      - resource: any-mcp
        action: any
      - resource: filesystem-outside-working-directory
        action: write (sole exception — the append-only analysis registry)
---

# /analyze — End-to-End Warehouse Analysis

You own the entire analytic process: question → clarification → schema discovery → SQL →
execution → QA → insights → deliverable. The user gives you a business question and answers one
batch of guidance questions; after that you work autonomously to a finished, evidence-backed answer.

All warehouse access goes through the scripts at `~/.claude/bin/` (read-only enforced by the
shared `sql_guard.py` validator, statement timeout, output-path containment; installed by
`setup_env.sh` — if `~/.claude/bin/rs` is missing, run
`"${CLAUDE_PLUGIN_ROOT}/skills/analyze/scripts/setup_env.sh"` once):

```bash
RS=~/.claude/bin
"$RS/rs" ping                          # connectivity test (run first; failure usually = not on AB VPN)
"$RS/rs" find <pattern>                # search table/view names
"$RS/rs" cols <schema.table>           # columns + types
"$RS/rs" peek <schema.table>           # first 10 rows
"$RS/rs" sql "<query>"                 # table output, auto-LIMIT (RS_ROW_CAP, default 500)
"$RS/rs" explain "<query>"             # plan check before a big run
"$RS/rs" csv "<query>" out.csv         # full results to CSV (path must be inside the working dir)
"$RS/rs_query.py" --file q.sql -o out.csv          # LOCAL schemas only (svv_*, dbt_*) + automatic profile
"$RS/rs_query.py" --profile-csv out.csv --key <grain_col>   # profile any CSV: nulls, describe, fan-out check
```

**Pull routing (hard rule):** external/Spectrum schemas — `production_*`, `indigo_aurora`,
`mixpanel` — MUST be pulled with `rs csv`; `rs_query.py` opens a read-only session and Redshift
rejects external tables inside read-only transactions ("transaction is read-only"). After any
`rs csv` pull, get the profile with `rs_query.py --profile-csv <file> --key <grain_col>`.
`rs` handles leading comments and `;` inside comments correctly — `rs sql "$(cat file.sql)"` is fine.

Python for charts/stats: `~/.venvs/abdata/bin/python` (pandas, matplotlib, plotly, psycopg2,
scipy, sklearn, statsmodels). If the venv is missing, run `setup_env.sh` as above.

## Phase 0 — Intake and the One Question Batch

Parse the ask. If it contains a causal claim ("did X work", rollout impact, cannibalization),
stop and hand off to `/experiment-design` — do not run a descriptive pull on a causal question.

Determine what is genuinely ambiguous among:

1. **Time range** (and comparison period, if any)
2. **Population / filters** (e.g., gross vs net of refunds, tips in or out, which entity types)
3. **Grain / segmentation** (by day? by entity? by donor cohort?)
4. **Deliverable + audience** (quick numbers for you vs. brief for stakeholders vs. charts for a deck)

Ask ONLY the ambiguous ones, in a single `AskUserQuestion` batch (max 4 questions, with sensible
recommended defaults). If the ask is fully specified, skip straight to Phase 1. After this batch,
do not ask again — state assumptions inline and keep moving. Stop only if genuinely blocked
(connection down, table truly not findable, results so suspect the question can't be answered).

## Phase 1 — Open the state file, then discover

**First action for any multi-query analysis: create `./analysis_<slug>_<yyyymmdd>/` and start
`analysis.md` in it** — question, clarification answers, definitions and filters chosen (with
catalog citations), assumptions. Append to it as you work (queries run, QA results, findings).
This file is the analysis's memory: it must let a fresh session resume the work if this one is
compacted or dies. One-number quick asks may skip the folder (see Phase 6 ceremony scaling).

Ground in the REAL schema before writing any SQL — never invent table or column names.

- **Semantic catalog FIRST** (structured, deterministic lookup): the `catalog` helper resolves the
  exact definition of any metric/table/join/filter/term —
  `~/.claude/actblue-semantic-catalog/bin/catalog metric <name>` (canonical expression + required
  filter macros), `catalog table <key>` (grain/keys/columns/gotchas), `catalog filter <name>`,
  `catalog join <a> <b>`, `catalog column <key>.<col>`, `catalog grep <regex>`. Metric SQL you
  write MUST match `catalog metric <name>` (or state why not); required filters come via
  `catalog filter`. **Precedence:** if the catalog and the prose dictionary disagree, the
  dictionary's `[validated]` fact wins — use it and note the catalog needs fixing.
- **Data dictionary** (the narrative behind the catalog): `~/.claude/actblue-data-dictionary.md` —
  hard query rules, the two refund conventions, official metric definitions, nuance, and known traps,
  all confidence-tagged. Deep per-source extracts (incl. column dictionaries for 30 core tables) in
  `~/.claude/actblue-data-dictionary-sources/`. If the catalog lacks an object, grep these + the live
  catalog and treat the gap as a catalog TODO — never silently invent schema.
- **Repo conventions** (how the team actually queries the domain):
  ```bash
  cd ~/analytics && grep -rhioE '(from|join)[[:space:]]+[a-z0-9_."]+' --include='*.sql' . \
    | grep -ioE '[a-z0-9_]+\.[a-z0-9_]+' | sort | uniq -c | sort -rn | head -30
  cd ~/analytics && grep -rliE '<domain keyword>' --include='*.sql' . | head
  ```
  Then read 1-2 representative `.sql` files for the chosen tables to confirm canonical filters.
- **Live catalog** (ground truth): `rs find`, `rs cols`, `rs peek` on candidate tables; check actual
  date ranges with a quick `min/max` query when recency matters.
- **Looker** (`~/looker-reporting-db`) when the ask references a dashboard metric — match its definition.

For asks spanning 2+ domains, fan out parallel Explore subagents (one per domain) over `~/analytics`
and synthesize their table/filter findings; keep live catalog probes in the main context.

**Known canonical objects** (verify each time — schema drifts):
- Prefer `production_*` schemas — `rs find` also returns per-analyst dev copies
  (`dbt_<user>_core_tables.*`); those are SAMPLED — never conclude "no data" from them.
- `production_core_tables.joined_lineitems` — EXTERNAL (Spectrum) table at transaction/payment
  grain (one row per paid lineitem); best for donation volume/$ trends, but always filter —
  unfiltered scans are slow and costly. Key cols: `paid_at`, `amount_dollars`, `is_paid`, `is_tip`,
  `is_refunded`, `refunded_at`, `is_recurring`, `recurrence_number`, `contribution_sequence`,
  `donor_email`, `entity_id`, `cycle`, `contribution_id`, `payment_method`.
- `production_core_tables.agg_contributions` — one row per contribution.
- `production_base_indigo.base_indigo__contributions` / `base_indigo__first_time_donations`.
- `production_core_views.joined_refunds` / `joined_bulk_refunds` — refund detail.
- Raw source: `indigo_aurora.*` (`indigo_cdc` was dropped Apr 2025 — older queries referencing it
  need a schema swap; dbt docs still use it as a source NAME only).

**Canonical "real donations" filter:** resolve via `catalog filter real_donations`; the baseline is
`is_paid is true and is_tip is false and is_refunded is false` — note `is_tip` is NULLable: use
`(is_tip is false or is_tip is null)` when tips-unknown rows should count, and say which you chose.
Valid-at-the-time variant: `(is_refunded is false or refunded_at::date > <period_end>)`.

## Phase 2 — Write and Validate SQL, then pre-register expectations

House style (from `~/analytics/.sqlfluff`): lowercase everything, leading commas, explicit aliases
(min 4 chars), 4-space indent, CTEs not indented, max line 160. Descriptive CTE names.

Redshift checklist — verify before executing, note "Redshift check: passed" once per query set:
- `dateadd`/`datediff` positional units, `getdate()`/`current_date` — no `interval` math, no `now()`
- `listagg(...) within group (...)` not `string_agg`; `json_extract_path_text` not `->`/`->>`
- No `unnest()` on tables, no `generate_series` joined to user tables, no lateral joins
- Window functions in CTEs rather than `qualify` when in doubt

Correctness checklist (the data-code-review core — run it on your own SQL):
- Join grain: will any join fan out rows and inflate aggregates?
- Aggregations at the right grain, before vs. after joins
- NULL handling in CASE branches, filters, and joins
- Date boundaries inclusive vs. exclusive; timezone (indigo timestamps are US Eastern wall-clock —
  never `convert_timezone('UTC', …)` them; Mixpanel `time` IS epoch UTC)
- Implicit INNER JOIN behavior silently dropping rows

**Pre-register before executing** (into `analysis.md`, or one chat line for quick asks): the
expected grain (what one row is), expected row-count order of magnitude, and expected result
magnitude (dollars/counts, roughly). Phase 4 checks results against THESE, written down BEFORE
the numbers came back — not against post-hoc intuition.

## Phase 3 — Execute

1. `rs ping` once per session if connectivity is unproven.
2. `rs explain` on anything non-trivial (catches syntax + insane scan plans cheaply).
3. Shape-check with `rs sql` using an EXPLICIT small limit in the query (10-50 rows) — do not
   lean on the auto-cap for peeks; 500 wide rows of table output floods the context.
4. Full pull: external schemas (`production_*`, `indigo_aurora`, `mixpanel`) → `rs csv` then
   `rs_query.py --profile-csv <file> --key <grain_col>`; local objects → `rs_query.py --file`.
5. Append every executed query to the output directory as a numbered `.sql` file as you go
   (not at the end) so the analysis survives compaction and is reproducible.

## Phase 4 — QA gates (before believing them)

These are GATES, not suggestions — each either passes or the discrepancy is investigated and
explained in `analysis.md` before any finding is reported:

1. **Pre-registration match**: row count and magnitudes vs. the Phase 2 pre-registered
   expectations. Off by an order of magnitude → find out why before proceeding.
2. **Grain assertion (mandatory for any query with a join)**: run
   `select count(*), count(distinct <declared_grain_key>)` on the pre-aggregation relation
   (or use `--profile-csv --key`); a mismatch is fan-out — fix it or state why it is intentional.
3. **Benchmark reconciliation**: for any dollar/count total leadership might quote, reconcile
   against a NAMED independent anchor — dictionary §11 official metrics, the daily_metrics_report
   snapshot, a prior published number, or a deliberately simpler recount query. Name the anchor
   in the brief.
4. **Null & duplicate audit**: from the profile output — explain any surprise.
5. **Partial-period flag**: is the most recent day/week/month incomplete? Leadership always asks.
6. **Comparison discipline**: any rate/share comparison between segments or periods reports the
   n/denominator on BOTH sides, and either a quick two-proportion z / Wilson interval check
   (scipy is in the venv) or the explicit tag "descriptive gap — not tested for significance".
   The tag is MANDATORY when either side's n < 1,000 or the gap is within ~2 standard errors.

For high-stakes deliverables (going to leadership, large dollar claims), dispatch the
`warehouse-analyst` agent in **verify mode**: pass the business question verbatim, the claimed
headline number(s) with period/filters, and the tables the original used as a
use-a-different-path hint — NOT the original SQL (it would anchor the verifier). Reconcile
MATCH/MISMATCH before delivery.

## Phase 5 — Insights

- Profile: rows, grain, time range, data quality flags — stated upfront
- 3-5 findings, each citing a specific number ("Q1 was $X, up Y% vs Q4" — never "revenue increased")
- Every compared rate/share carries its n; every headline states period + population + convention
  (tips in/out, live vs published refunds, counting key) — the "definitions used" line
- One-paragraph strategic narrative: what is happening and why a leader should care
- Anomalies flagged with the date/value where they occur; counter-intuitive results get hypotheses
- Mandatory "What this data doesn't tell us" section — scope limits, confounders, missing dimensions

## Phase 6 — Deliverables

Everything already lives in `./analysis_<slug>_<yyyymmdd>/` (started in Phase 1):
- `analysis.md` — the brief (profile, findings, narrative, recommendations, limitations, QA gate
  results, query inventory) — polish the running file, don't write it from scratch here
- `NN_<purpose>.sql` — every executed query
- `results*.csv` — pulled data
- `chart_*.png` — 1-3 charts via `~/.venvs/abdata/bin/python` (matplotlib: titles state the finding,
  labeled axes with units, 10×5 single / 12×8 multi-panel; horizontal bars for ranked categories,
  no pie charts)

**Registry (every delivered analysis, including chat-only quick answers):** append one line to
`~/.claude/analysis-registry.jsonl`:
`{"date","question","headline","definitions":{"tips","refund_convention","counting_key"},"period","artifacts"}`
(`"artifacts"` = absolute folder path, or `"chat-only"`). This is how "how does this reconcile
with last quarter's number?" stays answerable.

Scale the ceremony to the ask: a one-number question gets the number, the query, the definitions
line, and caveats in chat — no folder, no charts (registry line still required). A full
investigation gets the works.

Close by reporting the headline answer in chat (not just file pointers), then offer:
chain `/exec-qa-prep` for leadership Q&A, `/data-code-review` if the SQL is headed for the
analytics repo, or a dbt model adaptation via `/code-draft`.

## Constraints

The key words "MUST", "MUST NOT", "SHALL", "SHOULD", "SHOULD NOT", "MAY" are per RFC 2119.

- All warehouse access MUST go through `~/.claude/bin/rs` / `rs_query.py` — the skill MUST NOT
  invoke psql, psycopg2, or any other client directly against the warehouse, and MUST NOT attempt
  any write/DDL statement (the scripts block these; do not work around them)
- External schemas (`production_*`, `indigo_aurora`, `mixpanel`) MUST be pulled via `rs csv`,
  never `rs_query.py`
- The skill MUST ask its clarifying questions in at most ONE AskUserQuestion batch at the start,
  and MUST NOT ask further questions unless genuinely blocked
- The skill MUST ground every table and column name in the catalog, repo, or live warehouse —
  invented or placeholder schema is not acceptable; on catalog-vs-dictionary conflict the
  dictionary's `[validated]` fact wins
- The skill MUST pre-register grain/row-count/magnitude expectations before executing, and MUST
  run every Phase 4 gate before presenting any finding — including the grain assertion on every
  join and the n + significance-or-tag rule on every comparison
- Every finding MUST cite a specific number from the results and state its definitions
  (tips, refund convention, counting key) and period
- For multi-query analyses the skill MUST create the output folder and running `analysis.md` in
  Phase 1 and keep it current as work proceeds — not only at delivery
- The skill MUST write files only inside the working directory, except the single append to
  `~/.claude/analysis-registry.jsonl`, which is REQUIRED for every delivered analysis
- The skill MUST validate all SQL against the Redshift checklist before execution and say so in one line
- If results cannot be QA-verified or the connection is unavailable, the skill MUST say so and
  deliver the validated SQL with assumptions documented instead of fabricating results
- Analysis outputs are ActBlue work product: the skill MUST NOT push, upload, or copy queries,
  results, or analysis files to any personal repository (`matthardardt/*`) or any destination
  outside the ActBlue ecosystem, and MUST NOT run `git push` to ANY remote without the user's
  express, confirmed permission in the current conversation
- The skill MUST NOT post to Jira or any external issue tracker — creating, editing, commenting on,
  transitioning, worklogging, or linking an issue — without the user's explicit, in-conversation
  confirmation for that specific action. Default to producing a DRAFT (title, type, priority,
  description, acceptance criteria) for the user to file themselves. Offering to post is fine;
  executing a post without a clear "yes" is not. (User standing policy 2026-08-04, reinforced
  2026-08-18; enforced independently by a `~/.claude/settings.json` ask-gate on the Atlassian
  Jira write tools.)
