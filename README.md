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

## 🔌 Default Exposed Ports

| Service | Container Port | Host Port | Notes |
|---------|---------------|-----------|-------|
| **Frontend** | 3333 | `3333` | Web UI & Nginx API reverse proxy |
| **Backend** | 8000 | `8000` | FastAPI REST & SSE endpoints |
| **PostgreSQL** | 5432 | `5433` | Standalone DB instance |
| **Redis** | 6379 | `6380` | Task broker & PubSub log engine |

---

## 🚀 Remote Server Deployment Guide

### Prerequisites

- **OS:** Debian 11/12, Ubuntu 22.04/24.04, or RHEL/Rocky 9 Linux server.
- **Kernel / Capabilities:** Linux Kernel 5.15+ with loop device support enabled (`modprobe loop`).
- **Software:** `git`, `docker`, and `docker-compose` (or `docker compose` plugin v2+).

### Step 1: Clone Repository

```bash
git clone https://github.com/masseselsev/edge-duro.git /opt/edge-duro
cd /opt/edge-duro
```

### Step 2: Configure Environment Variables & Generate JWT Key

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

# Admin Authentication
SUPERADMIN_USERNAME=admin
ADMIN_PASSWORD=SetYourSecureSuperadminPasswordHere
JWT_SECRET_KEY=e8f9a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c3d5e7f9

# Host Workspace Storage Path
DURO_WORKSPACE_PATH=/opt/data/duro_workspace
```

### Step 3: Launch Containers

```bash
docker-compose up -d --build
```

Verify service health:

```bash
docker-compose ps
```

### Step 4: Access Web UI

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
