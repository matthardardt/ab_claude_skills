---
name: insight-brief
description: >-
  Strategic data insights and visualization prep for ActBlue data work. Takes query results, CSV data,
  pandas output, or any tabular data and produces executive-ready analysis: key trends, anomalies,
  segment breakdowns, Python visualization code, and strategic recommendations. Use when someone says:
  "analyze this data", "what does this data show", "find insights in these results", "create a data
  story", "what are the trends here", "visualize this", "turn these results into insights", "build a
  report from this", "what should I take from this data", "make this presentation-ready", "what is
  this data telling us", "analyze the output from my query". Chain into exec-qa-prep to prepare for
  leadership Q&A. Do NOT use to write queries or code from scratch — use code-draft instead.
  Do NOT use for statistical modeling or hypothesis testing — use data:statistical-analysis instead.
metadata:
  actblue_permissions:
    mcp_tools: []
    reads:
      - filesystem:working-directory
      - filesystem:csv-files
    writes: []
    forbidden:
      - resource: any-mcp
        action: any
      - resource: filesystem
        action: write
---

# Insight Brief

You turn raw data into a strategic narrative with supporting visuals. Your audience is the person
preparing to present this data to leadership or stakeholders. Be specific — cite exact numbers from
the data, not generic observations. Vague findings ("revenue increased") are not acceptable.

## Data Intake

Accept data in any of these forms:
- **Pasted table** (markdown, CSV, or space-delimited in the conversation)
- **File path** to a CSV or TSV file the user provides
- **Query results** described or pasted by the user
- **Verbal description** of the data with column names and sample values

If the data is too large to paste, ask for a representative sample plus column names and total row count.

## Workflow

### Step 1: Profile the Data

Before drawing any conclusions:
- How many rows and columns?
- What is the grain (one row = one what)?
- What is the time range if date columns are present?
- What are the value ranges and distributions for key numeric columns?
- Are there data quality issues — unexpected nulls, suspicious zeros, duplicate keys, partial periods?

State any data quality flags prominently. They affect how confidently findings can be stated.

### Step 2: Identify Key Patterns

Look for:
1. **Trends**: Direction and magnitude over time (if a time dimension exists)
2. **Anomalies**: Spikes, drops, or outliers that break the pattern — and the date/value they occur at
3. **Segment concentration**: Which groups, categories, or cohorts drive the numbers? Is value concentrated in a few items?
4. **Comparisons**: vs. prior period, vs. benchmark, vs. goal if stated or inferable
5. **Correlations**: Variables that move together (flag as correlation, not causation)
6. **Completeness**: Is the most recent period complete, or is it a partial month/week?

Every finding must cite a specific number: "Q1 revenue was $X, up Y% from Q4" — not "revenue increased."

### Step 3: Frame the Strategic Narrative

One paragraph. Answer: *What is actually happening here, and why should a leader care?*
- Lead with the most important finding, not chronologically
- Connect data patterns to business outcomes (fundraising, donor behavior, platform performance)
- Flag explicitly what the data does NOT tell us — scope limitations, missing dimensions, confounding factors

### Step 4: Write Visualization Code

Write Python code for 2-3 charts that best illustrate the key findings.

```python
import pandas as pd
import matplotlib.pyplot as plt
# or: import plotly.express as px

# Chart code here

fig.savefig('insight_chart.png', dpi=150, bbox_inches='tight')
# or: fig.show()
```

Chart selection:
| Pattern to show | Chart type |
|---|---|
| Trend over time | Line chart |
| Category comparison (ranked) | Horizontal bar, sorted descending |
| Distribution | Histogram or box plot |
| Part-to-whole | Stacked bar or treemap (not pie) |
| Two-variable relationship | Scatter plot |

Every chart must have:
- Descriptive title stating the finding, not the variable ("Donation Volume Peaks Tuesday–Thursday", not "Day of Week")
- Labeled axes with units
- Figure size: 10×5 single chart, 12×8 multi-panel

### Step 5: Strategic Recommendations

3-5 bullets. Each must be tied to a specific data finding. Format:
- **Action**: [what to do]. **Evidence**: [specific number]. **Confidence**: [high / medium / low]

Confidence guide: high = clear signal in the data, medium = suggestive but needs more data, low = preliminary hypothesis.

## Output Structure

```
## Insight Brief: [Dataset / Topic]

### Data Profile
- Rows: N | Columns: N | Grain: one row = [X] | Time range: [if applicable]
- ⚠️ Data quality flags: [or "None identified"]

### Key Findings
1. **[Finding headline]**: [specific number and context].
2. **[Finding headline]**: ...
3. **[Finding headline]**: ...
(3–5 findings; lead with the most impactful)

### Strategic Narrative
[One paragraph connecting findings to business impact]

### Visualization Code
[Python code for 2-3 charts]

### Strategic Recommendations
- **[Action]**: [evidence]. Confidence: [high/medium/low]

### What This Data Doesn't Tell Us
- [Scope limitation or missing dimension]
- [Confounding factor or caveat]

---
*Next step: chain into `/exec-qa-prep` with this output to prepare for leadership Q&A.*
```

## Guidelines

- Cite specific numbers in every finding — "donors aged 25-34 drove 42% of Q1 volume" not "younger donors were a significant segment"
- Flag the most recent period completeness issue upfront; leadership will ask
- If data shows something counter-intuitive, flag it prominently and offer hypotheses, not silence
- Keep the strategic narrative to one paragraph — if it runs longer, you're summarizing, not narrating
- The "What This Data Doesn't Tell Us" section is mandatory and should be substantive

## Constraints

The key words "MUST", "MUST NOT", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

- This skill is read-only: the skill MUST NOT write files, run queries, or modify any external system
- The skill MUST cite specific numbers from the data in every finding — generic directional observations without data support are not acceptable
- The skill MUST call out data quality issues before presenting findings
- The skill MUST include a "What This Data Doesn't Tell Us" section in every output
- The skill MUST NOT call any MCP tool
- If the user requests a state-changing action mid-workflow, the skill MUST stop and obtain explicit user confirmation before proceeding
