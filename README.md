# Edge D.U.R.O. (Debian & Ubuntu Recipe Oven)

Web-based control plane and background job runner for `mkosi`. Visually configure, manage, and execute OS image recipes for Debian 12+ and Ubuntu 22+ (amd64/arm64) to produce monolithic provisioning artifacts (`.raw.xz`, `.iso`).

## Architecture & Tech Stack
- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Celery, Redis, SSE log streaming.
- **Frontend:** React 19, TypeScript, Tailwind CSS 3, CodeMirror 6, Lucide Icons, Vite 8.
- **Database:** PostgreSQL 15 (port 5433).
- **Deployment:** Docker Compose.

## Quick Start
```bash
cp .env.example .env
docker-compose up --build
```
Access UI at `http://localhost:3333`.
