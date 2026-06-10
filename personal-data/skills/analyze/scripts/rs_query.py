#!/Users/mhardardt/.venvs/abdata/bin/python
"""rs_query.py — read-only Redshift query runner for the personal-data:analyze skill.

Runs a SELECT against the warehouse, writes results to CSV, and prints a profile
(shape, dtypes, nulls, numeric summary, head) so the calling agent gets immediate
data sense without re-reading the file.

Usage:
    rs_query.py "<sql>" -o results.csv [--timeout 300] [--no-profile]
    rs_query.py --file query.sql -o results.csv

Credentials: REDSHIFT_* env vars, falling back to `export REDSHIFT_*` lines in ~/.zshrc.
Enforces the same read-only rules as the `rs` wrapper.
"""

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd
import psycopg2

WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|create|alter|truncate|grant|revoke|copy"
    r"|unload|merge|call|vacuum|into|set|begin|commit|rollback|lock|comment)\b"
)


def load_creds():
    keys = ["REDSHIFT_HOST", "REDSHIFT_PORT", "REDSHIFT_DB", "REDSHIFT_USERNAME", "REDSHIFT_PASSWORD"]
    if not all(os.environ.get(k) for k in keys):
        zshrc = Path.home() / ".zshrc"
        if zshrc.exists():
            for line in zshrc.read_text().splitlines():
                m = re.match(r"^export (REDSHIFT_\w+)=['\"]?([^'\"]*)['\"]?\s*$", line)
                if m:
                    os.environ.setdefault(m.group(1), m.group(2))
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        sys.exit(f"rs_query: missing credentials: {', '.join(missing)} (expected in env or ~/.zshrc)")
    return {k: os.environ[k] for k in keys}


def normalize(sql: str) -> str:
    sql = re.sub(r"'[^']*'", "''", sql)
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql.lower()


def validate_readonly(sql: str):
    norm = normalize(sql)
    words = re.findall(r"[a-z_]+", norm)
    if not words or words[0] not in ("select", "with", "explain", "show"):
        sys.exit(f"rs_query: blocked — statement must start with SELECT/WITH/EXPLAIN/SHOW (got: {words[0] if words else 'empty'})")
    hit = WRITE_KEYWORDS.search(norm)
    if hit:
        sys.exit(f"rs_query: blocked — write/DDL keyword detected: {hit.group(1)} (read-only access only)")
    if ";" in norm.rstrip().rstrip(";"):
        sys.exit("rs_query: blocked — multiple statements not allowed")


def profile(df: pd.DataFrame):
    print(f"\n=== profile: {df.shape[0]:,} rows x {df.shape[1]} cols ===")
    info = pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "nulls": df.isna().sum(),
        "null_pct": (df.isna().mean() * 100).round(1),
        "n_unique": df.nunique(),
    })
    print(info.to_string())
    numeric = df.select_dtypes("number")
    if not numeric.empty:
        print("\n=== numeric summary ===")
        print(numeric.describe().T.to_string())
    print("\n=== head(10) ===")
    print(df.head(10).to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?", help="SQL text (or use --file)")
    ap.add_argument("--file", "-f", help="path to a .sql file")
    ap.add_argument("--out", "-o", help="output CSV path")
    ap.add_argument("--timeout", type=int, default=300, help="statement timeout, seconds (default 300)")
    ap.add_argument("--no-profile", action="store_true", help="skip the profile printout")
    args = ap.parse_args()

    if args.file:
        sql = Path(args.file).read_text()
    elif args.sql:
        sql = args.sql
    else:
        ap.error("provide SQL text or --file")

    validate_readonly(sql)
    creds = load_creds()

    try:
        conn = psycopg2.connect(
            host=creds["REDSHIFT_HOST"],
            port=creds["REDSHIFT_PORT"],
            dbname=creds["REDSHIFT_DB"],
            user=creds["REDSHIFT_USERNAME"],
            password=creds["REDSHIFT_PASSWORD"],
            connect_timeout=10,
        )
    except psycopg2.OperationalError as e:
        sys.exit(f"rs_query: connection failed — check that you are on the AB VPN.\n{e}")

    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(f"set statement_timeout to {args.timeout * 1000}")
            cur.execute(sql)
            columns = [d[0] for d in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=columns)
    finally:
        conn.close()

    if args.out:
        df.to_csv(args.out, index=False)
        print(f"rs_query: wrote {len(df):,} rows to {args.out}")
    if not args.no_profile:
        profile(df)


if __name__ == "__main__":
    main()
