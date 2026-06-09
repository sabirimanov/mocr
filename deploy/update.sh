#!/usr/bin/env bash
# Run after git pull on the server to update dependencies and restart the service.
set -euo pipefail

APP_DIR="${APP_DIR:-/www/wwwroot/meter-ocr}"
cd "$APP_DIR"

.venv/bin/pip install -r requirements.txt

if command -v supervisorctl >/dev/null 2>&1; then
  supervisorctl restart meter-ocr
elif systemctl is-active --quiet meter-ocr 2>/dev/null; then
  sudo systemctl restart meter-ocr
else
  echo "Restart manually: supervisorctl restart meter-ocr"
fi

echo "Deploy complete. Health check:"
curl -fsS http://127.0.0.1:8080/health && echo
