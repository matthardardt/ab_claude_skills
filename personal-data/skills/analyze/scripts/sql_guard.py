#!/usr/bin/env python3
"""sql_guard.py — the single read-only SQL validator shared by `rs` (bash) and rs_query.py.

Both tools MUST delegate here; do not reimplement validation elsewhere. Golden
corpus lives in tests/test_sql_guard.py — run it after any change to this file.

CLI (used by the bash wrapper; query text arrives on stdin to dodge quoting):
    printf '%s' "$SQL" | sql_guard.py check         # exit 0 ok / exit 2 blocked (reason on stderr)
    printf '%s' "$SQL" | sql_guard.py needs-limit   # exit 0 = append a LIMIT / exit 1 = don't
    printf '%s' "$SQL" | sql_guard.py strip-tail    # print SQL with trailing comments/semicolons removed

Python API (used by rs_query.py):
    from sql_guard import validate_readonly, needs_limit, strip_tail, GuardError

Design notes:
- A single left-to-right STATE-MACHINE scanner segments the buffer into code /
  string ('' escapes) / dollar-quote / double-quoted identifier / line comment /
  nested block comment in ONE pass. Ordered regex passes are NOT safe here: an
  apostrophe inside a comment (-- don't) would desync a strings-first lexer and
  let `; drop ...` through — proven bypass, hence the scanner.
- Double-quoted identifiers are replaced with a neutral token, so a column
  literally named comment/set/copy is usable by quoting it: select "comment" from t.
- The scanner must lex EXACTLY like Redshift, or text the guard thinks is a
  literal/comment executes as code (2026-10-15 review, proven live). Redshift
  rules mirrored here: backslash escapes inside '...' strings (\' does not close
  the string); `--` comments end at \n OR \r; `$` is an identifier character, so
  `a$b$` is a name, not the start of a dollar quote. Dollar quotes have no
  read-only use and are rejected outright.
- Side-effecting functions callable from a SELECT (set_config,
  pg_terminate_backend, ...) are blocked by name.
- needs_limit is TAIL-anchored: an inner subquery LIMIT no longer suppresses the
  outer row cap. A leading `select [distinct] top N` also counts as capped.
- strip_tail removes trailing whitespace, trailing comments, and terminal
  semicolons from the RAW text (comment-aware), so `rs` can safely append
  `limit N` or wrap in EXPLAIN even when the query ends `; -- done`.
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

_DOLLAR_TAG = re.compile(r"\$(\w*)\$")

SIDE_EFFECT_FUNCS = re.compile(
    r"\b(set_config|pg_terminate_backend|pg_cancel_backend|pg_reload_conf|pg_rotate_logfile"
    r"|pg_advisory_\w+|pg_try_advisory_\w+|dblink\w*|lo_\w+)\s*\("
)


class GuardError(Exception):
    pass


def _segments(sql: str):
    """Single-pass scanner. Yields (start, end, kind) covering the whole buffer;
    kind in {'code','string','dollar','ident','lcomment','bcomment'}."""
    segs = []
    i, n = 0, len(sql)
    code_start = 0

    def flush_code(upto):
        if upto > code_start:
            segs.append((code_start, upto, "code"))

    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if c == "'":
            flush_code(i)
            j = i + 1
            while j < n:
                if sql[j] == "\\":
                    j += 2  # Redshift: backslash escapes the next char, incl. a quote
                    continue
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            end = min(j + 1, n)
            segs.append((i, end, "string"))
            i = end
            code_start = i
        elif c == '"':
            flush_code(i)
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            end = min(j + 1, n)
            segs.append((i, end, "ident"))
            i = end
            code_start = i
        elif c == "$":
            prev = sql[i - 1] if i > 0 else ""
            m = None if (prev.isalnum() or prev in "_$") else _DOLLAR_TAG.match(sql, i)
            if m:
                flush_code(i)
                tag = m.group(0)
                close = sql.find(tag, m.end())
                end = n if close == -1 else close + len(tag)
                segs.append((i, end, "dollar"))
                i = end
                code_start = i
            else:
                i += 1
        elif c == "-" and nxt == "-":
            flush_code(i)
            ends = [k for k in (sql.find("\n", i), sql.find("\r", i)) if k != -1]
            end = min(ends) if ends else n  # the line break itself stays code
            segs.append((i, end, "lcomment"))
            i = end
            code_start = i
        elif c == "/" and nxt == "*":
            flush_code(i)
            depth = 1
            j = i + 2
            while j < n and depth:
                if sql[j] == "/" and j + 1 < n and sql[j + 1] == "*":
                    depth += 1
                    j += 2
                elif sql[j] == "*" and j + 1 < n and sql[j + 1] == "/":
                    depth -= 1
                    j += 2
                else:
                    j += 1
            segs.append((i, j, "bcomment"))
            i = j
            code_start = i
        else:
            i += 1
    flush_code(n)
    return segs


def normalize(sql: str) -> str:
    """Neutralize literals/identifiers/comments; lowercase the remaining code."""
    parts = []
    for s, e, k in _segments(sql):
        if k in ("string", "dollar"):
            parts.append("''")
        elif k == "ident":
            parts.append(" qident ")
        elif k in ("lcomment", "bcomment"):
            parts.append(" ")
        else:
            parts.append(sql[s:e])
    return "".join(parts).lower()


def strip_tail(sql: str) -> str:
    """Remove trailing whitespace, trailing comments, and terminal semicolons
    from the raw text (comment-aware). Interior comments are preserved."""
    segs = _segments(sql)
    for s, e, k in reversed(segs):
        if k in ("lcomment", "bcomment"):
            continue
        if k == "code":
            frag = sql[s:e]
            while True:
                frag = frag.rstrip()
                if frag.endswith(";"):
                    frag = frag[:-1]
                else:
                    break
            if not frag:
                continue  # segment was only whitespace/semicolons — keep trimming
            return sql[: s + len(frag)]
        return sql[:e]  # string/dollar/ident segment ends the tail scan
    return ""


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
    if any(k == "dollar" for _, _, k in _segments(sql)):
        raise GuardError("blocked — dollar-quoted strings are not allowed in read-only queries")
    hit = SIDE_EFFECT_FUNCS.search(norm)
    if hit:
        raise GuardError(f"blocked — side-effecting function: {hit.group(1)}")


def needs_limit(sql: str, first_words_exempt=("explain", "show")) -> bool:
    """True if a row cap should be appended (no terminal LIMIT, not explain/show)."""
    norm = normalize(sql)
    words = re.findall(r"[a-z_]+", norm)
    if not words or words[0] in first_words_exempt:
        return False
    if re.match(r"\s*select\s+(distinct\s+)?top\s+\d+\b", norm):
        return False
    tail = norm.rstrip().rstrip(";").rstrip()
    return not re.search(r"\blimit\s+(\d+|all)(\s+offset\s+\d+)?$", tail)


def main() -> int:
    modes = ("check", "needs-limit", "strip-tail")
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        print(f"usage: sql_guard.py {{{'|'.join(modes)}}}  (SQL on stdin)", file=sys.stderr)
        return 64
    sql = sys.stdin.read()
    if sys.argv[1] == "check":
        try:
            validate_readonly(sql)
        except GuardError as e:
            print(f"sql_guard: {e}", file=sys.stderr)
            return 2
        return 0
    if sys.argv[1] == "strip-tail":
        sys.stdout.write(strip_tail(sql))
        return 0
    return 0 if needs_limit(sql) else 1


if __name__ == "__main__":
    sys.exit(main())
