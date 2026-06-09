#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/meter-ocr}"

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip libzbar0 libgl1 libglib2.0-0 tesseract-ocr

sudo mkdir -p "$APP_DIR"
sudo rsync -a --exclude .venv --exclude __pycache__ ./ "$APP_DIR/"
cd "$APP_DIR"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

sudo cp deploy/meter-ocr.service /etc/systemd/system/meter-ocr.service
sudo systemctl daemon-reload
sudo systemctl enable meter-ocr
sudo systemctl restart meter-ocr

echo "Service started. Check: curl http://127.0.0.1:8080/health"
