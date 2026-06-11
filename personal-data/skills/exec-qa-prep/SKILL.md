---
name: exec-qa-prep
description: >-
  Prepares data presenters for executive-level Q&A. Takes a data story, analytics output, or
  presentation summary and generates 10-15 likely leadership questions organized by executive
  perspective (Financial/CFO, Strategic/CEO, Technical/CTO, Process/Risk) — each with a
  data-grounded answer and confidence rating. Also surfaces "gotcha" questions on methodology,
  data quality, and scope. Use when someone says: "prep me for this presentation", "what will
  leadership ask about this data", "create Q&A for this", "prepare for exec review", "anticipate
  executive questions", "what questions should I expect", "briefing prep", "help me prepare for
  my data presentation", "executive Q&A prep", "practice questions for my data review",
  "what will the CFO/CTO/CEO ask". Always use with analytics output or a data story in hand.
  Do NOT use to create slides — use the pptx skill for that.
  Do NOT use without data or findings — this skill generates questions FROM data, not abstractly.
metadata:
  actblue_permissions:
    mcp_tools: []
    reads:
      - filesystem:~/.claude/actblue-data-dictionary.md
    writes: []
    forbidden:
      - resource: any-mcp
        action: any
      - resource: filesystem
        action: write
---

# Executive Q&A Prep

You think like a senior leader reviewing a data presentation for the first time — skeptical,
time-constrained, and looking for what's missing or could go wrong. Generate the hardest,
most consequential questions the presenter will face. Then help them answer those questions
with data they already have, or flag what they need to go find.

Do not generate soft questions. Generate the ones that will make an underprepared presenter sweat.

## Executive Frames

| Persona | Core concerns | Question style |
|---|---|---|
| **CFO / Finance** | Revenue, cost, ROI, budget impact, forecast accuracy | "What's the dollar impact?", "How confident are we in this number?", "What assumptions drive this forecast?" |
| **CEO / Strategy** | Direction, mission alignment, competitive position, donor/user impact | "What does this mean for our strategy?", "Are we better or worse than last year?", "What are we not doing that we should be?" |
| **CTO / VP Engineering** | Data quality, pipeline reliability, methodology, technical debt | "How fresh is this data?", "What could make this number wrong?", "How would we know if the pipeline broke?" |
| **Head of Data / PM** | Scope, completeness, methodology, actionability | "What's not in scope here?", "What would change this conclusion?", "How do we action on this finding?" |

## Gotcha Category

Always generate a dedicated set of questions that expose gaps. For ActBlue data stories, cross-check
the numbers against `~/.claude/actblue-data-dictionary.md` §11 (official metric definitions) and
§18 (open definition conflicts — NRR version, refund convention, tips in/out): "which definition did
you use?" is a guaranteed leadership question. Gap sources the presenter may not have anticipated:
- Data freshness and completeness (is the most recent period complete?)
- Population definition (who is included and excluded, and why?)
- Survivorship bias or selection effects in the data
- What the data explicitly cannot tell us that a leader might assume it does
- Contradictions with prior analyses or known context ("Last quarter's report showed Y — how do these reconcile?")
- Methodology choices that could be questioned ("Why use median instead of mean?", "Why this time window?")
- Edge cases the analyst may not have tested

## Workflow

### Step 1: Read the Input

Take in the analytics output, insight brief, or presentation summary. If only a topic is provided
without findings, ask for the key numbers and conclusions before proceeding.

Identify:
- The core claim(s) the data is making
- The key metrics being presented
- The time range and data scope
- Any already-acknowledged limitations

### Step 2: Generate Questions

Generate 10-15 questions total, organized by persona. Aim for:
- 3-4 Financial questions
- 3-4 Strategic questions
- 2-3 Technical/methodology questions
- 2-3 Gotcha questions (minimum — add more if the data has obvious gaps)

For each question, provide:
- **Prepared answer**: what the presenter should say, grounded in the data. If the data doesn't support a clean answer, say so explicitly rather than winging it
- **Confidence**: High (data clearly supports the answer), Medium (requires additional context), Low (needs research before presenting)
- **Supporting evidence**: the specific number, finding, or data point to cite

### Step 3: Flag Prep Gaps

After the Q&A, list every question that the presenter should be able to answer but currently cannot
from the data provided. These are the things to look up before the meeting. Be specific about what
data or analysis would close each gap.

## Output Format

```
## Executive Q&A Prep: [Topic]

### Financial / CFO Questions ([N])
| # | Question | Prepared Answer | Confidence | Evidence |
|---|---|---|---|---|
| 1 | What is the total revenue impact of this change? | [$X based on Y% lift × Z volume] | High | Finding #2 from the insight brief |

### Strategic / CEO Questions ([N])
| # | Question | Prepared Answer | Confidence | Evidence |
|---|---|---|---|---|

### Technical / Methodology Questions ([N])
| # | Question | Prepared Answer | Confidence | Evidence |
|---|---|---|---|---|

### Gotcha Questions ([N])
| # | Question | Prepared Answer | Confidence | Evidence |
|---|---|---|---|---|

---

### Prep Gaps — Look These Up Before the Meeting
- [ ] [Specific question you cannot currently answer, and what data would close the gap]
- [ ] [Prior conflicting analysis to reconcile and where to find it]

### One-Line Summary for the Presenter
*[The single most important thing to say if you only have 30 seconds with leadership]*
```

## Guidelines

- Write questions in the voice of a skeptical executive who has seen data presentations fail before
- "I'll look into that" is not a prepared answer — write a real answer, or mark it as a prep gap
- When confidence is Low, explain why: missing data, methodology uncertainty, partial period, etc.
- The prep gap list is often the most valuable part of this output — surface it prominently
- Include at least two Gotcha questions even if the data appears solid; leadership always finds the edge case
- Don't generate duplicate questions across personas just to hit the count target

## Constraints

The key words "MUST", "MUST NOT", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

- This skill is read-only: the skill MUST NOT write files or call any MCP tool
- The skill MUST generate questions from all four executive perspectives in every invocation
- The skill MUST include at least two Gotcha questions in every output
- The skill MUST include the Prep Gaps section in every output, even if it is empty (in which case it MUST say "None — all anticipated questions are answerable from the current data")
- The skill MUST NOT generate soft or non-consequential questions to pad the question count
- The skill MUST require actual data or findings as input — it MUST NOT generate abstract Q&A without data. If no data is provided, the skill MUST ask for key findings before proceeding
- If the user requests a state-changing action mid-workflow, the skill MUST stop and obtain explicit user confirmation before proceeding
