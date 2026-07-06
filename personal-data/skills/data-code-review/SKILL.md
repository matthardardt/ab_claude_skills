---
name: data-code-review
description: >-
  Harsh but fair code review for ActBlue data-stack code: Redshift SQL, Python (data/analytics),
  dbt models, and LookML. Grades every finding as Blocker (must fix before use), Warning (should
  fix), or Suggestion (optional improvement). Use when someone says: "review this code", "code
  review", "check this SQL", "is this query correct", "review my Python", "review the dbt model",
  "review this LookML", "critique this", "what's wrong with this", "LGTM check", "is this
  production-ready", "check for bugs", "can you review this before I run it". For fresh-eyes
  review of code AUTHORED IN THE CURRENT SESSION, dispatch the data-code-reviewer agent instead —
  its value is reviewing unanchored by the authoring context; this skill covers everything else.
  Do NOT use for general non-data code review (Rails, TypeScript) — use the code-review skill.
  Do NOT use for security vulnerability scanning — use skill-security-review instead.
metadata:
  actblue_permissions:
    mcp_tools: []
    reads:
      - filesystem:working-directory
      - filesystem:~/analytics
      - filesystem:~/looker-reporting-db
      - filesystem:~/.claude/actblue-data-dictionary.md
      - filesystem:~/.claude/actblue-semantic-catalog
    writes: []
    forbidden:
      - resource: filesystem
        action: write
      - resource: any-mcp
        action: any
---

# Data Code Review

Harsh but fair. Your job is to catch real functional problems before they hit production or a
stakeholder report. Call out what will break, what is likely to break, and what should be
improved — in that order. Don't pad the review with praise. Don't soften Blockers.

**The checklist is single-sourced: load `rubric.md` from this skill's directory and apply it.**
It carries the grading rules, the correctness/Redshift/domain/dbt/Python/LookML passes, the
catalog cross-check with its dictionary-outranks-catalog precedence rule, and the style pass.
Do not review from memory — the domain traps (NULLable is_tip, ACH legacy gate, counting keys,
refund conventions) live in the rubric and the knowledge layer, not in this file.

## Workflow

1. **Identify the language/type** from the code block or context. If unclear, ask before reviewing.
2. **Load `rubric.md`** (same directory as this SKILL.md) and run every applicable pass.
   Resolve domain claims via `~/.claude/actblue-semantic-catalog/bin/catalog` and the data
   dictionary, honoring the rubric's precedence rule.
3. **Compile findings** into the output format below.
4. **Deliver the verdict**: approve / approve-with-warnings / block.

## Output Format

```
## Code Review

**Verdict:** [approve | approve-with-warnings — N warning(s) | block — N blocker(s)]

### Blockers ([N])
| # | Location | Issue | Fix |
|---|---|---|---|
| 1 | CTE: daily_totals | JOIN to contributions on donor_id fans out — one donor has many contributions, inflating the aggregate | Aggregate contributions before joining, or DISTINCT the join key |

### Warnings ([N])
| # | Location | Issue | Recommendation |
|---|---|---|---|

### Suggestions ([N])
| # | Location | Issue | Recommendation |
|---|---|---|---|

### Notes
[Any cross-cutting observations on the overall approach]
```

If a category has zero findings, include the header with "None."

## Constraints

The key words "MUST", "MUST NOT", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

- This skill is read-only: the skill MUST NOT write files, execute queries, or modify any external system
- The skill MUST load and apply `rubric.md` — reviewing from memory or a paraphrased checklist is not acceptable
- The skill MUST classify every finding per the rubric's grades and MUST reference a specific
  location in every finding; only genuine functional errors MAY be graded Blocker
- The skill MUST NOT re-classify a Blocker as a Warning to soften the review
- The skill MUST NOT call any MCP tool
- If the user requests a state-changing action mid-review, the skill MUST stop and obtain explicit user confirmation before proceeding
- Reviewed code is ActBlue work product: the skill MUST NOT push it to any personal repository (`matthardardt/*`) or any destination outside the ActBlue ecosystem; a `git push` to ANY remote requires the user's express, confirmed permission in the current conversation
