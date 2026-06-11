---
name: dictionary-refresh
description: >-
  Quarterly (or on-demand) refresh of the ActBlue data dictionary: re-crawls all seven sources of
  truth (analytics repo, Looker repo, live Redshift catalog, ats product repos, Confluence, Slack,
  Drive/Gmail) with parallel subagents, diff-synthesizes findings into
  ~/.claude/actblue-data-dictionary.md without overwriting validated facts, refreshes the deep
  source extracts, and regenerates the team-distributable corporate edition (Markdown + docx).
  Use when someone says: "refresh the data dictionary", "re-run the dictionary crawl",
  "/dictionary-refresh", "update the data dictionary", "quarterly dictionary refresh", "re-crawl
  the sources of truth", "is the data dictionary stale". Do NOT use to answer a data question
  (use analyze), to look up a definition (read the dictionary directly), or to add a single fact
  the user just validated (edit the dictionary in place and tag it [validated]).
metadata:
  actblue_permissions:
    mcp_tools:
      - atlassian:search-and-read-only (searchConfluenceUsingCql, getConfluencePage, getConfluenceSpaces, getPagesInConfluenceSpace, searchJiraIssuesUsingJql)
      - slack:search-and-read-only (slack_search_channels, slack_search_public_and_private, slack_read_channel, slack_read_thread, slack_read_canvas)
      - gmail:search-and-read-only (search_threads, get_thread)
      - gdrive:search-and-read-only (search_files, read_file_content)
    reads:
      - filesystem:~/analytics
      - filesystem:~/looker-reporting-db
      - filesystem:~/ats
      - filesystem:~/.claude/actblue-data-dictionary.md
      - filesystem:~/.claude/actblue-data-dictionary-sources
      - filesystem:working-directory
      - warehouse:redshift-read-only
    writes:
      - filesystem:~/.claude/actblue-data-dictionary.md
      - filesystem:~/.claude/actblue-data-dictionary-sources
      - filesystem:~/Cowork/team-data-dictionary
    forbidden:
      - resource: any-mcp
        action: write (no sending, posting, reacting, creating, or updating in any external system)
      - resource: warehouse
        action: write
      - resource: warehouse
        action: data-table-scans (catalog lane is svv_* metadata ONLY)
      - resource: git
        action: push
---

# /dictionary-refresh — Re-crawl the Sources of Truth

You refresh the two-tier ActBlue data dictionary: the canonical Claude-facing file at
`~/.claude/actblue-data-dictionary.md` (tier 1) and the deep per-source extracts at
`~/.claude/actblue-data-dictionary-sources/` (tier 2), then regenerate the team-distributable
corporate edition at `~/Cowork/team-data-dictionary/`. First built 2026-06-11; this skill repeats
that build differentially.

## Phase 0 — Baseline

1. Read `~/.claude/actblue-data-dictionary.md` in full. Note the last build date (§19) and compile
   the **ALREADY KNOWN block**: a ~25-line compression of its hard rules, validated domain facts,
   and §18 open questions. Every crawl agent receives this block so it hunts for NEW facts and
   CONTRADICTIONS, not re-derivations.
2. `rs ping` (path in global CLAUDE.md). If it fails, the VPN is off — tell the user, and either
   wait or proceed without the live-catalog lane (note the gap in the final report).
3. Record clone freshness: `git -C <repo> log -1 --format='%cd %h' --date=short` for `~/analytics`,
   `~/looker-reporting-db`, `~/ats/indigo`. If a clone is >2 months stale, suggest the user pull it
   before crawling (don't pull team repos yourself).

## Phase 1 — Parallel crawl (7 subagents, one message)

Dispatch seven `general-purpose` subagents in a single message. Every prompt MUST include: today's
date; the ALREADY KNOWN block; the output file path under
`~/.claude/actblue-data-dictionary-sources/` (overwrite the existing extract); the provenance +
confidence-tag contract ([validated] only for explicit human confirmation; else [code]/[doc]/[chat]);
the read-only rules below; and "final message = ≤80 dense lines for the orchestrator: top findings,
contradictions, output path, access failures."

Lane specs (the 2026-06-11 extracts in the sources dir are worked examples of the expected output):

1. **`01_analytics_repo.md`** — `~/analytics` + `~/daily_metrics_report` + workbench READMEs.
   Table-usage census (grep FROM/JOIN, ranked); per-table filter/join patterns; metric formulas with
   SQL fragments; value enumerations decoded in CASE statements; folder map deltas; new definitional
   comments since last build.
2. **`02_looker_repo.md`** — `~/looker-reporting-db`. Model/explore inventory deltas; join map
   (sql_on = canonical keys); view→table map changes; new/changed measures and logic-bearing
   dimensions (quote sql:); manifest constants; dashboard inventory; bugs (grep for dims whose sql
   doesn't match their name).
3. **`03_redshift_catalog.md`** — live catalog, **metadata ONLY** (svv_all_tables,
   svv_all_columns, svv_external_schemas via `rs`): schema map with table counts; new/dropped
   tables in core schemas; column dictionaries for the ~30 core tables (diff vs the prior extract —
   new/dropped/retyped columns are the headline); discovery sweeps (`rs find`) for new domains.
   ZERO queries against data tables — Spectrum/datashare scans cost money.
4. **`04_product_repos.md`** — `~/ats/*` (indigo priority). Skip entirely if clones haven't been
   pulled since the last refresh (note it). Value enumerations, model semantics, trigger-derived
   columns, fee logic, new migrations. Always tag [code, repo@<clone date>] and carry the "absence
   here proves nothing" caveat.
5. **`05_confluence.md`** — CQL search (the Rovo `search` tool misbehaves — use
   `searchConfluenceUsingCql`; serialize calls, parallel MCP calls duplicate payloads). Re-read the
   jackpot pages indexed in the prior extract §2 for changes (Scorecard, NRR, Merchant-vs-Conduit,
   PO1 Glossary, Business Rules, Pipeline SLAs, product-adoption pages) + search for new
   definitional pages since the last build date.
6. **`06_slack.md`** — search the data channels mapped in the prior extract §1
   (#data_science_and_engineering is the richest) for definitional threads SINCE the last build
   date: "definition", "grain", table names, "deprecated", "use X instead", dbt/Looker PR
   discussions. Settled definitions, gotchas, deprecations, pipeline changes.
7. **`07_gmail_drive.md`** — light pass (~15-20 calls): Drive for new definitional docs; Gmail as a
   PR-notification index for actblue/analytics + looker-reporting-db merges since last build.

## Phase 2 — Differential synthesis

1. Read all seven agent summaries (and spot-read extracts where a summary flags something big).
2. Merge into `~/.claude/actblue-data-dictionary.md` under these rules:
   - **[validated] facts are never silently overwritten.** A contradiction from any source goes to
     §18 (Open questions) with both versions and provenance; the user adjudicates.
   - New facts land in the right section with confidence tag + (→NN) source pointer.
   - Superseded non-validated facts are replaced; note "supersedes <date> entry" when material.
   - Resolved §18 items move into the body with their resolution; new conflicts join the list.
   - Update §19: build date, clone dates, anything that changed structurally.
3. Empirically re-verify any fact a lane contradicted IF one cheap metadata query settles it
   (the 2026-06-11 timezone probe — executed_at vs getdate() lag — is the model).
4. Propagate: if a NEW hard rule emerged (§1 material), also update the global CLAUDE.md cluster
   facts and the workbench AGENTS.md pointers, and note the plugin sync workflow (edit source →
   commit → STOP, push needs the user's express OK → sync installed copy by file copy).

## Phase 3 — Regenerate the team edition

Rebuild `~/Cowork/team-data-dictionary/ActBlue_Data_Dictionary_Team_Edition_v<N>.md` (+ `.docx`
via the docx skill) from the updated dictionary:
- Corporate format: document-control block (owner, version, date, classification "ActBlue Internal
  — Data Department"), golden rules, platform overview, table catalog, keys & counting, business
  glossary, metric definitions, conventions, domain notes, known issues, doc index, **numbered
  endnotes citing every item's source** (Confluence URL + date, repo path + clone date, Slack
  channel + author + date, live-catalog as-of date).
- Bump the version, add a revision-history row summarizing what changed this refresh.
- **Sensitivity pass before writing**: exclude unverified inferences about colleagues' active work,
  the user's personal-job bug details, and anything §18 flags as unadjudicated; keep commercially
  sensitive terms (e.g. processor contract rates) only under the internal classification header.

## Phase 4 — Report

Tell the user: what changed (new facts, corrections, new conflicts in §18), what was verified, any
lanes that failed (VPN, auth), clone staleness, and the team-edition version produced. Remind them
the team edition is ActBlue work product — they distribute it through ActBlue channels themselves.

## Constraints

The key words "MUST", "MUST NOT", "SHALL", "SHOULD", "SHOULD NOT", "MAY" are per RFC 2119.

- The skill and all subagents MUST be strictly read-only against every external system: no Slack
  messages/reactions, no Confluence/Jira creates or updates, no Gmail drafts/labels, no Drive writes
- Warehouse access MUST go through the `rs` scripts; the catalog lane MUST issue metadata (svv_*)
  queries only — no data-table scans; any empirical verification query MUST be tightly filtered
- The skill MUST NOT overwrite a [validated] fact on crawl evidence alone — contradictions go to
  §18 for the user to adjudicate
- The skill MUST NOT commit or push in team repos (`~/analytics`, `~/looker-reporting-db`,
  `~/ats/*`), MUST NOT push to ANY remote, and MUST NOT print credentials or tokens
- The team edition MUST carry the internal classification header and MUST NOT be uploaded, posted,
  or published anywhere by the skill — distribution is the user's act
- Subagent prompts MUST embed the ALREADY KNOWN block and the provenance/confidence contract; an
  extract without per-fact provenance is not acceptable
