#!/usr/bin/env bash
# run_prod.sh  –  Start the Flask backend with gunicorn (4 async workers)
# Usage: bash run_prod.sh
# Requires: gunicorn installed in your venv  (pip install gunicorn)

cd "$(dirname "$0")"

# Activate venv if it exists
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
  source venv/Scripts/activate
fi

PORT=${PORT:-5000}

exec gunicorn app:app \
  --workers 4 \
  --threads 2 \
  --worker-class gthread \
  --timeout 300 \
  --bind 0.0.0.0:$PORT \
  --log-level info
