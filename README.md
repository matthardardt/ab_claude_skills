# ab_claude_skills

Personal Claude Code plugin marketplace for Matt Hardardt (ActBlue data team). Plugins:
`personal-data` (router, cold-start preflight, warehouse analysis, multi-grain refresh pipeline,
causal design, code drafting/review, exec Q&A prep, dictionary refresh, dispatchable agents) and
`personal-productivity` (command-center briefing).

## Repo rules (hard — for humans and Claude alike)

- **Never push to this repo — or any `matthardardt/*` repo — without Matt's express, confirmed permission in the current conversation.** Commit locally and stop; the push waits for an explicit yes.
- This repo is the **single sanctioned exception** to "everything stays inside the ActBlue ecosystem," and the exception covers **built Claude tooling only** (skills, agents, hooks, plugin metadata). ActBlue work product — queries, query results, data files, analysis output, dashboard logic — must never be committed here. It belongs in `actblue/*` repos or stays local.

## Layout and the three copies

| Copy | Path | Role |
|---|---|---|
| Source | `~/claude-personal-skills` | Edit HERE only |
| Marketplace clone | `~/.claude/plugins/marketplaces/personal-claude-skills` | What the loader registers |
| Loader cache | `~/.claude/plugins/cache/personal-claude-skills/<plugin>/<version>` | What actually loads at startup |

Runtime scripts (`rs`, `sql_guard.py`, `rs_query.py`, `ab-doctor`) additionally install to
**`~/.claude/bin/`** via `personal-data/skills/analyze/scripts/setup_env.sh` — that is the ONE
path skills, agents, and CLAUDE.md reference. Never point components at the per-copy script paths.

## Release workflow (every change batch)

1. Edit in the source repo. Run the tests:
   `python3 personal-data/skills/analyze/scripts/tests/test_sql_guard.py`
2. If scripts changed: re-run `setup_env.sh` (reinstalls `~/.claude/bin`, gated on the tests).
3. Bump `personal-data/.claude-plugin/plugin.json` AND the matching `plugins[]` entry in
   `.claude-plugin/marketplace.json` (they must stay equal).
4. Commit. **Stop — push only with Matt's express OK.**
5. Sync the marketplace clone from source (handles file-copy drift safely):
   `git -C ~/.claude/plugins/marketplaces/personal-claude-skills fetch ~/claude-personal-skills main && git -C ~/.claude/plugins/marketplaces/personal-claude-skills reset --hard FETCH_HEAD`
6. Rebuild the cache for the new version dir and update
   `~/.claude/plugins/installed_plugins.json` (installPath, version, gitCommitSha).
   `~/.claude/bin/ab-doctor --verbose` checks the result.
7. Restart Claude Code — skills load at startup.

## Maintenance invariants

- **New skill or agent ⇒ check the `/ab` router table** for a needed tie-break or dispatch row
  (native-triggerable skills do NOT get mirror rows). The router names only installed skills.
- **One validator**: all read-only SQL validation lives in `sql_guard.py`; `rs` and `rs_query.py`
  both delegate to it. Any change requires a golden-corpus case in `tests/test_sql_guard.py`.
- **One review rubric**: `personal-data/skills/data-code-review/rubric.md` is loaded by both the
  review skill and the reviewer agent. Never fork a second checklist.
- **Embedded domain facts** (canonical filter, ACH gate, cluster facts in analyze/warehouse-analyst/rubric)
  are propagation targets of `dictionary-refresh` Phase 2.4 — keep them thin, prefer catalog pointers.
- `ab-doctor` runs at session start (hook) and self-repairs a wiped loader cache; run
  `ab-doctor --verbose` any time skills look missing.
