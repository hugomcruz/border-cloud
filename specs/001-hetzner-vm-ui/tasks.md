---
description: "Task list for Hetzner Cloud VM Management UI"
---

# Tasks: Hetzner Cloud VM Management UI

**Input**: Design documents from `/specs/001-hetzner-vm-ui/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/api-routes.md ✅ quickstart.md ✅

**Tests**: Included — Constitution Principle II requires TDD (NON-NEGOTIABLE). Tests must be written and fail before implementation begins.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Exact file paths included in all descriptions

## Path Conventions

- **Two-project layout** in one repository:
  - Backend: `backend/` — `backend/app/`, `backend/tests/`, `backend/alembic/`, `backend/scripts/`
  - Frontend: `frontend/` — `frontend/src/`, `frontend/tests/`
- Shared: `docker-compose.yml`, `docker-compose.test.yml`, `.github/workflows/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize both the FastAPI backend project and the Next.js frontend project with their testing infrastructure and shared tooling. These tasks have no dependency on one another — backend and frontend setup can proceed in parallel after T001.

- [X] T001 Create `backend/pyproject.toml` with uv-managed dependencies: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `passlib[bcrypt]`, `python-jose[cryptography]`, `hcloud`, `sse-starlette`, `pydantic-settings`, `httpx`; dev extras: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `ruff`, `mypy`
- [X] T002 [P] Configure ruff (`--select ALL`, zero-warning gate) and mypy (`strict = true`) in `backend/pyproject.toml`; add `lint` and `typecheck` scripts to `[tool.scripts]`
- [X] T003 [P] Configure pytest + pytest-asyncio in `backend/pyproject.toml`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `--cov=app --cov-fail-under=80`; add `test` and `test:cov` scripts
- [X] T004 Create full `backend/` directory tree per plan.md: `app/auth/`, `app/vms/`, `app/ip/`, `app/firewall/`, `app/config/`, `app/models/`, `app/lib/`, `alembic/versions/`, `tests/unit/`, `tests/integration/`, `scripts/`; add `__init__.py` to all Python packages
- [X] T005 Initialize `frontend/` Next.js 14 App Router TypeScript project via `create-next-app` with `--typescript --eslint --tailwind --src-dir --app` flags; move into `frontend/` subdirectory of repo root
- [X] T006 [P] Install shadcn/ui in `frontend/`; configure Tailwind CSS design tokens (colour palette, spacing, typography) in `frontend/tailwind.config.ts` and `frontend/src/app/globals.css`; add base shadcn/ui components: `Button`, `Card`, `Input`, `Dialog`, `Badge`
- [X] T007 [P] Configure ESLint with TypeScript strict rules in `frontend/.eslintrc.json`: `@typescript-eslint/strict`, `no-unused-vars`, `no-console`; add `lint` npm script enforcing zero warnings
- [X] T008 [P] Set up Vitest + React Testing Library in `frontend/vitest.config.ts` with 80% line/branch coverage threshold; add `test`, `test:watch`, `test:coverage` npm scripts; install `vitest`, `@testing-library/react`, `@testing-library/user-event`, `@vitest/coverage-v8`
- [X] T009 [P] Set up Playwright targeting local Next.js dev server (`baseURL: 'http://localhost:3000'`) in `frontend/playwright.config.ts`; add `test:e2e` and `test:e2e:ui` npm scripts; install `@playwright/test`
- [X] T010 [P] Configure msw 2.x in `frontend/tests/contract/mocks/setup.ts` for Node.js (Vitest) and browser (Playwright) environments to intercept all `/api/*` calls in contract tests; install `msw`
- [X] T011 Create `frontend/next.config.ts` with rewrites: `{ source: '/api/:path*', destination: '${process.env.API_URL}/:path*' }` — proxies all browser `/api/*` calls to FastAPI with no CORS needed
- [X] T012 [P] Create `backend/.env.example` with all required env vars per `specs/001-hetzner-vm-ui/quickstart.md`: `HETZNER_API_TOKEN`, `CLOUDFLARE_API_TOKEN`, `DATABASE_URL`, `DATABASE_URL_TEST`, `SECRET_KEY`, `ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_MINUTES=1440`, `IP_REFLECTION_URL`, `ADMIN_PASSWORD`
- [X] T013 [P] Create `frontend/.env.example` with `API_URL=http://localhost:8000`; add env var validation note in `frontend/next.config.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure that MUST be complete before ANY user story can begin. Covers DB models, settings, Alembic, authentication layer (backend) and TypeScript types, API client, shared UI components, auth pages, and middleware (frontend).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Backend Foundational

- [X] T014 Create SQLAlchemy ORM models in `backend/app/models/db.py`: `User`, `VmConfig`, `AppConfig`, `OperationLog` with all columns and `DeclarativeBase` per `specs/001-hetzner-vm-ui/data-model.md`
- [X] T015 Create `backend/app/database.py`: `create_async_engine` + `async_sessionmaker` from `DATABASE_URL` setting; `get_db()` async generator dependency yielding `AsyncSession`
- [X] T016 Create `backend/app/config.py`: `pydantic-settings` `Settings` class reading all env vars (`HETZNER_API_TOKEN`, `CLOUDFLARE_API_TOKEN`, `DATABASE_URL`, `DATABASE_URL_TEST`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `IP_REFLECTION_URL`); singleton `settings` instance
- [X] T017 Initialize Alembic: create `backend/alembic.ini` and `backend/alembic/env.py` pointing at `DATABASE_URL` from settings and importing `Base` from `backend/app/models/db.py`; run `alembic revision --autogenerate -m "init"` to generate initial migration for all four tables
- [X] T018 Create `backend/scripts/seed.py`: idempotent script that (1) creates `admin` user from `ADMIN_PASSWORD` env var using `passlib` bcrypt hash (`INSERT ... ON CONFLICT DO NOTHING`), (2) inserts default `app_configs` rows (`hetzner_firewall_name`, `hetzner_default_server_type`, `hetzner_default_location`, `hetzner_default_ssh_key`) also idempotent
- [X] T019 Create `backend/app/auth/schemas.py`: Pydantic v2 `LoginRequest` (`username: str`, `password: str`), `TokenResponse` (`access_token: str`, `token_type: str = "bearer"`)
- [X] T020 Implement `backend/app/auth/service.py`: `CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)`, `verify_password(plain, hashed)`, `create_access_token(data: dict) -> str` (signs with `SECRET_KEY`, `HS256`, TTL from settings), `get_current_user(access_token: str = Cookie(None), db: AsyncSession = Depends(get_db)) -> User` dependency that decodes JWT and queries `users` table; raises `HTTPException(401)` if absent/invalid/expired
- [X] T021 Implement `backend/app/auth/router.py`: `POST /auth/token` — verify credentials via `verify_password`, issue JWT, set `httpOnly; Secure; SameSite=Lax; Path=/` cookie, return `TokenResponse`; `POST /auth/logout` — set `Max-Age=0` cookie, return `{ "message": "Logged out" }`; both routes are public (no `get_current_user` dependency)
- [X] T022 Create `backend/app/main.py`: instantiate `FastAPI` with lifespan; mount all routers (`auth`, `vms`, `ip`, `firewall`, `config`) with appropriate prefixes; configure trusted proxy middleware if needed
- [X] T023 Create `backend/tests/conftest.py`: async test engine pointing at `DATABASE_URL_TEST`; session-scoped fixture that calls `alembic upgrade head` on test DB; function-scoped `AsyncSession` fixture; `admin_user` fixture that inserts test user; `authenticated_client` fixture (`httpx.AsyncClient(app=app, base_url="http://test")` with auth cookie set)

### Backend Auth Integration Tests (write first — must FAIL before T021 implementation)

- [X] T024 Write `backend/tests/integration/test_auth.py`: (1) `POST /auth/token` with correct credentials → 200 + `Set-Cookie` header; (2) `POST /auth/token` with wrong password → 401; (3) `GET /vms` without cookie → 401; (4) `POST /auth/logout` → 200 + `Max-Age=0` cookie; (5) `GET /vms` after logout cookie cleared → 401

### Frontend Foundational

- [X] T025 Define all TypeScript types in `frontend/src/types/index.ts`: `VmStatus`, `VirtualMachine`, `Snapshot`, `OperationStep`, `OperationStepStatus`, `OperationEvent`, `OperationEventKind`, `FirewallSyncResult`, `IpDetectionResult` per `specs/001-hetzner-vm-ui/data-model.md` — these exactly mirror the FastAPI Pydantic response schemas
- [X] T026 Create `frontend/src/lib/api.ts`: `apiFetch(path, options)` wrapper over `fetch()` that always calls `/api/*` (same-origin); on `401` response redirects to `/login`; throws typed error with `{ message: string }` shape for non-OK responses
- [X] T027 Create `frontend/src/context/OperationContext.tsx`: `useReducer` tracking `{ vmName: string | null; operation: string | null }`; actions `LOCK` and `UNLOCK`; exports `OperationContext` and `useOperation()` hook (FR-013)
- [X] T028 [P] Create `frontend/src/components/ErrorBanner.tsx`: accepts `message: string` and optional `completedSteps: string[]`; renders shadcn/ui `Alert` with user-friendly text and dismiss button; never exposes raw API error text; lists completed steps if provided (FR-012, FR-015)
- [X] T029 [P] Create `frontend/src/components/ProgressSteps.tsx`: accepts `steps: OperationStep[]`; renders each step with spinner icon (in-progress), checkmark (done), X (error), or muted dot (pending); uses shadcn/ui and Tailwind tokens only (FR-011)
- [X] T030 Create `frontend/src/middleware.ts`: reads `access_token` cookie from `request.cookies.get('access_token')`; if absent and path is not `/login`, redirects to `/login`; if present and path is `/login`, redirects to `/`
- [X] T031 Create `frontend/src/app/layout.tsx`: root layout wrapping children with `OperationContext` provider; imports `globals.css`; sets page `<title>` and Tailwind font class
- [X] T032 Create `frontend/src/components/LoginForm.tsx` and `frontend/src/app/login/page.tsx`: shadcn/ui `Card` + `Input` + `Button`; `POST /api/auth/token` with `{ username, password }` JSON via `apiFetch`; on 200 redirect to `/`; on 401 show inline shadcn/ui error alert "Invalid username or password"; no raw API text exposed; and `frontend/src/app/login/page.tsx` rendering it
- [X] T033 Create `frontend/src/app/api/auth/logout/route.ts`: Next.js route handler that sets `access_token` cookie with `Max-Age=0` (clearing it) then calls `POST /api/auth/logout` proxied to FastAPI and redirects to `/login`

**Checkpoint**: Foundation complete — DB schema, auth, and shared UI primitives exist. All user story implementation can now begin.

---

## Phase 3: User Story 1 — View VM Dashboard (Priority: P1) 🎯 MVP

**Goal**: Display all Hetzner Cloud VMs (running, stopped, archived) with their status and contextually available actions.

**Independent Test**: Load the UI; verify each live VM appears with correct status badge and action buttons per state; verify archived VMs (snapshot-only, `vm-name` label) appear as "Archived" with Restore available only when `canRestore=true`; verify loading skeleton while fetching; verify `ErrorBanner` when API is unreachable.

### Tests for User Story 1 ⚠️ Write these FIRST — must FAIL before implementation begins

- [ ] T034 [P] [US1] Write unit tests for `list_servers()` and `list_snapshots_by_label()` in `backend/tests/unit/test_hetzner.py`: (1) two live servers returned and mapped to `VirtualMachineOut`; (2) one labeled snapshot for archived VM; (3) Hetzner API raises exception → `HTTPException(500)` with user-friendly message "Unable to reach Hetzner Cloud. Please try again."; (4) `list_snapshots_by_label()` returns empty list when no labeled snapshots exist
- [ ] T039 [P] [US1] Write msw handler for `GET /api/vms` in `frontend/tests/contract/mocks/vms-list.handler.ts`: mock returning 1 running + 1 stopped + 1 archived VM; assert `vms` array contains `VirtualMachine[]`; assert `canStart=true` only for stopped, `canStop=true` only for running, `canRestore=true` only for archived with snapshot, `canArchive=true` for running and stopped
- [ ] T040 [P] [US1] Write unit tests for `VmCard` in `frontend/tests/unit/components/VmCard.test.tsx`: (1) running VM shows Stop button, no Start/Restore; (2) stopped VM shows Start button, no Stop/Restore; (3) archived VM with snapshot shows Restore button only; (4) archived VM without snapshot shows no actions; (5) operation lock disables all buttons; (6) `publicIp` displayed for live VMs only

### Implementation for User Story 1

- [ ] T035 [US1] Create `backend/app/vms/schemas.py`: `SnapshotOut`, `VirtualMachineOut` (with all `can*` fields), `OperationEventOut` Pydantic models per `specs/001-hetzner-vm-ui/data-model.md`
- [ ] T036 [P] [US1] Implement `list_servers()` and `list_snapshots_by_label()` in `backend/app/lib/hetzner.py`: instantiate `hcloud.Client(token=settings.HETZNER_API_TOKEN)`; wrap `client.servers.get_all()` and `client.images.get_all(type='snapshot', label_selector='vm-name')` with `asyncio.to_thread()`; map to `VirtualMachineOut` and `SnapshotOut` shapes; raise `HTTPException(500, detail="Unable to reach Hetzner Cloud. Please try again.")` on SDK exception
- [X] T037 [US1] Implement `GET /vms` in `backend/app/vms/router.py`: call `list_servers()` + `list_snapshots_by_label()` concurrently via `asyncio.gather()`; merge results — names in snapshots but not in live servers become `status='archived'`; attach `latest_snapshot` to live VMs if labeled snapshot exists; compute all `can*` boolean flags; return `{ "vms": [...] }`; requires `Depends(get_current_user)`
- [X] T038 [US1] Write integration tests for `GET /vms` in `backend/tests/integration/test_vms.py` (against real test DB + mocked hcloud via unittest.mock.patch): (1) authenticated → 200 with merged VM list; (2) unauthenticated → 401; (3) hcloud raises exception → 500 with user-friendly error; (4) archived VM correctly identified when name absent from live servers but present in snapshots
- [X] T041 [US1] Implement `frontend/src/components/VmCard.tsx`: shadcn/ui `Card` rendering VM name, status `Badge` (colour-coded per VmStatus), `publicIp` for live VMs, action buttons from `can*` flags; button disabled when `OperationContext` lock active for this `vmName`; integrates with `ErrorBanner` for per-card error display (FR-012, FR-013)
- [X] T042 [US1] Implement `frontend/src/app/page.tsx`: call `GET /api/vms` via `apiFetch` on mount; render loading skeleton (shadcn/ui `Skeleton`) while in-flight; render one `VmCard` per VM; render `ErrorBanner` on fetch failure; implement `refreshVms()` function called after any VM mutation; trigger on-load firewall sync (stub call for now — wired in US5)

**Checkpoint**: US1 fully functional — read-only dashboard delivering immediate monitoring value.

---

## Phase 4: User Story 2 — Start and Stop a VM (Priority: P1)

**Goal**: Start a stopped VM or stop a running VM from the dashboard with real-time button feedback and operation locking.

**Independent Test**: Click Start on stopped VM → status transitions to running and UI updates; click Stop on running VM → status transitions to stopped; action button disabled and spinner shown during in-progress; `ErrorBanner` on API failure; buttons re-enabled after response.

### Tests for User Story 2 ⚠️ Write these FIRST — must FAIL before implementation begins

- [X] T043 [P] [US2] Write unit tests for `power_on(name)` and `power_off(name)` in `backend/tests/unit/test_hetzner.py`: (1) server found → SDK call made, returns successfully; (2) server not found by name → `HTTPException(404)` with user-friendly message; (3) SDK raises exception → `HTTPException(500)` with user-friendly message
- [X] T047 [P] [US2] Write msw handlers for `POST /api/vms/{name}/start` and `POST /api/vms/{name}/stop` in `frontend/tests/contract/mocks/vms-start.handler.ts` and `vms-stop.handler.ts`: success returns `{ "status": "running" }` / `{ "status": "stopped" }`; unknown name returns 404 with `{ "error": "..." }`
- [X] T048 [P] [US2] Write unit tests for Start/Stop button behavior in `frontend/tests/unit/components/VmCard.test.tsx`: (1) clicking Start calls `POST /api/vms/{name}/start` and re-fetches VM list on 200; (2) in-flight call shows spinner and disables button; (3) 404 response shows `ErrorBanner`; (4) OperationContext lock prevents concurrent clicks

### Implementation for User Story 2

- [X] T044 [P] [US2] Implement `power_on(name: str)` and `power_off(name: str)` in `backend/app/lib/hetzner.py`: call `client.servers.get_all(name=name)` → raise `HTTPException(404, "VM '{name}' not found or is not in the correct state")` if empty; call `server.power_on()` / `server.power_off()` wrapped with `asyncio.to_thread()`; raise `HTTPException(500)` with user-friendly message on SDK exception
- [X] T045 [US2] Implement `POST /vms/{name}/start` and `POST /vms/{name}/stop` in `backend/app/vms/router.py`: call `power_on(name)` / `power_off(name)`; return `{ "status": "running" }` / `{ "status": "stopped" }`; FastAPI exception handlers propagate 404/500 with `{ "error": detail }`; require `Depends(get_current_user)`
- [X] T046 [US2] Write integration tests for start/stop in `backend/tests/integration/test_vms.py` (mocked hcloud): (1) authenticated start → 200 `{ "status": "running" }`; (2) authenticated stop → 200 `{ "status": "stopped" }`; (3) unknown VM name → 404; (4) unauthenticated → 401
- [X] T049 [US2] Wire Start and Stop buttons in `frontend/src/components/VmCard.tsx`: on click: `useOperation()` LOCK → `apiFetch(POST /api/vms/{name}/start|stop)` → UNLOCK → call `refreshVms()` on success → `ErrorBanner` on failure; button shows `Loader2` spinner SVG while in-flight; button re-enabled after response regardless of outcome (FR-013)

**Checkpoint**: US1 + US2 functional — basic VM lifecycle management delivered.

---

## Phase 5: User Story 3 — Archive a VM (Priority: P2)

**Goal**: Archive a running or stopped VM — create labeled Hetzner snapshot then delete server; stream step-by-step progress via SSE. If snapshot fails, server must NOT be deleted.

**Independent Test**: Click Archive on running VM → confirm dialog appears → confirm → ProgressSteps shows "Creating snapshot" then "Deleting server" with in-progress/done states → VM becomes Archived on dashboard. Simulate snapshot failure → error event emitted, server remains untouched.

### Tests for User Story 3 ⚠️ Write these FIRST — must FAIL before implementation begins

- [X] T050 [P] [US3] Write unit tests for `create_snapshot(name, server_id)` and `delete_server(server_id)` in `backend/tests/unit/test_hetzner.py`: (1) `create_snapshot` calls SDK with correct `labels={"vm-name": name}` → success; (2) SDK raises exception → `HTTPException(500)` with user-friendly message; (3) `delete_server` success; (4) `delete_server` raises exception → `HTTPException(500)`
- [X] T055 [P] [US3] Write msw SSE handler for `POST /api/vms/{name}/archive` in `frontend/tests/contract/mocks/vms-archive.handler.ts`: emits 4 events: `step "Creating snapshot" in-progress` → `step "Creating snapshot" done` → `step "Deleting server" in-progress` → `step "Deleting server" done` → `complete`; and a failure variant emitting `error` after first step with `completedSteps: []`
- [X] T056 [P] [US3] Write unit tests for Archive flow in `frontend/tests/unit/components/VmCard.test.tsx`: (1) Archive button visible for running/stopped, hidden for archived; (2) clicking Archive shows shadcn/ui Dialog with confirmation text; (3) after confirm, `EventSource` opens to `/api/vms/{name}/archive` and `ProgressSteps` renders 2 steps; (4) `complete` event refreshes VM list; (5) `error` event shows `ErrorBanner` with `completedSteps`

### Implementation for User Story 3

- [X] T051 [P] [US3] Implement `create_snapshot(name: str, server_id: int) -> int` in `backend/app/lib/hetzner.py`: resolve `Server` object; call `client.servers.create_image(server, image_type='snapshot', labels={"vm-name": name})` wrapped with `asyncio.to_thread()`; wait for action to complete; return snapshot image ID; raise `HTTPException(500)` with user-friendly detail on failure (FR-005)
- [X] T052 [P] [US3] Implement `delete_server(server_id: int)` in `backend/app/lib/hetzner.py`: resolve `Server` object; call `client.servers.delete(server)` wrapped with `asyncio.to_thread()`; raise `HTTPException(500)` on failure (FR-006)
- [X] T053 [US3] Implement `POST /vms/{name}/archive` SSE stream in `backend/app/vms/router.py`: define async generator that yields `ServerSentEvent` JSON objects; step 1: emit `{"kind":"step","step":{"step":"Creating snapshot","status":"in-progress"}}` → call `create_snapshot()` → if exception emit `{"kind":"error","message":"...","completedSteps":[]}` and return (do NOT proceed to delete, per FR-006); emit step done; step 2: emit `{"kind":"step","step":{"step":"Deleting server","status":"in-progress"}}` → call `delete_server()` → emit step done or error; emit `{"kind":"complete","summary":"VM '{name}' archived successfully."}`; wrap with `EventSourceResponse`; write `OperationLog` record on entry and update on completion; requires `Depends(get_current_user)`
- [X] T054 [US3] Write integration tests for archive SSE in `backend/tests/integration/test_vms.py` (mocked hcloud): (1) successful archive — read all SSE events and assert 4 step events + complete; (2) snapshot failure — assert error event emitted and delete NOT called; (3) `OperationLog` record created with correct `status`; (4) unauthenticated → 401
- [X] T057 [US3] Add Archive button + confirmation dialog + SSE client to `frontend/src/components/VmCard.tsx`: Archive button visible when `canArchive=true`; click opens shadcn/ui `Dialog` explaining server will be deleted with snapshot retained; on confirm: LOCK operation → open native `EventSource('/api/vms/{name}/archive')` → update `ProgressSteps` state as events arrive → on `complete` event: UNLOCK + `refreshVms()` → on `error` event: UNLOCK + show `ErrorBanner` with `completedSteps` (FR-011, FR-012, FR-013)

**Checkpoint**: US3 functional — archive flow complete with SSE progress display.

---

## Phase 6: User Story 4 — Restore a VM from Snapshot (Priority: P2)

**Goal**: Restore archived VM — find latest snapshot, create new server, update Cloudflare DNS, update firewall. Three-step SSE stream. Partial failure halts without rollback; completed steps reported.

**Independent Test**: Click Restore on archived VM → ProgressSteps shows 3 steps completing → VM shows as running with new IP. Simulate DNS failure → SSE `error` event with `completedSteps: ["Creating server from snapshot"]` → `ErrorBanner` lists completed step; server not deleted.

### Tests for User Story 4 ⚠️ Write these FIRST — must FAIL before implementation begins

- [X] T058 [P] [US4] Write unit tests for `create_server_from_snapshot(name, snapshot_id, db)` in `backend/tests/unit/test_hetzner.py`: (1) SDK `create` called with correct `server_type`, `location`, `ssh_keys` read from `AppConfig`; (2) returns `{"server_id": int, "public_ip": str}` when IP assigned; (3) no snapshot found → `HTTPException(404)`; (4) SDK error → `HTTPException(500)`
- [X] T059 [P] [US4] Write unit tests for `update_a_record(vm_name, new_ip, db)` in `backend/tests/unit/test_cloudflare.py`: mock Cloudflare REST API with `respx`; (1) successful zone lookup → record lookup → PATCH → returns; (2) zone not found → `HTTPException(502)` with user-friendly message; (3) DNS record not found → `HTTPException(502)`; (4) PATCH fails → `HTTPException(502)`
- [X] T060 [P] [US4] Write unit tests for `upsert_ip_rule(firewall_name, ip)` in `backend/tests/unit/test_hetzner.py`: (1) IP already in `source_ips` → returns `already_present=True`, setRules NOT called; (2) IP not present → appends rule, calls setRules, returns `already_present=False`; (3) firewall not found by name → `HTTPException(404)`
- [X] T066 [P] [US4] Write msw SSE handler for `POST /api/vms/{name}/restore` in `frontend/tests/contract/mocks/vms-restore.handler.ts`: 3-step success sequence ending with `complete` summary including new IP; and a DNS-failure variant emitting `error` after step 1 done with `completedSteps: ["Creating server from snapshot"]`
- [X] T067 [P] [US4] Write unit tests for Restore flow in `frontend/tests/unit/components/VmCard.test.tsx`: (1) Restore button visible only when `canRestore=true`; (2) EventSource opens on click; (3) ProgressSteps shows 3 steps updating; (4) `complete` event refreshes VM list showing new IP; (5) `error` event shows `ErrorBanner` listing `completedSteps` (FR-015)

### Implementation for User Story 4

- [X] T061 [P] [US4] Implement `create_server_from_snapshot(name: str, snapshot_id: int, db: AsyncSession) -> dict` in `backend/app/lib/hetzner.py`: read `hetzner_default_server_type`, `hetzner_default_location`, `hetzner_default_ssh_key` from `AppConfig` rows via `db`; call `client.servers.create(name=name, server_type=..., image=Image(id=snapshot_id), location=..., ssh_keys=[...])` wrapped with `asyncio.to_thread()`; poll until `public_net.ipv4.ip` is assigned; return `{"server_id": int, "public_ip": str}` (FR-014)
- [X] T062 [P] [US4] Implement `update_a_record(vm_name: str, new_ip: str, db: AsyncSession)` in `backend/app/lib/cloudflare.py`: query `VmConfig` by `vm_name` to get `domain`; extract zone root (last two domain labels); call Cloudflare REST API v4 via `httpx.AsyncClient`: `GET /zones?name={zone_root}` → `GET /zones/{zone_id}/dns_records?type=A&name={domain}` → `PATCH /zones/{zone_id}/dns_records/{record_id}` body `{"content": new_ip}`; `Authorization: Bearer {settings.CLOUDFLARE_API_TOKEN}`; raise `HTTPException(502)` with user-friendly message on any failure (FR-008)
- [X] T063 [US4] Implement `upsert_ip_rule(firewall_name: str, ip: str) -> bool` in `backend/app/lib/hetzner.py` (shared with US5): call `client.firewalls.get_all(name=firewall_name)` wrapped with `asyncio.to_thread()`; search existing rules for `{ip}/32` in `source_ips`; if found return `True` (idempotent, no API call); if not found append new TCP+UDP inbound ALLOW rule for `{ip}/32` and call `client.firewalls.set_rules(...)`; return `False`; raise `HTTPException(404)` if firewall not found (FR-009)
- [X] T064 [US4] Implement `POST /vms/{name}/restore` SSE stream in `backend/app/vms/router.py`: find latest snapshot — call `list_snapshots_by_label()` and filter by `vm_name=name`, sort by `created_at` descending, take first; if none emit `error` and return; async generator: step 1 `create_server_from_snapshot` → on exception emit `error {"completedSteps":[]}` and return; step 2 `update_a_record` → on exception emit `error {"completedSteps":["Creating server from snapshot"]}` and return (no rollback, FR-015); step 3 `upsert_ip_rule` with client IP from `X-Forwarded-For` header or `detect_public_ip()`; emit `complete {"summary":"VM '{name}' restored. IP: {public_ip}"}`; write `OperationLog`; wrap with `EventSourceResponse`; requires `Depends(get_current_user)`
- [X] T065 [US4] Write integration tests for restore SSE in `backend/tests/integration/test_vms.py` (mocked hcloud + respx Cloudflare): (1) full 3-step success → assert 6 step events + complete with IP in summary; (2) no snapshot → `error` event immediately, no server created; (3) DNS failure → `error` with `completedSteps: ["Creating server from snapshot"]`, server not rolled back; (4) `OperationLog` correct; (5) unauthenticated → 401
- [X] T068 [US4] Add Restore button + SSE client to `frontend/src/components/VmCard.tsx`: visible only when `canRestore=true`; on click: LOCK operation → open `EventSource('/api/vms/{name}/restore')` → update `ProgressSteps` for 3 steps as events arrive → on `complete` event: UNLOCK + `refreshVms()` (new IP visible in next fetch) → on `error` event: UNLOCK + show `ErrorBanner` with `completedSteps` listed (FR-011, FR-013, FR-015)

**Checkpoint**: US4 functional — restore creates server, updates DNS, updates firewall with SSE progress.

---

## Phase 7: User Story 5 — Firewall Auto-Update on Login (Priority: P2)

**Goal**: On every page load detect user's public IP and upsert it into the shared Hetzner firewall. Failures must be non-blocking — user can still use the dashboard.

**Independent Test**: Load dashboard from a known IP → firewall rule added; reload → `alreadyPresent=true`, no duplicate; simulate IP detection failure → only non-blocking warning shown below nav bar, dashboard still loads and VM actions still work.

### Tests for User Story 5 ⚠️ Write these FIRST — must FAIL before implementation begins

- [X] T069 [P] [US5] Write unit tests for `detect_public_ip(request)` in `backend/tests/unit/test_ip.py`: (1) `X-Forwarded-For` header present → returns first IP in list; (2) header absent → `httpx` calls `IP_REFLECTION_URL`, parses `{"ip":"..."}`, returns IP (mock with `respx`); (3) `IP_REFLECTION_URL` returns non-200 → `HTTPException(503, "Unable to detect your public IP at this time.")`; (4) network timeout → `HTTPException(503)`
- [X] T074 [P] [US5] Write msw handlers for `GET /api/ip` and `POST /api/firewall/sync` in `frontend/tests/contract/mocks/ip.handler.ts` and `frontend/tests/contract/mocks/firewall-sync.handler.ts`: `GET /api/ip` returns `{ "ip": "203.0.113.1" }`; `POST /api/firewall/sync` returns `{ "ip": "203.0.113.1", "alreadyPresent": false }` first call; `{ ..., "alreadyPresent": true }` second call; 503 variant for IP detection failure; 400 variant for invalid IP body

### Implementation for User Story 5

- [X] T070 [P] [US5] Implement `detect_public_ip(request: Request) -> str` in `backend/app/lib/ip.py`: read `X-Forwarded-For` header from `request.headers.get("X-Forwarded-For")`; if present use first IP (split by comma, strip); if absent make async `httpx.get(settings.IP_REFLECTION_URL, timeout=5.0)` and parse `response.json()["ip"]`; raise `HTTPException(503, "Unable to detect your public IP at this time.")` on any failure
- [X] T071 [P] [US5] Implement `GET /ip` in `backend/app/ip/router.py`: call `detect_public_ip(request)`; return `{ "ip": ip }`; on `HTTPException(503)` propagate as-is; requires `Depends(get_current_user)`
- [X] T072 [US5] Implement `POST /firewall/sync` in `backend/app/firewall/router.py`: parse `{ "ip": str }` request body; validate IPv4 format via `ipaddress.ip_address(ip)` — `400` on `ValueError`; read `hetzner_firewall_name` from `AppConfig` via `db`; call `upsert_ip_rule(firewall_name, ip)` (implemented in T063); return `{ "ip": ip, "alreadyPresent": bool }`; raise `HTTPException(500)` on upsert failure; requires `Depends(get_current_user)`
- [X] T073 [US5] Write integration tests for `GET /ip` and `POST /firewall/sync` in `backend/tests/integration/test_firewall.py` (respx for ipify + mocked hcloud): (1) `GET /ip` with `X-Forwarded-For` header → 200; (2) `GET /ip` without header → calls ipify mock → 200; (3) ipify failure → 503 user-friendly error; (4) `POST /firewall/sync` valid IP → 200 `{ alreadyPresent }` toggles; (5) invalid IP → 400; (6) unauthenticated → 401
- [X] T075 [US5] Integrate on-load firewall auto-update in `frontend/src/app/page.tsx`: in `useEffect` on mount — call `GET /api/ip` then `POST /api/firewall/sync`; on success: silent, no UI indicator; on any failure: show distinct non-blocking dismissible `WarningBanner` (separate from `ErrorBanner`; does NOT block dashboard or VM actions per US5 scenario 2); `WarningBanner` auto-dismisses after 10 s or user clicks ×

**Checkpoint**: All 5 user stories independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Config management API, E2E test suite, containerisation, and CI pipeline.

- [ ] T076 [P] Implement config CRUD routes in `backend/app/config/schemas.py` (`VmConfigOut`, `VmConfigCreate`, `VmConfigUpdate`, `AppConfigOut`, `AppConfigUpdate`) and `backend/app/config/router.py`: `GET /config/vm-configs`, `POST /config/vm-configs`, `PUT /config/vm-configs/{id}`, `DELETE /config/vm-configs/{id}`, `GET /config/app`, `PUT /config/app`; all require `Depends(get_current_user)`; 409 on duplicate `vm_name`; 404 on missing record (Routes 9–10 from contracts/api-routes.md)
- [ ] T077 [P] Write integration tests for config routes in `backend/tests/integration/test_config.py`: CRUD lifecycle for vm-configs; PUT app config updates values; duplicate vm_name → 409; unauthenticated → 401
- [ ] T078 [P] Write Playwright E2E for US1 in `frontend/tests/e2e/us1-dashboard.spec.ts`: load page; assert all 3 VM states rendered with correct badge colours; assert no Restore button on VM without snapshot; assert loading skeleton visible then resolves; assert ErrorBanner when API mocked to 500
- [X] T079 [P] Write Playwright E2E for US2 in `frontend/tests/e2e/us2-start-stop.spec.ts`: click Start on stopped VM → assert status badge changes to running; click Stop on running VM → assert status changes to stopped; assert Start button disabled during in-flight; assert ErrorBanner on 404
- [X] T080 [P] Write Playwright E2E for US3 in `frontend/tests/e2e/us3-archive.spec.ts`: click Archive → assert Dialog appears → confirm → assert ProgressSteps renders "Creating snapshot" then "Deleting server" steps → assert VM becomes Archived; assert snapshot-fail error shows ErrorBanner with completedSteps
- [X] T081 [P] Write Playwright E2E for US4 in `frontend/tests/e2e/us4-restore.spec.ts`: click Restore → assert ProgressSteps shows 3 steps completing → assert VM shows running with new IP; simulate DNS failure mid-stream → assert ErrorBanner lists step 1 as completed, no rollback text
- [X] T082 [P] Write Playwright E2E for US5 in `frontend/tests/e2e/us5-firewall.spec.ts`: load page → assert no blocking UI from firewall sync; assert WarningBanner appears and dismisses when ipify mocked to fail; assert second load shows no duplicate rule (alreadyPresent=true response, no visible change)
- [X] T083 [P] Write Playwright E2E for login/logout in `frontend/tests/e2e/us6-auth.spec.ts`: navigate to `/` unauthenticated → redirected to `/login`; submit wrong password → inline error shown; submit correct credentials → redirected to dashboard; click logout → redirected to `/login`; navigate to `/` after logout → redirected back to `/login`
- [X] T084 Create `backend/Dockerfile`: multi-stage build (`python:3.12-slim` builder → runtime); `COPY pyproject.toml`; `RUN pip install uv && uv pip install --system -e "."` (or equivalent); `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`
- [X] T085 Create `frontend/Dockerfile`: multi-stage Next.js build (`node:20-alpine` deps → builder → runner); `COPY package*.json`; `npm ci`; `npm run build`; `CMD ["node", "server.js"]`
- [X] T086 Create `docker-compose.yml` with 3 services: `db` (postgres:16, health-check, named volume), `backend` (build from `backend/Dockerfile`, `depends_on: db`, env from `backend/.env`), `frontend` (build from `frontend/Dockerfile`, `depends_on: backend`, env `API_URL=http://backend:8000`); create `docker-compose.test.yml` with `db_test` service and `backend` overriding `DATABASE_URL` to test DB
- [X] T087 Create CI pipeline in `.github/workflows/ci.yml`: 3 parallel jobs — (1) backend lint+typecheck (`ruff check backend/` + `mypy backend/`) + tests (`pytest --cov=app --cov-fail-under=80`); (2) frontend lint+typecheck (`npm run lint && tsc --noEmit`) + tests (`npm run test:coverage`); (3) Playwright E2E (`docker compose up -d db backend frontend && npm run test:e2e`); all jobs trigger on PR and push to `main`

---

## Dependency Graph

```
Phase 1 (Setup — Backend) ──────────────────────┐
Phase 1 (Setup — Frontend) ─────────────────────┤
                                                  ↓
Phase 2: Foundational (Backend + Frontend)
  T014–T024 (backend) must complete before US1 backend tasks
  T025–T033 (frontend) must complete before US1 frontend tasks
                                                  ↓
Phase 3: US1 (View Dashboard)                    [MVP — read-only]
  T034–T035 must complete before T036–T038
  T039–T040 must complete before T041–T042
  T036 (lib/hetzner.py list fns) → T037 (GET /vms route)
  T041 (VmCard) → T042 (page.tsx)
                                                  ↓
Phase 4: US2 (Start / Stop)
  T043 must fail before T044; T047–T048 before T049
  T044 → T045 → T046
  T049 requires VmCard from T041
                                                  ↓
Phase 5: US3 (Archive) ──────────────────────────┐
Phase 6: US4 (Restore)  ─────────────────────────┤ (can proceed in parallel once US2 done)
                                                  │
  US4 T063 (upsert_ip_rule) ←── US5 T072 (firewall/sync route)
                                                  ↓
Phase 7: US5 (Firewall Auto-Update)
                                                  ↓
Phase 8 (Polish): T076—T087
  T063 must exist before T072
  T076–T077 (config) independent of US1–US5 routes
  T078–T083 (E2E) require all feature phases complete
  T084–T086 (Docker) require T084 before T086
  T087 (CI) requires T084–T086
```

**US3 and US4 are sisters** — both wire into `VmCard.tsx` from US1, and US4 reuses `upsert_ip_rule` from T063 which also powers US5. Plan US3 and US4 in consecutive sprints.

---

## Parallel Execution Summary

| Phase | Parallel Tasks |
|-------|---------------|
| Phase 1 | T002 ∥ T003 (after T001); T006 ∥ T007 ∥ T008 ∥ T009 ∥ T010 (after T005); T012 ∥ T013 |
| Phase 2 Backend | T015 ∥ T016 (after T014); T019 ∥ T023 (after T015–T018); T028 ∥ T029 (frontend, after T025) |
| Phase 3 US1 | T034 ∥ T039 ∥ T040 (write tests first, all parallel); T036 ∥ T035 (parallel); T041 ∥ T038 (after T037) |
| Phase 4 US2 | T043 ∥ T047 ∥ T048 (tests first, parallel); T044 ∥ T047 (parallel); T046 after T045 |
| Phase 5 US3 | T050 ∥ T055 ∥ T056 (tests first, parallel); T051 ∥ T052 (implementation, parallel) |
| Phase 6 US4 | T058 ∥ T059 ∥ T060 ∥ T066 ∥ T067 (tests first, all parallel); T061 ∥ T062 (parallel) |
| Phase 7 US5 | T069 ∥ T074 (tests first, parallel); T070 ∥ T071 (parallel) |
| Phase 8 | T076 ∥ T077 ∥ T078 ∥ T079 ∥ T080 ∥ T081 ∥ T082 ∥ T083 ∥ T084 ∥ T085 (all parallel, after features) |

---

## Implementation Strategy

**MVP = Phase 1 + Phase 2 + Phase 3 (US1)** — read-only dashboard showing all VM states. Already valuable as a monitoring view without implementing any write operations.

**MVP+ = Phase 4 (US2)** — basic VM lifecycle management (start/stop).

**Full Feature = Phase 5 (US3) + Phase 6 (US4) + Phase 7 (US5)** — archive/restore with DNS + firewall, plus firewall auto-update on login.

**Suggested delivery order**: US1 → US2 (both P1, one sprint) → US3 → US4 (P2, second sprint, US4 reuses US3 lib functions) → US5 (P2, lightweight after US4) → Polish.
