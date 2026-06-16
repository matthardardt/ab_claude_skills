---
name: experiment-design
description: >-
  Design and analysis planning for causal questions at ActBlue: feature-rollout impact,
  cannibalization, "did X cause Y", A/B tests, power analysis, and sample-size math. Produces a
  written analysis plan — estimand, identification strategy (staggered diff-in-diff, event study,
  matching, or randomized analysis), design-validity checks, power/MDE calculation, and a grounded
  SQL skeleton — then chains to /analyze for execution. Use when someone says: "design an
  experiment", "measure the impact of <feature/change>", "is X cannibalizing Y", "did X cause Y",
  "A/B test", "diff-in-diff", "power analysis", "how big a sample do we need", "is this effect
  real or selection". Do NOT use for descriptive pulls or trend questions with no causal claim
  (use analyze), for explaining statistical concepts (use data:statistical-analysis), or for
  reviewing finished analysis code (use data-code-review).
metadata:
  actblue_permissions:
    mcp_tools: []
    reads:
      - filesystem:working-directory
      - filesystem:~/analytics
      - filesystem:~/.claude/actblue-data-dictionary.md
      - filesystem:~/.claude/actblue-semantic-catalog
      - warehouse:redshift-read-only
    writes:
      - filesystem:working-directory
    forbidden:
      - resource: warehouse
        action: write
      - resource: any-mcp
        action: any
      - resource: filesystem-outside-working-directory
        action: write
---

# /experiment-design — Causal Design & Analysis Planning

You turn a causal question into a defensible analysis plan. The deliverable is the PLAN —
estimand, identification, checks, power — not the executed analysis (chain `/analyze` for that).

## ActBlue reality (design around these, not textbook RCTs)

- **Features ship as staggered opt-in rollouts, not randomized experiments.** Entities choose
  to enable (e.g. `accepts_ach` flips in `indigo_aurora.audits` with a timestamp). Treatment
  timing is observable; assignment is NOT random — selection into treatment is the default
  threat, not an edge case.
- **Donors are nested in entities** and give to many entities — spillover and SUTVA violations
  are real (a donor's ACH adoption at one entity changes their card behavior at others).
  State the interference assumption explicitly in every plan.
- **The platform is event-driven** (news shocks, fundraising deadlines, cycle seasonality).
  Any pre/post comparison without a control group is presumptively confounded — the anomaly
  model exists precisely because exogenous shocks are constant.
- Worked example to crib from: the ACH cannibalization suite
  (`~/ACH Dashboard Analytics/cannibalization/`, 7 validated queries) — enabled-cohort volume
  trends, donor retention after adoption, new-money decomposition.

## Phase 0 — One question batch (AskUserQuestion, max 4)

Ask only what's genuinely ambiguous among: (1) the decision this informs (ship/kill/tune?),
(2) unit of analysis (entity, donor, contribution), (3) outcome metric + horizon,
(4) what variation exists (who's treated, when, who plausibly isn't). Then proceed
autonomously; state assumptions inline.

## Phase 1 — Classify the identification setting

Pick the FIRST that fits, and say why the simpler ones below it don't:

1. **Randomized assignment exists** (rare — product experiment with a real control):
   straight comparison of means + CUPED-style pre-period adjustment for variance reduction.
2. **Staggered adoption** (the ActBlue default): two-way fixed-effects diff-in-diff or an
   event study around each unit's adoption date. Use never-treated or not-yet-treated units
   as controls; with staggered timing, prefer event-time stacking over a single pooled 2x2.
3. **Single cutover date, everyone treated** (policy/fee change): interrupted time series
   against the entity's own seasonal baseline, ideally with a placebo series that the change
   could not have affected.
4. **No usable variation** (everyone treated at once, no pre-period): say so honestly —
   offer bounding exercises or a forward-looking holdout design instead of fake causality.

For matching designs, match on the drivers of selection (entity tier, race type, pre-period
volume trajectory) — `entity_finance_tiers`-style net-raised tiers are the standard strata.

## Phase 2 — Design-validity checks (the plan MUST name each, with a query to test it)

- **Parallel trends**: plot/compare treated vs control outcome trends for ≥8 pre-periods;
  an event-study plot with flat pre-coefficients is the standard exhibit.
- **Selection into treatment**: compare treated vs control on pre-period levels AND growth;
  if adopters were already growing faster, say what that does to the sign of the bias.
- **Spillover/interference**: name the path (shared donors, conduit relationships) and either
  bound it or restrict the sample (e.g. donors exclusive to one entity).
- **Contamination by platform shocks**: check whether any anomaly-model event-library event
  lands in the analysis window; mask or dummy it.
- **Composition drift**: new-to-platform vs existing donors decomposed separately (the
  cannibalization suite's new-money decomposition is the template).
- **Data traps**: legacy-vs-new-era gates (e.g. ACH `paid_at >= '2026-04-20'`), settled-only
  tables, refund rules — resolve as named filter macros via
  `~/.claude/actblue-semantic-catalog/bin/catalog filter <name>` (`legacy_ach_gate`, `real_donations`,
  `published_refunds`, `exclude_internal_entities`, …) and read `~/.claude/actblue-data-dictionary.md`
  for nuance; don't re-derive.

## Phase 3 — Power / MDE (always, even for observational designs)

Use `~/.venvs/abdata/bin/python` (scipy/numpy) with closed forms — no notebook ceremony:

- Two proportions: `n_per_arm = (z_a/2 + z_b)^2 * (p1(1-p1) + p2(1-p2)) / (p1-p2)^2`
- Two means: `n_per_arm = 2 * sigma^2 * (z_a/2 + z_b)^2 / delta^2`
- Cluster designs (entities = clusters of donors): inflate n by the design effect
  `1 + (m-1) * ICC`; state the assumed ICC.
- For DiD: power on the pre-period residual variance of the unit-level outcome, not the raw
  variance — report the MDE at the actual sample size and say plainly if the question is
  underpowered (small-N rollouts usually are; recommend the wait-time to adequate power).

## Phase 4 — Deliverable

Write `./experiment_design_<slug>_<yyyymmdd>.md` containing: question + decision; estimand
in one sentence; identification choice + why; data spec (outcome metric resolved via
`catalog metric <name>`; tables/filters grounded via the semantic catalog + `~/analytics` grep +
`rs cols` — never invented); the validity checks as a numbered list,
each with its test query sketched; power/MDE numbers; analysis SQL/python skeleton;
known limitations. Close in chat with the 5-line summary and offer to chain `/analyze`
to execute the pre-period checks immediately.

## Constraints

The key words "MUST", "MUST NOT", "SHOULD", "MAY" are per RFC 2119.

- The skill MUST classify the identification setting explicitly and MUST refuse to dress up
  setting 4 (no variation) as a causal estimate — bounding or holdout proposals only
- Every validity check in Phase 2 MUST appear in the plan with a concrete test, or a stated
  reason it doesn't apply
- A power/MDE statement MUST be included; "we'll see what's significant" is not a plan
- All table/column references MUST be grounded in the semantic catalog, `~/analytics`, the live
  catalog, or the data dictionary; warehouse access MUST go through the `rs` scripts, read-only
- The skill MUST ask at most ONE AskUserQuestion batch, then proceed on stated assumptions
- Files MUST be written only inside the working directory
