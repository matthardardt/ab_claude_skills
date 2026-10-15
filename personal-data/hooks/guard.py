#!/usr/bin/env python3
"""guard.py — personal-data plugin hooks (hooks/hooks.json).

pretooluse    (Bash, every session)
  - any `git ... push` (incl. `git -C <dir> push`) → ask. Backs the hard rule that nothing is
    pushed without an express OK; settings.json's `git push` ask-gate misses the `-C` form.
  - inside this plugin's agents only (agent_type personal-data:*): deny network egress
    (curl/wget/nc/ssh/scp/rsync/sftp/ftp), raw DB clients (psql/pg_dump — warehouse access goes
    through ~/.claude/bin/rs so sql_guard applies), package installs, and git writes. Agents are
    read-only by contract; this makes the contract mechanical.
subagentstop  (warehouse-analyst)
  - verify mode: `VERDICT:` lines suffice. Otherwise a `STATUS:` line is required, and STATUS: OK
    also needs the `VERIFIED:` line. Blocks once with the missing items; never loops.

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


def subagentstop(ev):
    if ev.get("stop_hook_active"):
        return  # already blocked once; never loop
    msg = ev.get("last_assistant_message") or ""
    if re.search(r"^\W*VERDICT\W*:", msg, re.M):
        return  # verify mode: per-number VERDICT lines are the contract
    missing = []
    status = re.search(r"^\W*STATUS\W*:\W*(\w+)", msg, re.M)
    if not status:
        missing.append("a `STATUS:` line (or `VERDICT:` lines if this was a verify dispatch)")
    elif status.group(1).upper() == "OK" and not re.search(r"^\W*VERIFIED\W*:", msg, re.M):
        missing.append("the `VERIFIED: no — primary pull …` line")
    if missing:
        print(json.dumps({"decision": "block", "reason":
            "Return contract incomplete — add " + " and ".join(missing)
            + " to your final report, per the Return block in your instructions. Do not re-run queries."}))


if __name__ == "__main__":
    try:
        ev = json.load(sys.stdin)
        {"pretooluse": pretooluse, "subagentstop": subagentstop}[sys.argv[1]](ev)
    except Exception as e:  # fail open, loudly
        print(f"personal-data guard: internal error ({e}); not enforcing", file=sys.stderr)
    sys.exit(0)
