#!/usr/bin/env python3
"""sql_guard.py — the single read-only SQL validator shared by `rs` (bash) and rs_query.py.

Both tools MUST delegate here; do not reimplement validation elsewhere. Golden
corpus lives in tests/test_sql_guard.py — run it after any change to this file.

CLI (used by the bash wrapper; query text arrives on stdin to dodge quoting):
    printf '%s' "$SQL" | sql_guard.py check         # exit 0 ok / exit 2 blocked (reason on stderr)
    printf '%s' "$SQL" | sql_guard.py needs-limit   # exit 0 = append a LIMIT / exit 1 = don't

Python API (used by rs_query.py):
    from sql_guard import validate_readonly, needs_limit, GuardError

Design notes:
- Lexes the WHOLE buffer (multiline literals, '' escapes, dollar-quoting, nested
  block comments) before keyword checks — per-line sed cannot do this and the old
  bash/python pair had already diverged.
- Double-quoted identifiers are replaced with a neutral token, so a column
  literally named comment/set/copy is usable by quoting it: select "comment" from t.
- needs_limit is TAIL-anchored: an inner subquery LIMIT no longer suppresses the
  outer row cap.
"""

import re
import sys

FIRST_WORDS = ("select", "with", "explain", "show")

# Write/DDL keywords blocked anywhere in a normalized statement. `into` catches
# SELECT INTO; `set`/`comment`/`call` etc. as *bare* identifiers are blocked too —
# the documented escape hatch is to double-quote the identifier.
WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|create|alter|truncate|grant|revoke|copy"
    r"|unload|merge|call|vacuum|analyze|refresh|into|set|begin|commit|rollback|lock|comment)\b"
)

_BLOCK_COMMENT = re.compile(r"/\*(?:[^*/]|\*(?!/)|/(?!\*))*\*/", re.DOTALL)


class GuardError(Exception):
    pass


def normalize(sql: str) -> str:
    """Strip literals, quoted identifiers, and comments; lowercase the rest."""
    s = sql
    # dollar-quoted strings ($$...$$ or $tag$...$tag$), then single-quoted
    # literals with '' escapes (multiline-safe), then double-quoted identifiers
    s = re.sub(r"\$(\w*)\$.*?\$\1\$", "''", s, flags=re.DOTALL)
    s = re.sub(r"'(?:[^']|'')*'", "''", s, flags=re.DOTALL)
    s = re.sub(r'"(?:[^"]|"")*"', " qident ", s, flags=re.DOTALL)
    # line comments, then block comments (loop handles Postgres-style nesting)
    s = re.sub(r"--[^\n]*", "", s)
    prev = None
    while prev != s:
        prev = s
        s = _BLOCK_COMMENT.sub(" ", s)
    return s.lower()


def validate_readonly(sql: str) -> None:
    """Raise GuardError unless sql is a single read-only statement."""
    norm = normalize(sql)
    words = re.findall(r"[a-z_]+", norm)
    if not words or words[0] not in FIRST_WORDS:
        raise GuardError(
            f"blocked — statement must start with SELECT/WITH/EXPLAIN/SHOW "
            f"(got: {words[0] if words else 'empty'})"
        )
    hit = WRITE_KEYWORDS.search(norm)
    if hit:
        raise GuardError(
            f"blocked — write/DDL keyword detected: {hit.group(1)} (read-only access only). "
            f'If this is a column/identifier name, double-quote it: "{hit.group(1)}"'
        )
    if ";" in norm.rstrip().rstrip(";"):
        raise GuardError("blocked — multiple statements not allowed")


def needs_limit(sql: str, first_words_exempt=("explain", "show")) -> bool:
    """True if a row cap should be appended (no terminal LIMIT, not explain/show)."""
    norm = normalize(sql)
    words = re.findall(r"[a-z_]+", norm)
    if not words or words[0] in first_words_exempt:
        return False
    tail = norm.rstrip().rstrip(";").rstrip()
    return not re.search(r"\blimit\s+(\d+|all)(\s+offset\s+\d+)?$", tail)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("check", "needs-limit"):
        print("usage: sql_guard.py {check|needs-limit}  (SQL on stdin)", file=sys.stderr)
        return 64
    sql = sys.stdin.read()
    if sys.argv[1] == "check":
        try:
            validate_readonly(sql)
        except GuardError as e:
            print(f"sql_guard: {e}", file=sys.stderr)
            return 2
        return 0
    return 0 if needs_limit(sql) else 1


if __name__ == "__main__":
    sys.exit(main())
