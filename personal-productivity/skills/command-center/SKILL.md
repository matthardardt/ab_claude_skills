---
name: command-center
description: >-
  Comprehensive daily briefing across all work systems. Scans Gmail, Slack, Google Calendar, and
  Jira in parallel to produce a single prioritized action plan for the day — what needs a response,
  what is blocking others, what meetings need prep, and what Jira tickets are at risk. Use when
  someone says: "daily briefing", "command center", "what do I need to do today", "morning briefing",
  "what's on my plate", "what's urgent across all my inboxes", "prioritize my day", "daily standup
  prep", "what's waiting on me", "check everything", "catch me up across everything", "what's
  blocking me", "daily status across tools". Supersedes email-briefing when a cross-system view is
  needed. Do NOT use when the request is email-only — use email-briefing for just Gmail.
  Do NOT use when the request is Jira-only — use jira-issue-update or jira-issue-create instead.
metadata:
  actblue_permissions:
    mcp_tools:
      - server: google-workspace-gmail
        tools:
          - search_threads
          - get_thread
          - list_labels
      - server: slack
        tools:
          - slack_search_public_and_private
          - slack_read_thread
          - slack_read_channel
      - server: google-workspace-calendar
        tools:
          - list_calendars
          - list_events
          - get_event
      - server: atlassian
        tools:
          - searchJiraIssuesUsingJql
          - getJiraIssue
          - getVisibleJiraProjects
    reads:
      - gmail:thread
      - gmail:label
      - slack:channel
      - slack:thread
      - google-calendar:event
      - jira:issue
    writes: []
    forbidden:
      - resource: gmail
        action: send
      - resource: gmail
        action: delete
      - resource: gmail
        action: archive
      - resource: gmail
        action: modify-labels
      - resource: slack
        action: send
      - resource: slack
        action: post
      - resource: jira:issue
        action: create
      - resource: jira:issue
        action: modify
      - resource: jira:issue
        action: transition
      - resource: google-calendar:event
        action: create
      - resource: google-calendar:event
        action: modify
      - resource: google-calendar:event
        action: delete
---

# Command Center

You run a comprehensive daily briefing across Gmail, Slack, Google Calendar, and Jira. Run every
section every time — don't skip sections even if you expect them to be empty. Deliver a single,
prioritized action plan the user can act on immediately.

## Available Tools

**Gmail** (`google-workspace-gmail`): `search_threads`, `get_thread`, `list_labels`

**Slack** (`slack`): `slack_search_public_and_private`, `slack_read_thread`, `slack_read_channel`

**Google Calendar** (`google-workspace-calendar`): `list_calendars`, `list_events`, `get_event`

**Jira** (`atlassian`): `searchJiraIssuesUsingJql`, `getJiraIssue`, `getVisibleJiraProjects`

## Workflow

**Run Steps 1–4 in parallel.** Do not wait for one to complete before starting the others.

---

### Step 1: Gmail Scan

Run these searches in parallel:
1. `in:inbox is:unread newer_than:1d` — today's unread
2. `in:inbox to:me is:unread newer_than:3d` — direct requests still open
3. `is:starred is:unread` — starred / flagged

Call `get_thread` on any thread where the subject or snippet contains: urgent, action required,
approve, please respond, deadline, a question mark, or a direct address to the user by name.

Classify each thread:
- 🔴 **Respond today**: explicit deadline, decision request, waiting on user to unblock someone
- 🟡 **Respond this week**: question or request without a stated deadline
- 🔵 **FYI**: notifications, newsletters, CCs, confirmations

---

### Step 2: Slack Scan

Run these searches:
1. `slack_search_public_and_private` for `@[username]` mentions in the last 24h
2. Search for direct messages (DMs) from the last 24h
3. Look for threads where the user was mentioned or asked something and hasn't replied in 24h+

Classify each:
- 🔴 **Respond today**: direct question, someone explicitly waiting on the user
- 🟡 **Respond this week**: FYI thread the user should acknowledge
- ⭕ **Passive mention**: @here, @channel broadcast — not personal

---

### Step 3: Calendar Scan

Retrieve today's and tomorrow's events using `list_events`.

For each event today, assess:
- Is prep needed? (substantive meeting vs. routine check-in, external attendees, user is presenting)
- Is the user presenting data or bringing analysis?
- Is there a double-booking or conflict?

Flag events where the user likely needs to prepare but there is no clear prep artifact yet.

---

### Step 4: Jira Scan

Run these JQL queries:
1. `assignee = currentUser() AND status NOT IN (Done, Closed, "Won't Do") ORDER BY updated DESC` — all open work
2. `assignee = currentUser() AND status = "In Progress"` — active items
3. `assignee = currentUser() AND duedate <= 3d AND status NOT IN (Done, Closed)` — due within 3 days
4. Issues with a recent comment @-mentioning the user, indicating someone is waiting

Classify:
- 🔴 **At risk**: overdue, due today, or explicitly blocking another ticket
- 🟡 **In flight**: active, not at risk
- 🔵 **On deck**: unstarted, not due soon

---

### Step 5: Prioritize and Compile

Cross-system priority order:
1. Things blocking other people (Jira blockers, Slack threads with someone waiting)
2. Hard deadlines today (email / Jira due today)
3. Meeting prep needed for sessions starting in the next few hours
4. Everything else by recency

The **Must Do Today** list MUST NOT exceed 7 items. If more qualify, ruthlessly prioritize by who is blocked waiting on the user.

---

## Output Format

```
## Command Center — [Day, Date]

> ⚠️ SECURITY / PAYMENT ALERT: [if any suspicious emails, phishing attempts, or fraud flags — surface here FIRST]

### 🔴 Must Do Today ([N])
| # | System | Item | Why urgent | Action |
|---|---|---|---|---|
| 1 | Gmail | Subject line | Stakeholder waiting 24h | Reply |
| 2 | Jira | TICKET-123 | Due today, blocking TICKET-456 | Update status |
| 3 | Slack | #data-team, @name | Direct question 8h ago | Respond in thread |

### 📅 Meetings Today ([N])
| Time | Meeting | Prep needed? | What to prep |
|---|---|---|---|
| 10:00 | Standup | No | — |
| 2:00 | Q2 Data Review | Yes | Bring donor volume numbers, Q2 vs Q1 |

### 🟡 This Week ([N])
| # | System | Item | Action |
|---|---|---|---|

### 🎫 Jira Status
| Ticket | Title | Status | Due | Risk |
|---|---|---|---|---|
| TICKET-123 | [title] | In Progress | Today | 🔴 At risk |

### 🔵 FYI — No Action Needed ([N])
- [Subject] (Gmail)
- [@mention in #channel] (Slack)

---

### 📊 Summary
- **Must do today**: N items across N systems
- **Meetings**: N today (N needing prep)
- **Open Jira tickets**: N (N at risk)
- **Unread emails needing response**: N
- **Unanswered Slack mentions**: N
```

## Guidelines

- For meetings needing prep, give a one-line reminder of WHAT to prepare, not just that prep is needed
- If you can't read a channel, thread, or calendar due to permissions, note it rather than silently skipping
- Flag any security alert, phishing attempt, or payment fraud signal at the very top of the output before all other sections
- If Jira has no open tickets, include the section with "No open Jira items"
- Keep the Must Do Today list actionable — each row should have a clear, concrete next action

## Constraints

The key words "MUST", "MUST NOT", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

- This skill is read-only: the skill MUST NOT send messages, post to Slack, create or modify calendar events, comment on or transition Jira issues, or take any write action on any connected system
- The skill MUST run all four system scans (Gmail, Slack, Calendar, Jira) every invocation — the skill MUST NOT skip a section because it might be empty
- The skill MUST cap the Must Do Today list at 7 items; if more qualify, the skill MUST prioritize by who is blocked waiting on the user
- The skill MUST include the Summary table at the end of every output
- The skill MUST surface any security or payment alert at the very top of the output before all other sections
- If the user requests a state-changing action mid-workflow (send this reply, update this ticket), the skill MUST stop and obtain explicit user confirmation before proceeding
- The skill MUST NOT send emails, post Slack messages, comment on Jira issues, or create calendar events even if asked mid-session — those are separate skills
