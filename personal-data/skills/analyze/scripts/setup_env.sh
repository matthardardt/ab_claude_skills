#!/bin/bash
# Environment bootstrap for the personal-data plugin. Idempotent; re-run any time.
#   1. Creates/verifies the ~/.venvs/abdata virtualenv (full package set — includes
#      scipy/sklearn/statsmodels, which experiment-design and code-draft depend on).
#   2. Installs rs + sql_guard.py + rs_query.py + ab-doctor to ~/.claude/bin — the
#      ONE stable runtime path every skill/agent references (fixes the
#      three-live-copies drift; rs_query.py's shebang is rewritten to the venv).
#   3. Runs the sql_guard golden corpus as an install gate.
set -euo pipefail

VENV="$HOME/.venvs/abdata"
BIN="$HOME/.claude/bin"
HERE="$(cd "$(dirname "$0")" && pwd -P)"

# pip names and import names differ (psycopg2-binary->psycopg2, scikit-learn->sklearn);
# keep the pairs adjacent so they cannot drift apart.
PAIRS=(
    "psycopg2-binary:psycopg2"
    "pandas:pandas"
    "matplotlib:matplotlib"
    "plotly:plotly"
    "scipy:scipy"
    "scikit-learn:sklearn"
    "statsmodels:statsmodels"
)
PIP_PKGS=(); IMPORT_MODS=()
for p in "${PAIRS[@]}"; do PIP_PKGS+=("${p%%:*}"); IMPORT_MODS+=("${p##*:}"); done
IMPORT_LIST="$(IFS=', '; echo "${IMPORT_MODS[*]}")"

# --- 1. venv ---
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import ${IMPORT_LIST}" 2>/dev/null; then
    echo "setup_env: $VENV already has the full package set"
else
    [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet "${PIP_PKGS[@]}"
    "$VENV/bin/python" -c "import ${IMPORT_LIST}; print('setup_env: all imports ok')"
fi

# --- 2. golden corpus gate ---
python3 "$HERE/tests/test_sql_guard.py"

# --- 3. install to the stable runtime path ---
mkdir -p "$BIN"
# never let an older copy (e.g. a stale versioned cache) overwrite a newer install
ver() { sed -nE 's/^RS_VERSION="([^"]+)".*/\1/p' "$1" 2>/dev/null; }
NEW_VER="$(ver "$HERE/rs")"; OLD_VER="$(ver "$BIN/rs")"
if [ -n "$OLD_VER" ] && [ "$OLD_VER" != "$NEW_VER" ] \
   && [ "$(printf '%s\n%s\n' "$OLD_VER" "$NEW_VER" | sort -V | tail -1)" = "$OLD_VER" ] \
   && [ "${FORCE_DOWNGRADE:-}" != "1" ]; then
    echo "setup_env: refusing to downgrade ~/.claude/bin/rs $OLD_VER -> $NEW_VER (from $HERE). Run from the newest copy, or FORCE_DOWNGRADE=1." >&2
    exit 1
fi
install -m 0755 "$HERE/rs" "$BIN/rs"
install -m 0755 "$HERE/sql_guard.py" "$BIN/sql_guard.py"
# rewrite rs_query.py's shebang to this machine's venv python
{ printf '#!%s\n' "$VENV/bin/python"; tail -n +2 "$HERE/rs_query.py"; } > "$BIN/rs_query.py"
chmod 0755 "$BIN/rs_query.py"
# ab-doctor lives beside these scripts (travels into the loader cache); install it too
if [ -f "$HERE/ab-doctor" ]; then
    install -m 0755 "$HERE/ab-doctor" "$BIN/ab-doctor"
else
    echo "setup_env: WARNING — ab-doctor not found at $HERE/ab-doctor; SessionStart health check will be missing" >&2
fi

echo "setup_env: installed to $BIN —"
"$BIN/rs" version
