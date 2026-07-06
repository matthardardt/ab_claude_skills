#!/Users/mhardardt/.venvs/abdata/bin/python
"""rs_query.py — read-only Redshift query runner for the personal-data:analyze skill.

Runs a SELECT against the warehouse, writes results to CSV, and prints a profile
(shape, dtypes, nulls, numeric summary, head) so the calling agent gets immediate
data sense without re-reading the file.

IMPORTANT SCOPE: this script opens a READ-ONLY session, and Redshift rejects
external/Spectrum tables inside read-only transactions — so it can only query
LOCAL objects (svv_* catalogs, dbt_* schemas). For production_*, indigo_aurora,
or mixpanel tables use the `rs` wrapper instead: rs csv "<query>" out.csv
(then profile the CSV here with --profile-csv).

Usage:
    rs_query.py "<sql>" -o results.csv [--timeout 300] [--no-profile]
    rs_query.py --file query.sql -o results.csv
    rs_query.py --profile-csv results.csv [--key <grain_column>]   # no warehouse contact

Credentials: REDSHIFT_* env vars, falling back to `export REDSHIFT_*` lines in
~/.zshrc. Read-only validation is delegated to sql_guard.py (the same validator
the `rs` wrapper uses — do not add separate rules here).
"""

import argparse
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sql_guard import GuardError, validate_readonly  # noqa: E402


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


def coerce_decimals(df: pd.DataFrame) -> pd.DataFrame:
    """psycopg2 returns NUMERIC as decimal.Decimal (object dtype), which the numeric
    summary would silently skip — exactly the money columns. Coerce to float."""
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna()
            if not sample.empty and isinstance(sample.iloc[0], Decimal):
                df[col] = df[col].astype(float)
    return df


def profile(df: pd.DataFrame, key: str | None = None):
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
    if key:
        if key in df.columns:
            n, d = len(df), df[key].nunique(dropna=False)
            flag = "OK — one row per key" if n == d else f"FAN-OUT? {n:,} rows vs {d:,} distinct {key}"
            print(f"\n=== grain check on '{key}': {flag} ===")
        else:
            print(f"\n=== grain check: column '{key}' not in result ===")
    print("\n=== head(10) ===")
    print(df.head(10).to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?", help="SQL text (or use --file / --profile-csv)")
    ap.add_argument("--file", "-f", help="path to a .sql file")
    ap.add_argument("--out", "-o", help="output CSV path")
    ap.add_argument("--timeout", type=int, default=300, help="statement timeout, seconds (default 300)")
    ap.add_argument("--no-profile", action="store_true", help="skip the profile printout")
    ap.add_argument("--profile-csv", help="profile an existing CSV (e.g. from `rs csv`) — no warehouse contact")
    ap.add_argument("--key", help="grain column: print count(*) vs count(distinct key) fan-out check")
    args = ap.parse_args()

    if args.profile_csv:
        df = pd.read_csv(args.profile_csv)
        profile(df, key=args.key)
        return

    if args.file:
        sql = Path(args.file).read_text()
    elif args.sql:
        sql = args.sql
    else:
        ap.error("provide SQL text, --file, or --profile-csv")

    try:
        validate_readonly(sql)
    except GuardError as e:
        sys.exit(f"rs_query: {e}")
    creds = load_creds()

    import psycopg2  # deferred so --profile-csv works without a DB driver present

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
            try:
                cur.execute(sql)
            except psycopg2.Error as e:
                if "read-only" in str(e).lower():
                    sys.exit(
                        "rs_query: this query touches an external/Spectrum schema "
                        "(production_*, indigo_aurora, mixpanel), which rs_query.py cannot reach — "
                        "its session is read-only by design and Redshift rejects external tables "
                        "in read-only transactions.\n"
                        "Use the rs wrapper instead:  rs csv \"<query>\" out.csv\n"
                        "then profile the file:       rs_query.py --profile-csv out.csv [--key <grain_col>]"
                    )
                sys.exit(f"rs_query: query failed —\n{e}")
            columns = [d[0] for d in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=columns)
    finally:
        conn.close()

    df = coerce_decimals(df)
    if args.out:
        df.to_csv(args.out, index=False)
        print(f"rs_query: wrote {len(df):,} rows to {args.out}")
    if not args.no_profile:
        profile(df, key=args.key)


if __name__ == "__main__":
    main()
