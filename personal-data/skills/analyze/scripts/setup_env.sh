#!/bin/bash
# One-time environment bootstrap for the personal-data:analyze skill.
# Creates the ~/.venvs/abdata virtualenv used by rs_query.py and chart generation.
set -euo pipefail

VENV="$HOME/.venvs/abdata"

if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import psycopg2, pandas, matplotlib, plotly" 2>/dev/null; then
    echo "setup_env: $VENV already set up"
    exit 0
fi

python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet psycopg2-binary pandas matplotlib plotly
"$VENV/bin/python" -c "import psycopg2, pandas, matplotlib, plotly; print('setup_env: all imports ok')"
