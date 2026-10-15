#!/Users/mhardardt/.venvs/abdata/bin/python
"""rs_query.py — read-only Redshift query runner for the personal-data:analyze skill.

Runs a SELECT against the warehouse, writes results to CSV, and prints a profile
(shape, dtypes, nulls, numeric summary, head) so the calling agent gets immediate
data sense without re-reading the file.

SCOPE: the session is read-only + autocommit. External/Spectrum schemas
(production_*, indigo_aurora, mixpanel) used to fail here with "transaction is
read-only"; as of 2026-10-15 they work (1-row joined_lineitems pull verified).
If that error comes back, fall back to `rs csv "<query>" out.csv` and profile the
CSV with --profile-csv. The read-only session is NOT a security control — the
login itself can write to dev schemas; sql_guard is the gate.

Usage:
    rs_query.py "<sql>" -o results.csv [--force] [--timeout 300] [--max-rows N] [--no-profile]
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


def check_out_path(out, force):
    """Same containment rules as `rs csv`: .csv only, inside the CWD (symlinks
    resolved), no silent overwrite."""
    p = Path(out)
    if p.suffix != ".csv":
        sys.exit(f"rs_query: output path must end in .csv (got: {out})")
    parent = p.parent.resolve()
    cwd = Path.cwd().resolve()
    if parent != cwd and cwd not in parent.parents:
        sys.exit(f"rs_query: output path must be inside the current working directory (got: {parent})")
    if (p.exists() or p.is_symlink()) and not force:
        sys.exit(f"rs_query: refusing to overwrite existing {out} (pass --force)")
    if p.is_symlink():
        sys.exit(f"rs_query: refusing to write through a symlink: {out}")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?", help="SQL text (or use --file / --profile-csv)")
    ap.add_argument("--file", "-f", help="path to a .sql file")
    ap.add_argument("--out", "-o", help="output CSV path (must end .csv and sit inside the CWD)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing --out file")
    ap.add_argument("--max-rows", type=int, default=2_000_000, help="abort if the result exceeds this many rows (default 2,000,000)")
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
    if not 1 <= args.timeout <= 3600:
        sys.exit("rs_query: --timeout must be 1..3600 seconds")
    out_path = check_out_path(args.out, args.force) if args.out else None
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
            rows = []
            while True:
                batch = cur.fetchmany(50_000)
                if not batch:
                    break
                rows.extend(batch)
                if len(rows) > args.max_rows:
                    sys.exit(f"rs_query: result exceeds --max-rows {args.max_rows:,}; aggregate in SQL or raise the cap")
            df = pd.DataFrame(rows, columns=columns)
    finally:
        conn.close()

    df = coerce_decimals(df)
    if out_path:
        df.to_csv(out_path, index=False)
        print(f"rs_query: wrote {len(df):,} rows to {args.out}")
    if not args.no_profile:
        profile(df, key=args.key)


if __name__ == "__main__":
    main()
