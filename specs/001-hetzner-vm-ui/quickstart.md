# Quickstart: Hetzner Cloud VM Management UI

**Branch**: `001-hetzner-vm-ui` | **Date**: 2026-03-26 (revised)  
**Phase**: 1 — Design  
**Audience**: Developer setting up or running the project locally or in production.

This project has two services — a **Python FastAPI backend** and a **Next.js frontend** — orchestrated by Docker Compose. You can run them individually for development or together via Compose.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.12+ | Install via [pyenv](https://github.com/pyenv/pyenv) or official installer |
| uv | latest | Fast Python package manager: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 20 LTS | Install via [nvm](https://github.com/nvm-sh/nvm) or official installer |
| npm | 10+ | Bundled with Node.js 20 |
| Git | Any | For cloning |
| PostgreSQL | 16+ | Docker recommended (see below) |
| Docker + Compose | 24+ | For PostgreSQL in dev and full-stack deployment |
| Hetzner Cloud account | — | API token (Read & Write) |
| Cloudflare account | — | API token with Zone:DNS:Edit permission |

---

## 1. Clone

```bash
git clone <repo-url>
cd <repo-name>
```

---

## 2. Start PostgreSQL

Using Docker:

```bash
docker run -d \
  --name vmmanager-db \
  -e POSTGRES_DB=vmmanager \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  postgres:16
```

Or use any local PostgreSQL 16+ installation and create a database named `vmmanager`.

---

## 3. Backend Setup

```bash
cd backend
```

### 3a. Create and activate virtual environment

```bash
uv venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
```

### 3b. Install dependencies

```bash
uv pip install -e ".[dev]"
```

This installs all runtime and development dependencies from `pyproject.toml`.

### 3c. Configure environment

```bash
cp .env.example .env
```

Edit `backend/.env`:

```env
# ── Hetzner Cloud API ─────────────────────────────────────────────────
HETZNER_API_TOKEN=your_hetzner_api_token_here

# ── Cloudflare API ────────────────────────────────────────────────────
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token_here

# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/vmmanager
DATABASE_URL_TEST=postgresql+asyncpg://postgres:password@localhost:5432/vmmanager_test

# ── Authentication ────────────────────────────────────────────────────
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# ── IP Detection ──────────────────────────────────────────────────────
IP_REFLECTION_URL=https://api.ipify.org?format=json
```

> **Security**: `backend/.env` is listed in `.gitignore` and MUST never be committed. All credentials are backend-only and never sent to the frontend.

### 3d. Run Alembic migrations

```bash
alembic upgrade head
```

This creates all tables (`users`, `vm_configs`, `app_configs`, `operation_logs`).

### 3e. Seed initial data

```bash
# ADMIN_PASSWORD is used once at seed time and never stored
ADMIN_PASSWORD=your-initial-password python scripts/seed.py
```

The seed script creates:
- An initial `admin` user with the hashed password from `ADMIN_PASSWORD`.
- Default `app_configs` rows (firewall name, server type, location, SSH key — prompted interactively or read from legacy env vars if present).

> **Re-seeding**: The seed script is idempotent — it uses `INSERT ... ON CONFLICT DO NOTHING`. Re-running does not duplicate data.

### 3f. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

The FastAPI server starts at `http://localhost:8000`. Interactive OpenAPI docs are at `http://localhost:8000/docs`.

---

## 4. Frontend Setup

Open a new terminal:

```bash
cd frontend
```

### 4a. Install dependencies

```bash
npm install
```

### 4b. Configure environment

```bash
cp .env.example .env.local
```

Edit `frontend/.env.local`:

```env
# URL of the FastAPI backend — used server-side by Next.js rewrites only
API_URL=http://localhost:8000
```

> This is the only environment variable the frontend needs. All secrets stay in `backend/.env`.

### 4c. Start the frontend

```bash
npm run dev
```

The Next.js server starts at `http://localhost:3000`.

Open [http://localhost:3000](http://localhost:3000). You will be redirected to `/login`. Enter credentials seeded in step 3e (`admin` / `ADMIN_PASSWORD` value).

After login, the dashboard will:
1. Load all Hetzner VMs and archived (snapshot-only) VMs.
2. Detect your public IP and sync it to the shared Hetzner firewall.

> **How requests work**: The browser calls `/api/*` (same-origin, port 3000). Next.js rewrites these to `http://localhost:8000/*`. Auth cookies set by FastAPI are forwarded through the Next.js proxy to the browser.

---

## 5. Run Tests

### Backend Tests

Ensure the test database exists:

```bash
docker exec vmmanager-db createdb -U postgres vmmanager_test
```

Then run:

```bash
cd backend
source .venv/bin/activate

# Unit tests only
pytest tests/unit/

# Integration tests (spins up against vmmanager_test DB)
pytest tests/integration/

# All tests with coverage (must be ≥ 80%)
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

> The test `conftest.py` runs `alembic upgrade head` against `DATABASE_URL_TEST` before the test session. No manual migration step needed.

### Frontend Tests

```bash
cd frontend

# Unit + component tests (Vitest + React Testing Library)
npm run test

# Watch mode
npm run test:watch

# With coverage (must be ≥ 80% lines)
npm run test:coverage
```

### E2E Tests (Playwright)

Playwright runs against the live Next.js + FastAPI dev stack. Start both services first (steps 3f and 4c), then:

```bash
cd frontend
npm run test:e2e            # headless
npm run test:e2e:ui         # headed with trace viewer
```

---

## 6. Build and Run in Production

### Option A: Docker Compose (recommended)

```bash
docker compose up --build
```

This starts three containers:
- `db` — PostgreSQL 16
- `backend` — FastAPI on port 8000
- `frontend` — Next.js on port 3000 (mapped to host port 80 or as configured)

On first deploy, run migrations and seed inside the backend container:

```bash
docker compose exec backend alembic upgrade head
docker compose exec -e ADMIN_PASSWORD=your-password backend python scripts/seed.py
```

### Option B: Manual builds

**Backend**:

```bash
cd backend
uv pip install -e "."
DATABASE_URL=postgresql+asyncpg://... uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Frontend**:

```bash
cd frontend
npm run build
API_URL=http://your-backend-host:8000 npm run start
```

> In production, place both services behind a reverse proxy (nginx, Caddy) with HTTPS. The frontend is the only public-facing service. The backend should NOT be publicly accessible — only reachable from the frontend container.

---

## 7. Key Environment Variables Reference

### `backend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `HETZNER_API_TOKEN` | ✅ | Hetzner Cloud API token (Read+Write). Never in frontend. |
| `CLOUDFLARE_API_TOKEN` | ✅ | Cloudflare API token (Zone:DNS:Edit). Never in frontend. |
| `DATABASE_URL` | ✅ | PostgreSQL async connection string (`postgresql+asyncpg://...`) |
| `DATABASE_URL_TEST` | ✅ (tests) | Test DB async connection string |
| `SECRET_KEY` | ✅ | 32-byte hex secret for JWT signing. Generate with `secrets.token_hex(32)`. |
| `ALGORITHM` | ✅ | JWT algorithm — `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ✅ | JWT TTL in minutes — default `1440` (24 h) |
| `ADMIN_PASSWORD` | Seed only | Initial admin password. Read at seed time only; never persisted. |
| `IP_REFLECTION_URL` | Optional | IP echo service. Default: `https://api.ipify.org?format=json` |

### `frontend/.env.local`

| Variable | Required | Description |
|----------|----------|-------------|
| `API_URL` | ✅ | Base URL of the FastAPI backend; used by Next.js rewrites (server-side only). E.g. `http://localhost:8000` or `http://backend:8000` in Docker. |

**Operational configuration** (firewall name, server defaults, VM→DNS mappings) is database-stored in `app_configs` and `vm_configs` tables — not in environment variables.

---

## 8. How VM State and Config Work

**VM State** (live data — not stored in DB):
- **Live VMs** (`running` / `stopped`): returned by the Hetzner Servers API via the `hcloud` Python SDK.
- **Archived VMs**: represented by Hetzner snapshot images carrying the label `vm-name=<vmName>`. Any name present in snapshot labels but absent from live servers is displayed as `archived`.
- **Latest snapshot for restore**: the snapshot with the highest `created` timestamp among all snapshots sharing a `vm-name` label value.

**Stored configuration** (in DB):
- `vm_configs` table: maps each VM name to its Cloudflare DNS domain. Required before the Restore step "Updating DNS" can succeed.
- `app_configs` table: `hetzner_firewall_name`, `hetzner_default_server_type`, `hetzner_default_location`, `hetzner_default_ssh_key`. Required before Restore and Firewall Sync operations.


**Branch**: `001-hetzner-vm-ui` | **Date**: 2026-03-25  
**Phase**: 1 — Design  
**Audience**: Developer setting up or running the project locally or in production.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 20 LTS | Install via [nvm](https://github.com/nvm-sh/nvm) or official installer |
| npm | 10+ | Bundled with Node.js 20 |
| Git | Any | For cloning |
| PostgreSQL | 16+ | Docker recommended: `docker run -d --name vmmanager-db -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:16` |
| Docker (optional) | 24+ | For PostgreSQL in dev and/or containerised deployment |
| Hetzner Cloud account | — | With an API token (Read & Write) |
| Cloudflare account | — | With an API token scoped to DNS edit on the target zone(s) |

---

## 1. Clone and Install

```bash
git clone <repo-url>
cd <repo-name>
npm install
```

---

## 2. Configure Environment Variables

Copy the example file to `.env.local`:

```bash
cp .env.example .env.local
```

Edit `.env.local` with your values:

```env
# ── Hetzner Cloud API ─────────────────────────────────────────────────
# API token with Read + Write permissions
HETZNER_API_TOKEN=your_hetzner_api_token_here

# ── Cloudflare API ────────────────────────────────────────────────────
# API token with Zone:DNS:Edit permission on the relevant zone(s)
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token_here

# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL=postgresql://postgres:password@localhost:5432/vmmanager

# ── Authentication ────────────────────────────────────────────────────
NEXTAUTH_SECRET=<generate-with: openssl rand -hex 32>
NEXTAUTH_URL=http://localhost:3000

# ── IP Detection ──────────────────────────────────────────────────────
# URL of a public IP reflection service returning JSON { "ip": "x.x.x.x" }
# Fallback used if X-Forwarded-For header is not present
IP_REFLECTION_URL=https://api.ipify.org?format=json
```

> **Security**: `.env.local` is listed in `.gitignore` and MUST never be committed. All credentials stay server-side and are never sent to the browser.
>
> Operational configuration (firewall name, server type, DNS mappings) is stored in the **database** and managed via the app. See section 3 (Database Setup) for seeding instructions.

---

## 3. Database Setup

### 3a. Start PostgreSQL (local dev)

Using Docker:

```bash
docker run -d \
  --name vmmanager-db \
  -e POSTGRES_DB=vmmanager \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  postgres:16
```

Or use any local PostgreSQL 16+ installation and create a database named `vmmanager`.

### 3b. Run Prisma Migrations

```bash
npx prisma migrate dev --name init
```

This creates all tables (`users`, `vm_configs`, `app_configs`, `operation_logs`) in the database.

### 3c. Seed Initial Data

```bash
# Set ADMIN_PASSWORD before seeding — it is used once and never stored.
ADMIN_PASSWORD=your-initial-password npx prisma db seed
```

The seed script (`prisma/seed.ts`) creates:
- An initial `admin` user with the hashed password from `ADMIN_PASSWORD`.
- Default `app_configs` rows (firewall name, server type, location, SSH key — prompted interactively or read from legacy env vars if still present).

> **Re-seeding**: The seed is idempotent. Re-running performs upserts — existing data is not duplicated.

### 3d. Inspect the Database (Optional)

```bash
npx prisma studio
```

Opens a web browser at `http://localhost:5555` with a visual DB editor.

---

## 4. Run Locally (Development)

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

You will be redirected to `/login`. Enter the credentials created during seeding (`admin` / the value you passed as `ADMIN_PASSWORD`).

After login, the dashboard will:
1. Load all Hetzner VMs and archived (snapshot-only) VMs.
2. Detect your public IP and sync it to the shared Hetzner firewall.

> **Note on IP detection in local dev**: If you're running the Next.js server locally and accessing it on `localhost`, `X-Forwarded-For` will not be set, so the server calls `IP_REFLECTION_URL` to detect your outbound IP. This is the IP that will be added to the Hetzner firewall.

---

## 5. Run Tests

### Test Database Setup

E2E and DB integration tests use a separate database. Set `DATABASE_URL_TEST` in `.env.local`:

```env
DATABASE_URL_TEST=postgresql://postgres:password@localhost:5432/vmmanager_test
```

Create and migrate the test DB:

```bash
DATABASE_URL="$DATABASE_URL_TEST" npx prisma migrate deploy
```

### Unit + Component Tests (Vitest)

```bash
npm run test           # run once
npm run test:watch     # watch mode for development
npm run test:coverage  # run with coverage report (must be ≥ 80%)
```

### Contract Tests (msw)

Contract tests run as part of the Vitest suite using msw handlers:

```bash
npm run test
```

msw intercepts all outbound Hetzner and Cloudflare HTTP calls. DB tests use the real test database (`DATABASE_URL_TEST`) — Prisma client is not mocked.

### Integration / E2E Tests (Playwright)

```bash
npm run test:e2e            # headless
npm run test:e2e:ui         # headed, visual trace
```

Playwright tests start a local Next.js server (targeting `DATABASE_URL_TEST`) and run all user story flows end-to-end, including the login flow (US6).

---

## 6. Build and Run in Production

```bash
npm run build
npm run start
```

The server listens on port `3000` by default. Set `PORT` environment variable to override:

```bash
PORT=8080 npm run start
```

**Before first production deploy**, run migrations and seed the database:

```bash
npx prisma migrate deploy              # applies all migrations
ADMIN_PASSWORD=your-password npx prisma db seed
```

---

## 7. Docker (Optional)

A `Dockerfile` is included for containerised deployment:

```bash
docker build -t hetzner-vm-ui .

docker run -d \
  --name hetzner-vm-ui \
  -p 3000:3000 \
  --env-file .env.local \
  hetzner-vm-ui
```

The container exposes port `3000`. Use a reverse proxy (nginx, Caddy) in front for HTTPS. In production set `NEXTAUTH_URL` to your public URL (e.g. `https://vms.example.com`).

> **Reverse proxy and IP detection**: Ensure the proxy forwards `X-Forwarded-For`. The Next.js server reads this to detect the user's real public IP for firewall sync. Without it, the server's own outbound IP is used.

> **Database connectivity**: The container must be able to reach the PostgreSQL host. If using Docker Compose, put both services in the same network and use the service name as the DB host in `DATABASE_URL`.

---

## 8. Key Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `HETZNER_API_TOKEN` | ✅ | Hetzner Cloud API token (Read+Write). Never stored in DB. |
| `CLOUDFLARE_API_TOKEN` | ✅ | Cloudflare API token (Zone:DNS:Edit). Never stored in DB. |
| `DATABASE_URL` | ✅ | PostgreSQL connection string (production DB) |
| `DATABASE_URL_TEST` | ✅ (tests) | PostgreSQL connection string (test DB) |
| `NEXTAUTH_SECRET` | ✅ | 32-byte random hex. Generate: `openssl rand -hex 32` |
| `NEXTAUTH_URL` | ✅ | Public base URL of the app (e.g. `http://localhost:3000`) |
| `ADMIN_PASSWORD` | Seed only | Initial admin password. Read at seed time, never persisted. |
| `IP_REFLECTION_URL` | Optional | IP detection service. Default: `https://api.ipify.org?format=json` |
| `PORT` | Optional | Port for `next start` / Docker. Default: `3000` |

**Operational config** (firewall name, server defaults, VM→DNS mappings) is managed in the database via `app_configs` and `vm_configs` tables. These no longer require environment variables.

---

## 9. How VM State and Config Work

**VM State** (live data — not stored in DB):
- **Live VMs** (`running` / `stopped`): returned by the Hetzner Servers API.
- **Archived VMs**: represented by Hetzner snapshot images carrying the label `vm-name=<vmName>`. Any name present in snapshot labels but absent from live servers is shown as `archived`.
- **Latest snapshot for restore**: the snapshot with the highest `created` timestamp among all snapshots sharing a `vm-name` label value.

VM list API responses are cached on the server for 30 seconds to reduce Hetzner API load (SC-001 ≤ 3 s target).

**Operational Configuration** (stored in DB):
- `app_configs` table: firewall name, server type, location, SSH key. Read live with each operation.
- `vm_configs` table: VM-name → Cloudflare domain mappings. Read on restore to resolve the DNS record to update.

**Operation History** (stored in DB):
- `operation_logs` table: one row per operation (start, stop, archive, restore), recording status and step details. Written by each API route handler.

---

## 10. Troubleshooting

| Symptom | Likely Cause | Resolution |
|---------|-------------|------------|
| Redirected to `/login` on every request | `NEXTAUTH_SECRET` not set or session cookie missing | Set `NEXTAUTH_SECRET` in `.env.local`; clear browser cookies |
| Login fails with "Invalid credentials" | Admin user not seeded or wrong password | Re-run `ADMIN_PASSWORD=<pw> npx prisma db seed`; check DB `users` table |
| Dashboard shows "Unable to reach Hetzner Cloud" | Invalid or missing `HETZNER_API_TOKEN` | Check `.env.local`; verify token has Read+Write scope |
| Restore fails at "Updating DNS" | No `vm_configs` row for VM or invalid `CLOUDFLARE_API_TOKEN` | Add VM config via `GET /api/config/vm-configs`; verify Cloudflare token permissions |
| Firewall sync fails on load | `hetzner_firewall_name` app config not set | Check `app_configs` table in DB; update via `PUT /api/config/app` |
| Wrong IP added to firewall | Reverse proxy not forwarding `X-Forwarded-For` | Configure proxy to pass `X-Forwarded-For`; or access the UI directly in local dev |
| Archive shows "Archived" but VM still appears live | Hetzner API cache TTL (30 s) | Refresh after 30 seconds |
| Migration fails: "relation already exists" | Previous partial migration applied | Run `npx prisma migrate resolve --applied <migration-name>` then retry |
| Prisma client not generated | Missing post-install step | Run `npx prisma generate` manually |
