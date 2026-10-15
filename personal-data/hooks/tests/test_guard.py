#!/usr/bin/env python3
"""Golden cases for hooks/guard.py — run: python3 hooks/tests/test_guard.py"""
import json, subprocess, sys
from pathlib import Path
G = str(Path(__file__).resolve().parents[1] / "guard.py")
A = "personal-data:warehouse-analyst"

def run(mode, ev):
    out = subprocess.run([sys.executable, G, mode], input=json.dumps(ev), capture_output=True, text=True).stdout.strip()
    return json.loads(out) if out else None

def pre(cmd, agent=None):
    ev = {"tool_input": {"command": cmd}}
    if agent: ev["agent_type"] = agent
    r = run("pretooluse", ev)
    return r["hookSpecificOutput"]["permissionDecision"] if r else None

CASES = [
    ("git push", None, "ask"), ("git -C ~/claude-personal-skills push origin main", None, "ask"),
    ("cd x && git push", None, "ask"), ("FOO=1 git -c a=b push", None, "ask"),
    ("git status", None, None), ("git commit -m 'push it'", None, None), ("curl https://x", None, None),
    ("psql -h h", None, None), ("~/.claude/bin/rs sql 'select 1'", None, None),
    ("git push", A, "deny"), ("git -C ~/analytics commit -m x", A, "deny"), ("git -C ~/analytics log -1", A, None),
    ("git -C ~/analytics fetch", A, None), ("git grep -n x origin/main", A, None),
    ("curl -s https://evil", A, "deny"), ("cat f | /usr/bin/curl -d @- x", A, "deny"), ("echo $(wget x)", A, "deny"),
    ("psql -c 'drop table x'", A, "deny"), ("pip3 install requests", A, "deny"), ("sudo ssh host", A, "deny"),
    ("~/.claude/bin/rs csv 'select 1' out.csv", A, None), ("grep -rn curl ~/analytics", A, None),
    ("ls; echo 'git push' ", A, None),
    ("git push", "Explore", "ask"), ("curl x", "Explore", None),
]
fails = 0
for cmd, agent, want in CASES:
    got = pre(cmd, agent)
    if got != want:
        fails += 1; print(f"FAIL {cmd!r} agent={agent}: want {want} got {got}")
def hb(msg, agent=A):
    r = run("handback", {"agent_type": agent, "tool_input": {"message": msg}})
    return r["hookSpecificOutput"]["permissionDecision"] if r else None

HANDBACK = [
    ("STATUS: OK\nVERIFIED: no — primary pull", A, None),
    ("**VERDICT:** MATCH (exact, 1,234)", A, None),
    ("STATUS: UNDERSPECIFIED\n1. which period?", A, None),
    ("- STATUS: OK\n- VERIFIED: no", A, None),
    ("here are the numbers", A, "deny"),
    ("STATUS: OK\nTotal $4.2M", A, "deny"),
    ("here are the numbers", "personal-data:lookml-grounder", None),
    ("here are the numbers", "general-purpose", None),
]
for msg, agent, want in HANDBACK:
    got = hb(msg, agent)
    if got != want:
        fails += 1; print(f"FAIL handback {msg!r} agent={agent}: want {want} got {got}")

def ar(tool_input, tool_response):
    r = run("agent_result", {"tool_input": tool_input, "tool_response": tool_response})
    return "flag" if r and "additionalContext" in r.get("hookSpecificOutput", {}) else None

WA = {"subagent_type": A}
RESULT = [  # shapes mirror the live 2026-10-15 toolUseResult
    (WA, {"status": "completed", "agentType": A, "handbackReport": {"text": "I didn't run anything."}}, "flag"),
    (WA, {"status": "completed", "agentType": A, "handbackReport": {"text": "STATUS: OK\nVERIFIED: no"}}, None),
    (WA, {"status": "completed", "agentType": A, "content": [{"type": "text", "text": "numbers only"}]}, "flag"),
    (WA, {"status": "completed", "agentType": A, "content": [{"type": "text", "text": "VERDICT: MATCH"}]}, None),
    (WA, {"status": "async_launched", "agentId": "x"}, None),
    ({"subagent_type": "general-purpose"}, {"status": "completed", "content": "no status here"}, None),
    (WA, "plain string response", None),
]
for ti, tr, want in RESULT:
    got = ar(ti, tr)
    if got != want:
        fails += 1; print(f"FAIL agent_result {tr!r}: want {want} got {got}")
n = len(CASES) + len(HANDBACK) + len(RESULT)
print(f"{'OK' if not fails else 'FAILED'} — {n - fails}/{n} cases pass"); sys.exit(1 if fails else 0)
