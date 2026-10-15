#!/usr/bin/env python3
"""guard.py — personal-data plugin hooks (hooks/hooks.json).

pretooluse    (Bash, every session)
  - any `git ... push` (incl. `git -C <dir> push`) → ask. Backs the hard rule that nothing is
    pushed without an express OK; settings.json's `git push` ask-gate misses the `-C` form.
  - inside this plugin's agents only (agent_type personal-data:*): deny network egress
    (curl/wget/nc/ssh/scp/rsync/sftp/ftp), raw DB clients (psql/pg_dump — warehouse access goes
    through ~/.claude/bin/rs so sql_guard applies), package installs, and git writes. Agents are
    read-only by contract; this makes the contract mechanical.
handback      (PreToolUse on SubagentHandback, inside warehouse-analyst)
  - the report travels in the handback call, so it is checked there and DENIED until compliant:
    verify mode needs `VERDICT:` lines; otherwise a `STATUS:` line, and STATUS: OK also needs
    the `VERIFIED:` line. (A SubagentStop check was tried first: it fired only after delivery,
    and last_assistant_message doesn't hold the report — live test 2026-10-15.)
agent_result  (PostToolUse on Agent/Task, parent session)
  - backstop: flags a non-compliant warehouse-analyst report to the parent as additionalContext
    (numbers UNVERIFIED). Background launches carry no report yet and are skipped.

Fails open on its own errors (a broken guard must not wedge a session) but prints why.
"""
import json
import re
import shlex
import sys

AGENT_PREFIX = "personal-data:"
EGRESS = {"curl", "wget", "nc", "ncat", "netcat", "ssh", "scp", "sftp", "rsync", "ftp", "telnet"}
RAW_DB = {"psql", "pg_dump", "pg_dumpall", "redshift-data"}
INSTALL = {("pip", "install"), ("pip3", "install"), ("brew", "install"), ("npm", "install"), ("pipx", "install")}
GIT_WRITE = {"push", "commit", "remote", "checkout", "switch", "reset", "stash", "rebase", "merge",
             "pull", "fetch", "clean", "tag", "branch", "add", "rm", "mv", "restore", "cherry-pick"}
SEP = re.compile(r"(?:\|\||&&|[;|&\n()`]|\$\()")


def segments(cmd):
    """Split a shell line into simple-command word lists (best effort; unparsable → raw split)."""
    for part in SEP.split(cmd):
        part = part.strip()
        if not part:
            continue
        try:
            words = shlex.split(part, comments=True)
        except ValueError:
            words = part.split()
        while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
            words = words[1:]  # leading VAR=value assignments
        while words and words[0] in ("sudo", "env", "command", "exec", "nohup", "time", "xargs"):
            words = words[1:]
        if words:
            yield words


def git_subcommand(words):
    """`git [-C dir] [-c k=v] [--opt] <sub>` → sub."""
    i = 1
    while i < len(words):
        w = words[i]
        if w in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
        elif w.startswith("-"):
            i += 1
        else:
            return w
    return None


def classify(cmd, in_agent):
    for words in segments(cmd):
        prog = words[0].rsplit("/", 1)[-1]
        if prog == "git":
            sub = git_subcommand(words)
            if sub == "push":
                return ("deny" if in_agent else "ask"), "git push needs the user's express OK in this conversation (hard rule)"
            if in_agent and sub in GIT_WRITE and sub != "fetch":
                return "deny", f"`git {sub}` — plugin agents are read-only on git (fetch/log/show/grep/diff only)"
        if not in_agent:
            continue
        if prog in EGRESS:
            return "deny", f"`{prog}` — plugin agents have no network egress; use the granted tools"
        if prog in RAW_DB:
            return "deny", f"`{prog}` — warehouse access goes through ~/.claude/bin/rs (sql_guard enforced)"
        if len(words) > 1 and (prog, words[1]) in INSTALL:
            return "deny", f"`{prog} install` — plugin agents must not install packages"
    return None, None


def pretooluse(ev):
    cmd = (ev.get("tool_input") or {}).get("command") or ""
    in_agent = str(ev.get("agent_type") or "").startswith(AGENT_PREFIX)
    decision, reason = classify(cmd, in_agent)
    if decision:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"personal-data guard: {reason}",
        }}))


ANALYST = "warehouse-analyst"


def contract_gaps(report):
    """Missing return-contract items in a warehouse-analyst report ([] = compliant)."""
    if re.search(r"^\W*VERDICT\W*:", report, re.M):
        return []  # verify mode: per-number VERDICT lines are the contract
    status = re.search(r"^\W*STATUS\W*:\W*(\w+)", report, re.M)
    if not status:
        return ["a `STATUS:` line (or `VERDICT:` lines if this was a verify dispatch)"]
    if status.group(1).upper() == "OK" and not re.search(r"^\W*VERIFIED\W*:", report, re.M):
        return ["the `VERIFIED: no — primary pull …` line"]
    return []


def handback(ev):
    """PreToolUse on SubagentHandback, inside warehouse-analyst: deny a non-compliant report
    BEFORE delivery, so the agent fixes it (the report travels in this call, not in the final
    assistant message, so a SubagentStop check can't see it)."""
    if not str(ev.get("agent_type") or "").endswith(ANALYST):
        return
    report = str((ev.get("tool_input") or {}).get("message") or "")
    gaps = contract_gaps(report)
    if gaps:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "personal-data guard: return contract incomplete — add "
                + " and ".join(gaps) + " to the report, per the Return block in your instructions, "
                "then hand back again. Do not re-run queries.",
        }}))


def agent_result(ev):
    """PostToolUse on Agent/Task in the PARENT session: backstop that flags a warehouse-analyst
    report missing its contract lines, so unverified numbers can't be relayed silently.
    Background launches carry no report yet — skipped, never flagged."""
    ti, tr = ev.get("tool_input") or {}, ev.get("tool_response")
    rd = tr if isinstance(tr, dict) else {}
    who = str(rd.get("agentType") or ti.get("subagent_type") or "")
    if not who.endswith(ANALYST):
        return
    report = (rd.get("handbackReport") or {}).get("text") if isinstance(rd.get("handbackReport"), dict) else None
    if report is None and rd.get("status") == "completed":
        content = rd.get("content")
        if isinstance(content, list):
            report = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
        elif isinstance(content, str):
            report = content
    if not report:
        return
    gaps = contract_gaps(report)
    if gaps:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "personal-data guard: this warehouse-analyst report is missing "
                + " and ".join(gaps) + ". Treat every number in it as UNVERIFIED — do not relay a "
                "headline without a verify-mode MATCH, and tell the user the contract was incomplete.",
        }}))


if __name__ == "__main__":
    try:
        ev = json.load(sys.stdin)
        {"pretooluse": pretooluse, "handback": handback, "agent_result": agent_result}[sys.argv[1]](ev)
    except Exception as e:  # fail open, loudly
        print(f"personal-data guard: internal error ({e}); not enforcing", file=sys.stderr)
    sys.exit(0)
