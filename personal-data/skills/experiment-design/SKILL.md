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
  (use analyze), for explaining statistical concepts with no study attached (answer inline —
  no skill owns that), or for reviewing finished analysis code (use data-code-review).
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
  to enable; assignment is NOT random — selection into treatment is the default threat, not an
  edge case. Treatment timing is NOT one flag flip: ACH shows on forms only while three mutable
  conditions all hold (dictionary "ACH & Nacha" → eligibility three-part rule), so an
  `accepts_ach` flip in `indigo_aurora.audits` dates one condition, not exposure, and "ever
  opted in" is not reconstructable. Define treatment as effective exposure, rebuilt as-of each
  date from every condition you can observe (name the ones you can't); check for off→on
  reversals — if any, censor at first reversal (say so) or use a non-absorbing estimator
  (de Chaisemartin–D'Haultfœuille); stacked/CS/SA all assume absorbing treatment.
- **Formapp flags roll out per FORM**, as a % dial that can move inside the window or a binary
  per-form switch (Stripe Elements 2026-08: dials ramped in-window, then 0/3,000 forms served
  both arms; the pooled gap was form mix). Not documented in the dictionary — see findings-wiki
  `open-questions.md`.
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
   comparison of means + CUPED-style pre-period adjustment — but ONLY after the
   randomization-integrity checks in Phase 2 pass. "A real control" is a claim to verify,
   not an assumption: ActBlue A/B arms have run for DIFFERENT durations
   (`system_ab_tests_unnested`), and naive pooling let seasonality masquerade as a treatment
   effect (validated incident: recurring-checkbox test, naive +0.423pp → corrected +0.304pp,
   2026-06). Restrict every arm to the common assignment window before comparing anything.
   **Per-form rollouts:** the unit of assignment is the form — cluster SEs at form, effective n
   = forms. Reconstruct each form's dial history (flag config, PE-2786 — not in the warehouse);
   if the % moves in-window, compare only within stable-dial epochs (or IPW by epoch
   probability). A binary per-form switch has NO within-form contrast: at best it is
   cluster-randomized at form level, and if forms didn't flip at random it is setting 2, not 1.
2. **Staggered adoption** (the ActBlue default): **stacked event-study is the default
   estimator** — build a clean 2x2 per adoption cohort (treated cohort vs not-yet/never-treated
   in a fixed event window), stack, estimate with cohort×window fixed effects.
   Pooled static TWFE is acceptable ONLY with an explicit one-line homogeneity justification:
   with staggered timing and effects that grow post-adoption (the normal rollout shape),
   TWFE uses early adopters as controls for late ones and its negative weights can attenuate
   or sign-flip the estimate (Goodman-Bacon). Callaway–Sant'Anna / Sun–Abraham are the named
   alternatives if estimator packages are wanted; stacked OLS runs on the abdata venv
   (statsmodels is installed). State the estimand honestly: this identifies the **ATT for
   adopter cohorts**, not a platform-wide effect — the Phase 4 estimand sentence must say so.
3. **Single cutover date, everyone treated** (policy/fee change): interrupted time series
   against the entity's own seasonal baseline, ideally with a placebo series that the change
   could not have affected.
4. **No usable variation** (everyone treated at once, no pre-period): say so honestly —
   offer bounding exercises or a forward-looking holdout design instead of fake causality.

For matching designs, match on the drivers of selection (entity tier, race type, pre-period
volume trajectory) — `entity_finance_tiers`-style net-raised tiers are the standard strata, but
only as rebuilt for the pre-period (current tiers include post-adoption growth).

## Phase 2 — Design-validity checks (the plan MUST name each, with a query to test it)

- **Randomization integrity** (setting 1, mandatory before any comparison of means):
  (a) *Arm contemporaneity* — compute each arm's assignment window from sequence-0 `paid_at`
  (NOT `contribution_tag_updated_at`, whose churn makes tests look active through today) and
  restrict ALL arms to the common window `[max(arm starts), min(arm ends)]`;
  (b) *Sample-ratio mismatch* — chi-square the observed arm counts against the designed
  allocation; a significant SRM means broken assignment, stop and investigate before any
  effect estimate. Both have one-query tests — sketch them in the plan.
  SRM and comparison of means are valid ONLY when assignment is recorded for ALL units before
  the outcome and the designed allocation is known. `system_ab_tests_unnested` records arms
  only for contributions that happened (converters): there, SRM confuses a conversion effect
  with broken assignment, and within-converter means are conditional on conversion (selection
  + effect). Instead: run SRM and an ITT on an exposure-denominated source that carries the arm
  (form-view/landing events — confirm the arm is logged pre-outcome); or state the estimand as
  conditional-on-conversion and bound it; or treat the study as observational (setting 2/3).
- **Inference spec** (settings 1-3, mandatory): name the clustering level and it must match
  the assignment level — entity-level treatment means entity-clustered SEs; a daily panel
  over months has serially correlated outcomes, and unclustered SEs will produce p<0.001 on
  noise (Bertrand–Duflo–Mullainathan). With a handful of treated clusters, say plainly that
  clustered asymptotics fail (wild-cluster bootstrap or aggregate to one pre/post obs per unit).
- **Parallel trends**: plot/compare treated vs control outcome trends for ≥8 pre-periods;
  an event-study plot with flat pre-coefficients is the standard exhibit.
- **Selection into treatment**: compare treated vs control on pre-period levels AND growth;
  if adopters were already growing faster, say what that does to the sign of the bias.
- **Spillover/interference**: name the path (shared donors, conduit relationships) and either
  bound it or restrict the sample (e.g. donors exclusive to one entity in the PRE-period).
- **No post-treatment conditioning**: every stratifier, matching variable, and sample
  restriction (tiers, donor exclusivity, new-vs-existing status) is computed strictly as-of
  each cohort's adoption date − 1; name the as-of date for each. Current-state flags and
  tiers carry look-ahead bias.
- **Contamination by platform shocks**: check whether any anomaly-model event-library event
  lands in the analysis window; mask or dummy it.
- **Composition drift**: new-to-platform vs existing donors decomposed separately (the
  cannibalization suite's new-money decomposition is the template) — an outcome
  decomposition, never a conditioning variable for the causal estimate.
- **Heavy tails / whales**: dollar outcomes are dominated by a few donors (one donor was 85% of
  treated ACH dollars in the 2026-07 cannibalization run). Report the top-k donors' share, the
  estimate with and without the top donors (top-1 / top-1%), a winsorized (e.g. p99.9) or
  trimmed version, and a count or `log1p` outcome alongside.
- **Multiplicity & peeking**: pre-register ONE primary outcome + horizon; secondary outcomes
  and segment splits are Holm/BH-adjusted and labelled exploratory. No repeated (e.g. daily)
  significance reads of a running test unless the plan names a sequential method (mSPRT /
  alpha spending); otherwise one fixed-horizon read.
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
- Dollar outcomes: `sigma` is the variance of the outcome actually analyzed (winsorized /
  trimmed / log1p, or a robust estimator's), never the raw dollar σ a single whale dominates.
- **Ground the inputs**: baseline rates, variances, and unit counts SHOULD come from a quick
  real pull (`~/.claude/bin/rs`) rather than round-number guesses; state the source of every
  power input in the plan.

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
- For setting 1, the plan MUST include the randomization-integrity checks (arm common window
  from sequence-0 paid_at + SRM test) BEFORE any comparison of means, and MUST NOT run SRM or
  report a means comparison as causal on converter-only assignment data; for settings 1-3 the
  plan MUST carry an explicit inference spec (clustering level matched to assignment level —
  form for per-form flag rollouts)
- The plan MUST name ONE pre-registered primary outcome, MUST compute every conditioning
  variable as-of pre-treatment, and for dollar outcomes MUST include the with/without-top-donors
  robustness exhibit
- Every validity check in Phase 2 MUST appear in the plan with a concrete test, or a stated
  reason it doesn't apply
- A power/MDE statement MUST be included; "we'll see what's significant" is not a plan
- All table/column references MUST be grounded in the semantic catalog, `~/analytics`, the live
  catalog, or the data dictionary; warehouse access MUST go through the `rs` scripts, read-only
- The skill MUST ask at most ONE AskUserQuestion batch, then proceed on stated assumptions
- Files MUST be written only inside the working directory
