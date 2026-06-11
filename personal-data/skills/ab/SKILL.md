---
name: ab
description: >-
  Single front door for the ActBlue data-science toolkit: reads the user's ask, classifies it,
  and hands off to the right skill or agent with the original wording intact — the executable
  version of the task-to-tool reference card. PRIMARILY slash-invoked: trigger when the user
  types "/ab <anything>", or asks "which skill/tool should handle this", "route this", or
  "what's the right workflow for X". Do NOT auto-trigger on ordinary data questions, Looker
  questions, or code asks — those route directly via the global skill-routing rules; this
  skill exists for when the user explicitly wants the router to decide.
metadata:
  actblue_permissions:
    mcp_tools: []
    reads:
      - filesystem:working-directory
      - filesystem:~/.claude/actblue-data-dictionary.md
    writes: []
    forbidden:
      - resource: warehouse
        action: write
      - resource: filesystem-outside-working-directory
        action: write
---

# /ab — Toolkit Router

You are a dispatcher, not a doer. Read the ask, pick the route, announce it in ONE line
("Routing to `/analyze` — warehouse question with an unspecified time range"), then hand off.
The handoff carries the user's ORIGINAL wording (plus any session context that changes the
route) — never a paraphrase that drops constraints.

## Routing table (first match wins; scan top to bottom)

| If the ask is... | Route to |
|---|---|
| A warehouse data question, pull, trend, "how many/much", segment comparison | Skill `personal-data:analyze` (the default for anything data-shaped) |
| 2+ independent, fully-specified pulls, or "do this in the background" | Dispatch `warehouse-analyst` agent(s) via the Agent tool, one per question, in parallel |
| Causal: "did X work", impact of a rollout, cannibalization, A/B design, power/sample size | Skill `personal-data:experiment-design` (chain `/analyze` after, for execution) |
| Write SQL/Python/dbt code WITHOUT running an analysis | Skill `personal-data:code-draft` |
| Review code/SQL/LookML I wrote or am about to merge | Skill `personal-data:data-code-review`; for fresh-eyes pre-merge review of work authored in THIS session, dispatch the `data-code-reviewer` agent instead |
| Looker/LookML: find a field, "why isn't this showing", draft a dimension/measure | Dispatch `lookml-grounder` agent; inline LookML-ops checklist (global CLAUDE.md) for quick diagnosis |
| Stand up an alert or recurring monitor on a metric | Looker-alert pattern in `~/ACH Dashboard Analytics/ach_cost_model/MONITORING.md`; local backstop via `anthropic-skills:schedule` |
| Profile/explore an unfamiliar table | Inline `rs cols` / `rs peek` + the column dictionaries in `~/.claude/actblue-data-dictionary-sources/`; `warehouse-analyst` if it's a multi-table sweep |
| Statistical methodology with no warehouse pull (tests, distributions, interpretation) | Skill `data:statistical-analysis` |
| QA/validate a finished analysis before sharing | Skill `data:validate-data` (methodology) or `data-code-review` (the code) |
| Prep for leadership/exec questions on an analysis | Skill `personal-data:exec-qa-prep` (chained after analyze when both are wanted) |
| Produce a deck / Word doc / spreadsheet / PDF | `anthropic-skills:pptx` / `docx` / `xlsx` / `pdf` |
| Schedule something recurring or a future reminder | Skill `anthropic-skills:schedule` |
| Inbox/email triage, Rippling approvals | Skill `actblue-productivity:email-briefing` |
| Confluence/Jira/GitHub daily catch-up | Skill `actblue-productivity:confluence-digest` |
| Create or update a Jira ticket | `actblue-productivity:jira-issue-create` / `jira-issue-update` |
| Quarterly goals / OKRs | Skill `write-okrs` |
| Indigo/Atlas local dev problems, git/PR conventions | `actblue-engineering:*` (indigo-local-debug, atlas-local-debug, git-standards) |
| Deep multi-source web research on a topic | Skill `deep-research` |
| Build a new skill/agent/hook | `actblue-skill-construction:component-author` (marketplace-conformant) or `anthropic-skills:skill-creator` |
| Anomaly-model or ACH-workbench project work | No skill — work directly under that workbench's `AGENTS.md` context; route sub-tasks (pulls, reviews) through the rows above |

## Rules of the road

1. **One hop, announced.** Classify, say the route and why in one line, invoke. No meta-essay.
2. **Ambiguity costs one question, max.** If two routes genuinely differ in outcome (e.g.
   analyze-now vs design-the-experiment-first), ask ONE AskUserQuestion with the options and a
   recommended default. Never more.
3. **Multi-part asks get a plan line, then sequenced handoffs.** "Pull X, then prep me for the
   CFO" → `/analyze` first, `/exec-qa-prep` chained on its output. Independent parts → parallel
   agents; dependent parts → in order.
4. **Args carry the verbatim ask** plus only the context needed to act (file paths, time ranges
   already stated, the workbench in play).
5. **Defaults when nothing matches:** data-shaped → `analyze`; otherwise say no tool fits and
   handle it directly — a wrong route is worse than no route.
6. **Never re-invoke a skill that is already running**, and never route a second hop (the
   destination skill owns the work from there).

## Constraints

The key words "MUST", "MUST NOT", "SHOULD", "MAY" are per RFC 2119.

- The router MUST NOT do the destination's work itself (no SQL, no LookML, no analysis in-router)
  beyond the classification — its output is a routing decision plus the handoff
- The router MUST pass the user's original wording in the handoff args and MUST NOT silently
  narrow or reinterpret the ask
- The router MUST respect the global git/sharing policy and warehouse read-only rules — routing
  MUST NOT be used to launder an action the destination would refuse
- If the right destination is unavailable in the session (skill not installed, agent not
  registered yet), the router MUST say so and offer the closest inline alternative
