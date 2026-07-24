# Edge D.U.R.O. (Debian & Ubuntu Recipe Oven)

Automated image-building factory of the Edge ecosystem. A web-based control plane and background job runner for `mkosi` allowing users to visually configure, manage, and execute OS image recipes for Debian 12+ and Ubuntu 22+ (amd64/arm64) to produce monolithic provisioning artifacts (`.raw.xz`, `.iso`).

---

## 🏗️ Architecture & Tech Stack

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Celery, Redis, SSE log streaming.
- **Frontend:** React 19, TypeScript, Tailwind CSS 3, CodeMirror 6, Lucide Icons, Vite 8.
- **Database:** PostgreSQL 15.
- **Task Runner:** Celery Worker in privileged mode for `mkosi` systemd-nspawn build execution.
- **Deployment:** Docker Compose (6 isolated services).

---

## ✨ Recent Updates & Key System Features

### 📦 1. Dual-Card Visual Package Manager
The Web UI package selector divides packages into two interactive, searchable cards:
- **EDGE PLATFORM PACKAGES & DEPENDENCIES (Cyan Theme)**: Dedicated card for all 19 Edge target suite chips (`edge-base`, `edge-target-tools`, `edge-python3-psuctl`, `edge-target-uralan`, `edge-target-kaskad4`, `edge-target-puma`, `edge-target-skif`, `edge-target-wspaces7`, `edge-target-wspaces9`, `edge-target-trc`, `edge-target-roadeye3`, `edge-target-edges`, `edge-target-edges4`, `edge-mvs`, `edge-timekeeper`, `edge-zabbix-agent`, etc.).
- **STANDARD SYSTEM & CUSTOM APT PACKAGES (Amber Theme)**: Dedicated card for standard distribution utilities (`systemd`, `linux-image-amd64`, `nginx-full`, `openvpn`, `jq`, `rsyslog`, `usbutils`, `libmodbus5`, etc.).
- Both cards merge dynamically into `recipe.packages` for full customization.

### 🔒 2. HTTPS Repository Protocol & 301 Redirect Resolution
- Official Edge repositories use `https://edge.vitcompany.com/repo/bookworm/stable` (and `testing`).
- Solved silent APT package resolution failures caused by `HTTP 301 Moved Permanently` redirects during non-interactive chroot builds.
- Includes automatic startup migration in `backend/main.py` that upgrades any existing database recipes from `http://` to `https://`.

### ⚡ 3. Direct Pre-Download & Local Overlay Installer (`repo_downloader.py`)
- Python-level package fetcher (`backend/core/repo_downloader.py`) parses `Packages.gz` indices from configured HTTPS repositories before `mkosi` runs.
- Pre-downloads `edge-base` and selected `edge-*` platform `.deb` packages straight into `mkosi.extra/opt/edge_packages/`.
- Installs packages deterministically inside the rootfs via `dpkg -i` during post-install execution, ensuring 0 reliance on host APT quirks.

### 🏷️ 4. Dynamic Hostname from Active Port MAC Address
- When `hostname_from_netif` is enabled, target system hostname is automatically set equal to the raw 12-character MAC address of the active network installation port in **lowercase without colons or delimiters** (e.g. `525400123456`).
- Executes during post-installation and persists via `edge-firstboot.service` systemd unit.

### 🏷️ 5. Strict Versioned Artifact Naming Rules (`-auto` Suffix)
Both **ISO** installer and **RAW.XZ** disk image output artifacts strictly adhere to the unified versioned naming scheme:
- **ISO Installer**: `edge_${EDGE_BASE_VERSION}_${ARCH}-${RELEASE}-auto.iso`
  - *Example*: `edge_2026.3.0-18~testing+1371_amd64-bookworm-auto.iso`
- **RAW.XZ Disk Image**: `edge_${EDGE_BASE_VERSION}_${ARCH}-${RELEASE}-auto.raw.xz`
  - *Example*: `edge_2026.3.0-18~testing+1371_amd64-bookworm-auto.raw.xz`

### 🧹 6. Log Stream Throttling & Workspace Purging
- Real-time PTY stdout stream filtering in `backend/tasks/build_image.py` throttles repetitive percentage lines to 10% step increments.
- `prepare_workspace` automatically purges stale script hooks (`mkosi.postinst`, `mkosi.finalize`, `mkosi.prepare`) before launching new builds.

### 🌐 7. Multi-Language Support (i18n)
- Full internationalization support in English (EN), Russian (RU), and Ukrainian (UK).

---

## 🔌 Default Exposed Ports

| Service | Container Port | Host Port | Notes |
|---------|---------------|-----------|-------|
| **Frontend** | 3333 | `3333` | Web UI & Nginx API reverse proxy |
| **Backend** | 8000 | `8003` | FastAPI REST & SSE endpoints |
| **PostgreSQL** | 5432 | `5433` | Standalone DB instance |
| **Redis** | 6379 | `6380` | Task broker & PubSub log engine |

---

## 🚀 Remote Server Deployment Guide

### Prerequisites

- **OS:** Debian 11/12, Ubuntu 22.04/24.04, or RHEL/Rocky 9 Linux server.
- **Kernel / Capabilities:** Linux Kernel 5.15+ with loop device support enabled (`modprobe loop`).
- **Software:** `git`, `docker`, and Docker Compose v2 (`docker compose` plugin).

### Step 1: Clone Repository

```bash
git clone https://github.com/masseselsev/edge-duro.git /opt/edge-duro
cd /opt/edge-duro
```

### Step 2: Prepare Host Storage Directory & Permissions

Create the host data directory (e.g. `/data/duro` or `/mnt/nvme/duro_workspace`) and set non-root user permissions so Docker containers and system users can write build artifacts seamlessly:

```bash
# Create directory
sudo mkdir -p /data/duro

# Grant ownership to current non-root user
sudo chown -R $USER:$USER /data/duro

# Set standard write permissions
sudo chmod -R 775 /data/duro
```

### Step 3: Configure Environment Variables & Generate JWT Key

Create the `.env` configuration file:

```bash
cp .env.example .env
nano .env
```

#### Generating a Secure `JWT_SECRET_KEY`

To generate a cryptographically strong 256-bit secret key for JWT session tokens, run either of the following commands:

**Option A (OpenSSL):**
```bash
openssl rand -hex 32
```

**Option B (Python 3):**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated 64-character hexadecimal string into your `.env` file under `JWT_SECRET_KEY`.

#### Production `.env` Example

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=SetYourSecureDbPasswordHere
POSTGRES_DB=duro_image_builder
REDIS_URL=redis://redis:6379/0
DATABASE_URL=postgresql://postgres:SetYourSecureDbPasswordHere@db:5432/duro_image_builder

# Exposed Ports
BACKEND_PORT=8003

# Admin Authentication
SUPERADMIN_USERNAME=admin
ADMIN_PASSWORD=SetYourSecureSuperadminPasswordHere
JWT_SECRET_KEY=e8f9a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c3d5e7f9

# Host Workspace & Build Storage Mount Path
DURO_HOST_DATA_PATH=/data/duro
DURO_WORKSPACE_PATH=/opt/data/duro_workspace
```

### Step 4: Launch Containers

```bash
docker compose up -d --build
```

Verify service health:

```bash
docker compose ps
```

### Step 5: Access Web UI

Navigate to `http://<your-server-ip>:3333` in your web browser.

Default login:
- **Username:** `admin` (or `SUPERADMIN_USERNAME` configured in `.env`)
- **Password:** `q1w2e3r4` (or `ADMIN_PASSWORD` configured in `.env`)

---

## 🔒 Nginx Reverse Proxy & SSL (Optional)

To expose Edge D.U.R.O. securely behind a domain name with SSL/TLS termination:

```nginx
server {
    listen 80;
    server_name duro.your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name duro.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/duro.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/duro.your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3333;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Server-Sent Events (SSE) log streaming support
        proxy_read_timeout 3600s;
        proxy_buffering off;
    }
}
```
