#!/usr/bin/env bash
set -euo pipefail

# Write the FIREBASE_SERVICE_ACCOUNT_JSON to a file if provided.
if [ -n "${FIREBASE_SERVICE_ACCOUNT_JSON:-}" ]; then
  mkdir -p /srv
  printf '%s' "$FIREBASE_SERVICE_ACCOUNT_JSON" > /srv/service-account.json
  export GOOGLE_APPLICATION_CREDENTIALS="/srv/service-account.json"
fi

# Start the app using gunicorn
exec gunicorn payhero_server:app --bind 0.0.0.0:"${PORT:-8000}" --workers 2
