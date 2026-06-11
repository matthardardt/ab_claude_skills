# ab_claude_skills

Personal Claude Code plugin marketplace for Matt Hardardt (ActBlue data team). Plugins: `personal-data` (warehouse analysis, code drafting/review, exec Q&A prep, dispatchable agents) and `personal-productivity` (command-center briefing).

## Repo rules (hard — for humans and Claude alike)

- **Never push to this repo — or any `matthardardt/*` repo — without Matt's express, confirmed permission in the current conversation.** Commit locally and stop; the push waits for an explicit yes.
- This repo is the **single sanctioned exception** to "everything stays inside the ActBlue ecosystem," and the exception covers **built Claude tooling only** (skills, agents, hooks, plugin metadata). ActBlue work product — queries, query results, data files, analysis output, dashboard logic — must never be committed here. It belongs in `actblue/*` repos or stays local.
- Two clones exist: source at `~/claude-personal-skills`, installed copy at `~/.claude/plugins/marketplaces/personal-claude-skills/`. Workflow: edit source → commit → (approved) push → `git pull` in the installed copy.
