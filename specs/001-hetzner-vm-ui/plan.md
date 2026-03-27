# Implementation Plan: Hetzner Cloud VM Management UI

**Branch**: `001-hetzner-vm-ui` | **Date**: 2026-03-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-hetzner-vm-ui/spec.md`

## Summary

A two-project web application for managing Hetzner Cloud VMs. The **FastAPI backend** (Python 3.12) handles all business logic: JWT-based authentication against a PostgreSQL `users` table, Hetzner Cloud and Cloudflare API orchestration, SSE streaming for long-running operations, database persistence for configuration and operation history. The **Next.js 14 frontend** (TypeScript) renders the React UI; all browser calls to `/api/*` are reverse-proxied to the FastAPI backend via `next.config.ts` rewrites — making the system appear same-origin to the browser and eliminating CORS complexity. FastAPI sets JWT in an `httpOnly; Secure; SameSite=Lax` cookie; Next.js `middleware.ts` reads the cookie to protect dashboard routes.

## Technical Context

**Language/Version**: Backend: Python 3.12; Frontend: TypeScript 5.x, Node.js 20 LTS  
**Primary Dependencies**:
- Backend: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `passlib[bcrypt]`, `python-jose[cryptography]`, `hcloud`, `sse-starlette`, `pydantic-settings`, `httpx`
- Frontend: Next.js 14 App Router, shadcn/ui, Tailwind CSS  

**Storage**: PostgreSQL 16 (Docker for local dev; managed PostgreSQL for production)  
**Testing**:
- Backend: `pytest`, `pytest-asyncio`, `httpx` (ASGI test client), `respx` (httpx mock)
- Frontend: Vitest + React Testing Library (unit/component), Playwright (E2E), msw (contract mocks for backend API shapes)  

**Target Platform**: Linux server / Docker Compose (3 services: `db`, `backend`, `frontend`)  
**Project Type**: Two-project web application (FastAPI backend + Next.js frontend in one repository)  
**Performance Goals**: FastAPI API routes ≤ 200 ms p95 (non-SSE); login ≤ 500 ms p95; dashboard load ≤ 3 s (SC-001); firewall sync ≤ 10 s (SC-005)  
**Constraints**: All Hetzner/Cloudflare credentials backend-only (`backend/.env`); JWT in `httpOnly; Secure` cookie; Next.js rewrites proxy `/api/*` → FastAPI — no CORS needed in production  
**Scale/Scope**: 1–10 users; ≤ 20 VMs; single PostgreSQL instance

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | Two clearly separated projects, single responsibility each. FastAPI routers are domain-scoped (`auth/`, `vms/`, `config/`). Pydantic schemas and SQLAlchemy models in separate files. `ruff --select ALL` (Python) and ESLint strict (TypeScript) enforce zero-warning policy. |
| II. Testing Standards | ✅ PASS | TDD enforced. Backend: pytest ≥ 80% coverage, async ASGI test client, real test DB. Frontend: Vitest unit/component ≥ 80%, msw contract tests, Playwright E2E for all user stories (US1–US6). |
| III. UX Consistency | ✅ PASS | Frontend uses shadcn/ui + Tailwind tokens throughout. All auth states (unauthenticated, loading, error, session-expired redirect) explicitly handled in `middleware.ts` and component states. |
| IV. Performance | ✅ PASS | SLOs defined above. FastAPI async from top to bottom (asyncpg, hcloud async). bcrypt cost-12 ≈ 200 ms within 500 ms p95 login SLO. Next.js 30 s server-cache on list endpoint meets SC-001. |

**Justified split architecture**: Two projects increase deployment surface compared to a full-stack Next.js app but are fully warranted — Python has the `hcloud` official SDK, `sse-starlette`, and superior async ecosystem for long-running Hetzner operations. The split also enables independent scaling and testing of backend logic without the React layer.

## Project Structure

### Documentation (this feature)

```text
specs/001-hetzner-vm-ui/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (TypeScript types + SQLAlchemy/Pydantic models)
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api-routes.md    # Phase 1 output (FastAPI routes; auth + config + VM)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
backend/                                    # Python 3.12 FastAPI service
├── app/
│   ├── main.py                             # FastAPI app; startup lifespan; router mounts
│   ├── database.py                         # Async SQLAlchemy engine + get_db() dependency
│   ├── auth/
│   │   ├── router.py                       # POST /auth/token, POST /auth/logout
│   │   ├── service.py                      # verify_password(), create_access_token(), get_current_user() dep
│   │   └── schemas.py                      # LoginRequest, TokenResponse
│   ├── vms/
│   │   ├── router.py                       # GET /vms; POST /vms/{name}/start|stop|archive|restore (SSE)
│   │   └── schemas.py                      # VirtualMachineOut, SnapshotOut, OperationEventOut
│   ├── ip/
│   │   └── router.py                       # GET /ip
│   ├── firewall/
│   │   └── router.py                       # POST /firewall/sync
│   ├── config/
│   │   ├── router.py                       # CRUD /config/vm-configs; GET+PUT /config/app
│   │   └── schemas.py                      # VmConfigOut, VmConfigCreate, AppConfigOut
│   ├── models/
│   │   └── db.py                           # SQLAlchemy ORM: User, VmConfig, AppConfig, OperationLog
│   └── lib/
│       ├── hetzner.py                      # hcloud SDK wrapper: list_servers(), power_on(), etc.
│       ├── cloudflare.py                   # httpx Cloudflare REST wrapper: update_a_record()
│       └── ip.py                           # detect_public_ip()
├── alembic/
│   ├── env.py
│   └── versions/                           # Alembic migration scripts (auto-generated)
├── tests/
│   ├── conftest.py                         # Async engine + test-DB session fixtures; seed admin user
│   ├── unit/
│   │   ├── test_hetzner.py                 # hcloud wrapper (respx mocks)
│   │   ├── test_cloudflare.py              # Cloudflare wrapper (respx mocks)
│   │   └── test_ip.py
│   └── integration/
│       ├── test_auth.py                    # Login/logout/protected-route flows
│       ├── test_vms.py                     # GET /vms; start/stop; archive/restore SSE
│       ├── test_config.py                  # vm-configs CRUD; app config
│       └── test_firewall.py
├── alembic.ini
├── pyproject.toml                          # uv-managed; ruff + mypy config; pytest config
└── Dockerfile                              # Multi-stage Python build

frontend/                                   # Next.js 14 App Router (TypeScript)
├── src/
│   ├── app/
│   │   ├── layout.tsx                      # Root layout; OperationContext provider
│   │   ├── page.tsx                        # Dashboard (protected by middleware.ts)
│   │   ├── login/
│   │   │   └── page.tsx                    # Login page (LoginForm component)
│   │   └── api/
│   │       └── auth/
│   │           └── logout/route.ts         # Clears access_token cookie on logout
│   ├── components/
│   │   ├── VmCard.tsx
│   │   ├── ProgressSteps.tsx
│   │   ├── ErrorBanner.tsx
│   │   └── LoginForm.tsx                   # POSTs to /api/auth/token (proxied to FastAPI)
│   ├── context/
│   │   └── OperationContext.tsx
│   ├── lib/
│   │   └── api.ts                          # fetch() wrapper; all calls to /api/* (same-origin)
│   └── middleware.ts                       # Reads access_token cookie; redirects to /login if absent
├── tests/
│   ├── unit/
│   │   └── components/                     # Vitest + RTL (VmCard, LoginForm, ProgressSteps, ErrorBanner)
│   ├── contract/
│   │   └── mocks/                          # msw handlers for FastAPI response shapes
│   └── e2e/                                # Playwright (US1–US6)
├── next.config.ts                          # rewrites: /api/:path* → process.env.API_URL/:path*
├── vitest.config.ts
├── playwright.config.ts
└── Dockerfile                              # Multi-stage Node build

docker-compose.yml                          # Services: db (postgres:16), backend, frontend
docker-compose.test.yml                     # Test overrides: db_test, backend pointing at test DB
```

**Structure Decision**: Two-project layout — `backend/` (FastAPI) and `frontend/` (Next.js) — in a single repository. The frontend is a pure UI + proxy layer. All credentials, API orchestration, and DB access are strictly backend-only.

## Post-Phase 1 Constitution Re-check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | `backend/app/lib/` modules have ≤ 1 responsibility each. Pydantic schemas are separate from SQLAlchemy models. Frontend `lib/api.ts` is a thin fetch wrapper — no business logic in the UI layer. |
| II. Testing Standards | ✅ PASS | `backend/tests/conftest.py` provisions a real async test DB. `httpx.AsyncClient(app=app, base_url='http://test')` tests all routes without a live server. Frontend msw contract tests cover all FastAPI response shapes. Playwright E2E includes login (US6). |
| III. UX Consistency | ✅ PASS | Login page uses shadcn/ui `Card`, `Input`, `Button` — no hardcoded styles. Session-expired state triggers `middleware.ts` redirect — no blank screen. All auth states rendered. |
| IV. Performance | ✅ PASS | FastAPI async routes + asyncpg connection pool; bcrypt cost-12 measured ≈ 200 ms; Next.js 30 s server-side cache on `GET /api/vms` meets SC-001. |
