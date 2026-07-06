#!/usr/bin/env python3
"""Golden corpus for sql_guard.py — run after ANY change to the validator:
    python3 tests/test_sql_guard.py
Seeded with the empirically-proven divergences between the old bash/python
validators (2026-07-06 review) plus bypass attempts. Zero deps beyond stdlib.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sql_guard import GuardError, needs_limit, validate_readonly  # noqa: E402

ALLOW = [
    # bread and butter
    "select 1",
    "SELECT paid_at, amount_dollars FROM production_core_tables.joined_lineitems WHERE is_paid IS TRUE AND is_tip IS FALSE AND is_refunded IS FALSE",
    "with base as (select entity_id from production_core_tables.agg_contributions) select count(*) from base",
    "explain select count(*) from production_core_tables.joined_lineitems where paid_at >= '2026-06-01'",
    "show search_path",
    # snake_case identifiers containing blocked words (old validators passed these; keep it so)
    "select created_at, deleted_at, last_updated, refunded_at from foo",
    # literals containing keywords (single-line and MULTILINE — old bash blocked multiline)
    "select * from audits where action = 'delete'",
    "select 'line one\ndelete this text later' as note",
    "select 'it''s an escaped quote, drop table nothing' as s",
    # double-quoted identifiers containing keywords (old validators blocked all of these)
    'select count(*) as "soft delete count" from foo',
    'select x as "create date" from foo',
    'select "comment" from svv_table_info',
    'select "set" from foo',
    # comment handling (old bash rejected leading comments and ; inside comments)
    "-- daily pull\nselect 1",
    "/* block\ncomment; with semicolon */ select 1",
    "select 1 -- trailing note",
    "select /* nested /* inner */ still comment */ 1",
    # trailing semicolon is fine (single statement)
    "select 1;",
]

BLOCK = [
    "drop table foo",
    "delete from foo where 1=1",
    "insert into foo values (1)",
    "update foo set x = 1",
    "create table foo (x int)",
    "truncate foo",
    "grant select on foo to bar",
    "copy foo from 's3://bucket'",
    "unload ('select 1') to 's3://bucket'",
    "select 1 into foo",
    "vacuum foo",
    "refresh materialized view mv_foo",
    "analyze foo",
    "call my_proc()",
    "comment on table foo is 'x'",
    "set search_path to prod",
    "begin; drop table foo",
    # multi-statement smuggling (incl. the newline variant that diverged before)
    "select 1; drop table foo",
    "select 1;\nrefresh materialized view x",
    "select 1; select 2",
    # keyword hidden AFTER a literal-with-escape (lexer must not desync)
    "select 'a''b' as s; delete from foo",
    # first-word gate
    "with foo as (select 1) delete from bar",
    "",
    "   -- only a comment",
]

# (sql, expect_append)
LIMIT_CASES = [
    ("select * from big_table", True),
    ("select * from big_table limit 10", False),
    ("select * from big_table limit 10 offset 5", False),
    ("select * from big_table limit all", False),
    # inner subquery LIMIT must NOT suppress the outer cap (old bash bug)
    ("select * from t where id in (select id from u limit 5)", True),
    # trailing comment must NOT suppress the cap or swallow it (old bash bug)
    ("select * from t -- pull everything", True),
    ("select * from t limit 10 -- capped", False),
    ("select * from t limit 10;", False),
    # explain/show never get a cap appended
    ("explain select * from t", False),
    ("show search_path", False),
]


def main() -> int:
    failures = []
    for sql in ALLOW:
        try:
            validate_readonly(sql)
        except GuardError as e:
            failures.append(f"ALLOW failed: {sql!r} -> {e}")
    for sql in BLOCK:
        try:
            validate_readonly(sql)
            failures.append(f"BLOCK failed (was allowed): {sql!r}")
        except GuardError:
            pass
    for sql, expect in LIMIT_CASES:
        got = needs_limit(sql)
        if got != expect:
            failures.append(f"needs_limit({sql!r}) = {got}, expected {expect}")
    total = len(ALLOW) + len(BLOCK) + len(LIMIT_CASES)
    if failures:
        print(f"FAIL — {len(failures)}/{total}:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"OK — {total} cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
