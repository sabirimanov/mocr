# aaPanel deployment guide (Git)

Deploy the Meter OCR API on Ubuntu with aaPanel, Git, Supervisor, and Nginx reverse proxy.

## Prerequisites

- Ubuntu server with [aaPanel](https://www.aapanel.com/) installed
- A domain or subdomain (optional but recommended), e.g. `ocr.example.com`
- Git repository (GitHub / GitLab / Gitee) containing this project

## Step 1 — Push code to Git

On your local machine:

```bash
cd /path/to/METERS
git init
git add .
git commit -m "Initial meter OCR service"
git remote add origin git@github.com:YOUR_USER/meter-ocr.git
git push -u origin main
```

Use HTTPS if you prefer:

```bash
git remote add origin https://github.com/YOUR_USER/meter-ocr.git
```

## Step 2 — Install aaPanel plugins

In aaPanel web UI:

1. **App Store**
2. Install if missing:
   - **Nginx**
   - **Git** (optional; SSH is enough)
   - **Supervisor** (process manager)

## Step 3 — Install system libraries (SSH)

Open **aaPanel → Terminal** (or SSH into the server):

```bash
apt-get update
apt-get install -y python3 python3-venv python3-pip git \
  libzbar0 libgl1 libglib2.0-0
```

## Step 4 — Clone the repository

```bash
mkdir -p /www/wwwroot
cd /www/wwwroot

# SSH key (recommended)
git clone git@github.com:YOUR_USER/meter-ocr.git meter-ocr

# or HTTPS
# git clone https://github.com/YOUR_USER/meter-ocr.git meter-ocr

cd meter-ocr
chown -R www:www /www/wwwroot/meter-ocr
```

## Step 5 — Create Python virtualenv and install deps

```bash
cd /www/wwwroot/meter-ocr

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

First install downloads OCR models (~30 MB) — can take a few minutes.

Test locally on the server:

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

In another terminal:

```bash
curl http://127.0.0.1:8080/health
# {"status":"ok"}
```

Press `Ctrl+C` to stop the test server.

## Step 6 — Register Supervisor job

Copy the included config:

```bash
cp /www/wwwroot/meter-ocr/deploy/supervisor-meter-ocr.conf \
  /www/server/panel/plugin/supervisor/profile/meter-ocr.conf
```

Or in aaPanel UI:

1. **Supervisor → Add daemon**
2. Fill in:

| Field | Value |
|-------|-------|
| Name | `meter-ocr` |
| Run directory | `/www/wwwroot/meter-ocr` |
| Start command | `/www/wwwroot/meter-ocr/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080` |
| User | `www` |
| Log file | `/www/wwwlogs/meter-ocr.log` |

3. Save and **Start**

Verify:

```bash
supervisorctl status meter-ocr
curl http://127.0.0.1:8080/health
```

## Step 7 — Create website + reverse proxy in aaPanel

1. **Website → Add site**
   - Domain: `ocr.example.com` (or your subdomain)
   - Root: `/www/wwwroot/meter-ocr` (not used for static files; required by aaPanel)
   - PHP: **Pure static** / disable PHP

2. Open the site → **Reverse proxy → Add reverse proxy**
   - Proxy name: `meter-ocr`
   - Target URL: `http://127.0.0.1:8080`
   - Send domain: `$host`
   - Enable proxy

3. **SSL** (recommended): site → **SSL → Let's Encrypt → Apply**

Nginx config should look similar to:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
}
```

OCR can take several seconds on CPU — keep `proxy_read_timeout` at 120s or higher.

## Step 8 — Test public endpoint

```bash
curl https://ocr.example.com/health
curl -X POST https://ocr.example.com/ocr \
  -H "Content-Type: application/json" \
  -d '{"image_url":"https://example.com/meter.jpg","meter_type":"pf"}'
```

API docs: `https://ocr.example.com/docs`

## Step 9 — Deploy updates via Git

On the server after you push new commits:

```bash
cd /www/wwwroot/meter-ocr
git pull
bash deploy/update.sh
```

Or manually:

```bash
git pull
.venv/bin/pip install -r requirements.txt
supervisorctl restart meter-ocr
```

### Optional: aaPanel Webhook / cron

For simple auto-deploy on push, add a **Shell script** cron or use your Git provider’s webhook calling:

```bash
cd /www/wwwroot/meter-ocr && git pull && bash deploy/update.sh
```

## Firewall

In aaPanel **Security**:

- Open **80** and **443**
- Do **not** expose port **8080** publicly — only Nginx should reach it on localhost

## Environment variables

Edit Supervisor config or aaPanel daemon env:

| Variable | Default | Purpose |
|----------|---------|---------|
| `METER_OCR_PORT` | `8080` | Internal port |
| `METER_OCR_DOWNLOAD_TIMEOUT_SECONDS` | `30` | Image download timeout |
| `METER_OCR_MAX_IMAGE_BYTES` | `15728640` | Max image size |

After changing env, restart: `supervisorctl restart meter-ocr`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `libzbar.so not found` | `apt install libzbar0` |
| OpenCV errors | `apt install libgl1 libglib2.0-0` |
| 502 Bad Gateway | Check `supervisorctl status meter-ocr` and logs at `/www/wwwlogs/meter-ocr.log` |
| Slow first request | Normal — OCR model loads on startup; Supervisor `startsecs=10` helps |
| Permission denied | `chown -R www:www /www/wwwroot/meter-ocr` |

## Alternative: systemd instead of Supervisor

If you prefer systemd:

```bash
sudo cp deploy/meter-ocr.service /etc/systemd/system/
# Edit paths in the service file to /www/wwwroot/meter-ocr and User=www
sudo systemctl daemon-reload
sudo systemctl enable --now meter-ocr
```

Use either Supervisor **or** systemd, not both.
