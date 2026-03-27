# Research: Hetzner Cloud VM Management UI

**Branch**: `001-hetzner-vm-ui` | **Date**: 2026-03-26 (revised)
**Phase**: 0 — Outline & Research  
**Input**: Technical Context from plan.md + user requirement: "backend API in Python FastAPI"

---

## 1. Technology Stack

### Decision: Python 3.12 FastAPI (backend) + Next.js 14 App Router (frontend)

**Rationale**: Two-project split architecture. FastAPI handles all server-side concerns: authentication, Hetzner/Cloudflare API orchestration, SSE streaming, and database access. Next.js renders the React UI and reverse-proxies all `/api/*` calls to FastAPI via `next.config.ts` rewrites. This separation makes each layer independently testable and deployable while keeping credentials strictly server-side (FastAPI only).

**Why FastAPI over other Python frameworks**:  
- Native `async`/`await` support throughout — essential for non-blocking Hetzner API calls and SSE streaming.
- Built-in Pydantic v2 validation — request and response schemas are automatically enforced and documented.
- First-class OpenAPI docs generated at `/docs` — useful for testing routes without a frontend.
- `sse-starlette` integrates seamlessly with FastAPI's `StreamingResponse` pattern.

**Proxy architecture**: Next.js `next.config.ts` rewrites map `/api/:path*` → `{API_URL}/:path*`. The browser always calls same-origin (`/api/...`) — no CORS configuration required in production. FastAPI sees the proxied request with all original headers (including `Cookie`).

**Alternatives considered**:
- *Full-stack Next.js (previous plan)*: Eliminated because the user explicitly requires FastAPI. The Next.js API-routes-only approach cannot run Python.
- *Django REST Framework*: Heavier; synchronous by default; more boilerplate for a private tool.
- *Flask + Marshmallow*: Synchronous; no first-class async; no automatic schema enforcement.
- *Litestar*: Similar to FastAPI but smaller ecosystem; fewer `hcloud` / `sse-starlette` integration examples.

---

## 2. UI Component Library

### Decision: shadcn/ui + Tailwind CSS (unchanged)

**Rationale**: shadcn/ui provides copy-owned, accessible React components built on Radix UI primitives. All spacing, colour, and typography values use Tailwind design tokens — satisfying Constitution III. WCAG 2.1 AA, keyboard navigation, and screen reader support are built in, with no hardcoded style values.

**Alternatives considered**: See previous research — decision unchanged. The frontend technology stack is unchanged; only the backend changes.

---

## 3. Hetzner Cloud API Integration

### Decision: `hcloud` Python SDK (official)

**Rationale**: `hcloud` is the official Hetzner Cloud Python SDK. It provides a typed, synchronous client with all required operations. Since FastAPI uses async endpoints, `hcloud` calls are wrapped with `asyncio.to_thread()` to avoid blocking the event loop.

**Key operations**:

| Operation | SDK call |
|-----------|----------|
| List servers | `client.servers.get_all()` |
| Power on server | `client.servers.power_on(server)` |
| Power off server | `client.servers.power_off(server)` |
| Delete server | `client.servers.delete(server)` |
| Create snapshot | `client.servers.create_image(server, image_type='snapshot', labels={'vm-name': name})` |
| List snapshots by label | `client.images.get_all(type='snapshot', label_selector='vm-name')` |
| Create server from image | `client.servers.create(name=..., server_type=..., image=snapshot, location=..., ssh_keys=[...])` |
| Get firewall by name | `client.firewalls.get_all(name=firewall_name)` |
| Update firewall rules | `client.firewalls.set_rules(firewall, rules=[...])` |

**Wrapper location**: `backend/app/lib/hetzner.py` — one function per operation, each wrapped with `asyncio.to_thread()`. The `HCloudClient` is instantiated once with `HETZNER_API_TOKEN` from `pydantic-settings`.

**Alternatives considered**:
- *Direct `httpx` against Hetzner REST API*: Fully async but loses type safety and requires manual auth/error handling. Rejected in favour of the official SDK.
- *`hcloud-python` community fork*: Same underlying library; not needed.

---

## 4. Cloudflare API Integration

### Decision: `httpx` (async) with direct Cloudflare REST API calls

**Rationale**: The official Cloudflare Python SDK (`cloudflare`) wraps a synchronous client that does not support `asyncio.to_thread()` cleanly. `httpx` provides a fully async HTTP client with first-class FastAPI compatibility. Only two Cloudflare operations are needed (list DNS records, update A record) — implementing these directly with `httpx` is simpler than adding an SDK dependency.

**Key operations**:

| Operation | Endpoint |
|-----------|----------|
| List DNS records in zone | `GET /zones/{zone_id}/dns_records?type=A&name={hostname}` |
| Update A record IP | `PATCH /zones/{zone_id}/dns_records/{record_id}` body `{ "content": "<new-ip>" }` |
| Resolve zone by name | `GET /zones?name={zone_root}` |

**Auth header**: `Authorization: Bearer {CLOUDFLARE_API_TOKEN}`.

**Wrapper location**: `backend/app/lib/cloudflare.py` — `update_a_record(vm_name: str, new_ip: str)` resolves domain from `vm_configs` DB, constructs zone root from domain, calls Cloudflare API.

**Alternatives considered**:
- *`cloudflare` PyPI SDK*: Synchronous client; poor async story. Rejected.
- *`cloudflare` PyPI SDK v4 (async)*: Experimental as of March 2026; API surface unstable. Rejected in favour of direct `httpx`.

---

## 5. Public IP Detection

### Decision: `httpx` async GET to `IP_REFLECTION_URL` with `X-Forwarded-For` fallback

**Rationale**: FastAPI reads the `X-Forwarded-For` request header first (populated by the Next.js proxy if the reverse proxy sets it). If absent, makes an async `httpx` GET to `IP_REFLECTION_URL` (default: `https://api.ipify.org?format=json`) and extracts `{ "ip": "..." }`. All detection logic is server-side in `backend/app/lib/ip.py`.

**Alternatives considered**: Same as previous research — approach is framework-agnostic.

---

## 6. Real-Time Progress for Long Operations

### Decision: `sse-starlette` + FastAPI `StreamingResponse`

**Rationale**: `sse-starlette` provides a `ServerSentEvent` helper and `EventSourceResponse` compatible with FastAPI/Starlette. Archive (2 steps) and restore (3 steps) operations are modelled as async generator functions that `yield` `ServerSentEvent` objects as each step completes. FastAPI wraps the generator in `EventSourceResponse`.

**SSE generator pattern**:

```python
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
import json

async def archive_vm_stream(name: str, db: AsyncSession) -> AsyncIterator[ServerSentEvent]:
    yield ServerSentEvent(data=json.dumps({"kind": "step", "step": {"step": "Creating snapshot", "status": "in-progress"}}))
    try:
        await create_snapshot(name)
        yield ServerSentEvent(data=json.dumps({"kind": "step", "step": {"step": "Creating snapshot", "status": "done"}}))
    except Exception as e:
        yield ServerSentEvent(data=json.dumps({"kind": "error", "message": str(e), "completedSteps": []}))
        return
    # ... step 2 ...

@router.post("/vms/{name}/archive")
async def archive(name: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return EventSourceResponse(archive_vm_stream(name, db))
```

**Client**: Native browser `EventSource` API (unchanged from previous design).

**Alternatives considered**:
- *FastAPI `BackgroundTasks` + polling*: Requires server-side state store for operation progress tracking — adds unnecessary complexity.
- *WebSockets*: Bidirectional overhead for a one-directional push stream.

---

## 7. Testing Strategy

### Decision: Backend: pytest + pytest-asyncio + httpx + respx; Frontend: Vitest + RTL + msw + Playwright

| Layer | Tool | Scope |
|-------|------|-------|
| Backend unit | pytest + respx | `lib/hetzner.py`, `lib/cloudflare.py`, `lib/ip.py` — httpx calls mocked with `respx` |
| Backend integration | pytest-asyncio + httpx.AsyncClient | All FastAPI routes via ASGI test client; real PostgreSQL test DB |
| Frontend component | Vitest + React Testing Library | `VmCard`, `LoginForm`, `ProgressSteps`, `ErrorBanner` — all interactive states |
| Frontend contract | msw (mock service worker) | Mock FastAPI response shapes; validate frontend fetch calls |
| E2E | Playwright | Full user story flows US1–US6 against local Next.js + FastAPI dev stack |

**Backend test client**:

```python
# conftest.py
@pytest.fixture
async def client(app):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
```

**Coverage gate**: `pytest --cov=app --cov-fail-under=80` (backend). Vitest `--coverage lines: 80` (frontend).  
**Async test config**: `pytest.ini` → `asyncio_mode = auto` (via `pytest-asyncio`).  
**Test DB**: Separate `DATABASE_URL_TEST` PostgreSQL database; `alembic upgrade head` run in `conftest.py` session fixture.

**Alternatives considered**:
- *Mock Pydantic/SQLAlchemy models in backend tests*: Fragile; masks real DB constraint violations. Rejected — real test DB used.
- *Playwright against mocked backend*: Would miss FastAPI route validation and auth. Rejected — Playwright runs against live stack.

---

## 8. State Management (Frontend)

### Decision: React `useContext` + `useReducer` for operation lock state (unchanged)

**Rationale**: Single-user tool with ~20 VMs. Global state needs remain minimal: which VM (if any) has an in-progress operation. `OperationContext` (React context + reducer) tracks `{ vmName: string | null; operation: string | null }`. No Redux or Zustand overhead.

---

## 9. Environment Configuration Schema

**Two `.env` files — strictly separated by tier:**

**`backend/.env`** — All secrets and backend config (never shared with frontend):

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
ACCESS_TOKEN_EXPIRE_MINUTES=1440   # 24 hours

# ── IP Detection ──────────────────────────────────────────────────────
IP_REFLECTION_URL=https://api.ipify.org?format=json
```

**`frontend/.env.local`** — Only non-sensitive frontend config:

```env
# URL where FastAPI is running — used by Next.js rewrites (server-side only)
API_URL=http://localhost:8000
```

**Operational configuration** (firewall name, server defaults, VM→DNS mappings) remains database-stored in `app_configs` and `vm_configs` tables (seeded at first deploy). These are NOT environment variables.

---

## 10. Database

### Decision: PostgreSQL 16 + SQLAlchemy 2 (async) + Alembic

**Rationale**: Same decision as previous research — PostgreSQL is the right choice. The ORM switches from Prisma (Node.js) to **SQLAlchemy 2** with async support (`sqlalchemy[asyncio]` + `asyncpg` driver).

SQLAlchemy 2 provides:
- Fully async session management (`AsyncSession`) compatible with FastAPI's dependency injection.
- Declarative ORM models with type-annotated column definitions.
- All migrations managed by **Alembic** (the native SQLAlchemy migration tool) — `alembic revision --autogenerate` generates migration scripts from model changes.

**Schema** (SQLAlchemy ORM models in `backend/app/models/db.py`):

```python
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id           = Column(Integer, primary_key=True)
    username     = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)           # bcrypt hash; cost factor 12
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class VmConfig(Base):
    __tablename__ = "vm_configs"
    id         = Column(Integer, primary_key=True)
    vm_name    = Column(String, unique=True, nullable=False)  # exact Hetzner VM name
    domain     = Column(String, nullable=False)               # full Cloudflare domain
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AppConfig(Base):
    __tablename__ = "app_configs"
    id       = Column(Integer, primary_key=True)
    key      = Column(String, unique=True, nullable=False)
    value    = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class OperationLog(Base):
    __tablename__ = "operation_logs"
    id           = Column(Integer, primary_key=True)
    vm_name      = Column(String, nullable=False)
    operation    = Column(String, nullable=False)    # 'start'|'stop'|'archive'|'restore'
    status       = Column(String, nullable=False)    # 'in-progress'|'done'|'error'
    steps_json   = Column(String, nullable=True)     # JSON-serialised OperationStep list
    started_at   = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
```

**`app_configs` known keys** (seeded by `backend/scripts/seed.py`):

| Key | Description |
|-----|-------------|
| `hetzner_firewall_name` | Shared Hetzner firewall name |
| `hetzner_default_server_type` | e.g. `cx22` |
| `hetzner_default_location` | e.g. `nbg1` |
| `hetzner_default_ssh_key` | SSH key name registered in Hetzner |

**Async DB session dependency** (`backend/app/database.py`):

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
```

**Alternatives considered**:
- *Prisma for Python (prisma-client-py)*: Experimental; less mature than SQLAlchemy; async support is alpha-quality. Rejected.
- *Tortoise ORM*: Good async story but smaller community; less Alembic integration. Rejected.
- *SQLite*: Zero-infrastructure for dev but diverges from PostgreSQL in production. Rejected (same reasoning as previous plan).

---

## 11. Authentication

### Decision: FastAPI JWT (python-jose) + passlib[bcrypt] + httpOnly cookie

**Rationale**: FastAPI handles auth end-to-end. No NextAuth.js needed. The flow:

1. Browser POSTs `{ username, password }` JSON to `/api/auth/token` (proxied to FastAPI `POST /auth/token`).
2. FastAPI verifies password against `users.password_hash` using `passlib.verify()`.
3. On success, FastAPI creates a JWT (`python-jose`, signed with `SECRET_KEY`, `HS256`, 24 h TTL).
4. FastAPI sets `Set-Cookie: access_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/`.
5. Next.js proxy forwards the `Set-Cookie` header to the browser.
6. Browser stores the cookie automatically. All subsequent requests include it.
7. FastAPI reads the cookie via a `get_current_user` dependency:

```python
from fastapi import Cookie, HTTPException
from jose import jwt, JWTError
from app.config import settings

async def get_current_user(access_token: str = Cookie(None), db: AsyncSession = Depends(get_db)) -> User:
    if access_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

8. Next.js `middleware.ts` reads the `access_token` cookie and redirects to `/login` if absent (the cookie is `httpOnly` but Next.js server-side middleware CAN read it via `request.cookies.get('access_token')`).

**Password hashing**: `passlib.context.CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)`. Cost-12 ≈ 200 ms — within the 500 ms p95 login SLO.

**Initial user provisioning**: `backend/scripts/seed.py` creates an initial `admin` user using `ADMIN_PASSWORD` env var (read at seed time, never stored). Script is idempotent (`INSERT ... ON CONFLICT DO NOTHING`).

**Alternatives considered**:
- *NextAuth.js + FastAPI token endpoint*: Would require NextAuth in the frontend and a JWT endpoint in FastAPI — duplicate auth logic. Rejected.
- *OAuth2 `password` grant via FastAPI's `OAuth2PasswordBearer`*: Standard for APIs but uses `Authorization: Bearer` header, not cookies. Requires frontend JS to manage and attach the token to every request — more complex than httpOnly cookie. Rejected.
- *Session-based auth (server-side sessions)*: Requires a session store (Redis or DB); stateful. JWT is simpler for a single-server deployment. Rejected.

---

## 12. Configuration Migration (env vars → DB)

### Decision: Seed-based migration via `backend/scripts/seed.py`; runtime DB reads via SQLAlchemy

**Rationale**: Identical to previous plan — operational config (firewall name, server defaults, VM→DNS mappings) is stored in `app_configs` and `vm_configs` DB tables. FastAPI reads them at operation time via `get_db()` dependency. Config update API (`GET/PUT /config/app`, `CRUD /config/vm-configs`) is authenticated.

**Migration path**: First-deploy seed reads any legacy env vars (`HETZNER_FIREWALL_NAME`, `VM_DNS_MAP`, etc.) and inserts them into the DB tables. After seeding, those env vars are removed from `backend/.env`.

---

## Summary of Decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Stack | FastAPI (Python 3.12) + Next.js 14 | User requirement; Python `hcloud` SDK + async SSE |
| UI | shadcn/ui + Tailwind CSS | WCAG 2.1 AA, design tokens, accessible — unchanged |
| Hetzner client | `hcloud` Python SDK + `asyncio.to_thread` | Official SDK, typed; wrapped for async |
| Cloudflare client | `httpx` async (direct REST) | Fully async; avoids sync SDK |
| IP detection | httpx + X-Forwarded-For | Server-side; async |
| Progress streaming | `sse-starlette` + FastAPI `EventSourceResponse` | First-class SSE in FastAPI |
| Backend testing | pytest + pytest-asyncio + httpx + respx | Full async test pyramid; real test DB |
| Frontend testing | Vitest + RTL + msw + Playwright | Unchanged; msw mocks FastAPI response shapes |
| State | React Context (frontend only) | Unchanged — right-sized |
| Config (secrets) | `backend/.env` only | Credentials never in DB or frontend |
| Database | PostgreSQL 16 + SQLAlchemy 2 async + Alembic | Official SQLAlchemy async; typed; migration-managed |
| Authentication | FastAPI JWT + passlib[bcrypt] + httpOnly cookie | Single auth layer; no NextAuth.js needed |
| Config (non-secret) | PostgreSQL `app_configs` + `vm_configs` | Live config updates without redeploy |

**Rationale**: A full-stack Next.js project keeps the entire codebase in one TypeScript repository. API routes on the server handle all Hetzner Cloud and Cloudflare API calls — credentials never reach the browser. React (via Next.js) provides the reactive UI needed for real-time progress streaming. No separate backend process is required; a single `next start` (or Docker container) serves the entire application.

**Alternatives considered**:
- *Python (FastAPI) + React SPA*: Two codebases, two runtimes, two deployment units. More overhead than justified for a single-user tool.
- *Streamlit / Gradio*: Simple but poor UX customisation; cannot satisfy Constitution III design-system requirements without significant workarounds.
- *Plain HTML + Vanilla JS + Express*: No type safety, no component model; testing surface is harder to structure; rejected in favour of TypeScript.
- *SvelteKit*: Viable alternative, but Next.js has broader ecosystem precedent for server-side API integrations of this kind.

---

## 2. UI Component Library

### Decision: shadcn/ui + Tailwind CSS

**Rationale**: shadcn/ui provides copy-owned, accessible React components built on Radix UI primitives. It satisfies Constitution III requirements out of the box: all spacing, colour, and typography values use Tailwind design tokens; components pass WCAG 2.1 AA; keyboard navigation and screen reader support are built in. There are no hardcoded style values.

**Alternatives considered**:
- *MUI (Material UI)*: Full design system but large bundle; opinionated visual style; className-level token overrides required to avoid hardcoded values.
- *Mantine*: Good accessibility, but requires additional Tailwind integration; fewer Next.js App Router examples.
- *Headless UI alone*: Requires building all component primitives from scratch; too much overhead for a private tool.

---

## 3. Hetzner Cloud API Integration

### Decision: `@hetzner-cloud/sdk` (official Node.js SDK)

**Key endpoints used**:

| Operation | SDK method |
|-----------|-----------|
| List servers | `client.servers.getAll()` |
| Power on server | `client.servers.powerOn(id)` |
| Power off server | `client.servers.powerOff(id)` |
| Delete server | `client.servers.delete(id)` |
| Create snapshot | `client.servers.createImage(id, { type: 'snapshot', description, labels })` |
| List snapshots by label | `client.images.getAll({ type: 'snapshot', label_selector: 'vm-name=<name>' })` |
| Create server from image | `client.servers.create({ name, server_type, image: snapshotId, location, ssh_keys })` |
| Get firewall by name | `client.firewalls.getAll({ name })` |
| Update firewall rules | `client.firewalls.setRules(id, { rules })` |

**Snapshot labelling convention**: When archiving VM `myvm`, the snapshot is created with `labels: { 'vm-name': 'myvm' }`. Dashboard queries `images.getAll({ label_selector: 'vm-name' })` to enumerate all archived VMs (VM names present in labels but not in live servers).

**Latest snapshot selection**: Among all snapshots sharing label `vm-name=<name>`, the one with the highest `created` timestamp is selected for restore.

**Firewall update strategy**: The shared firewall contains a set of `ALLOW` rules for TCP/UDP inbound. On login and on restore, the current user IP is upserted: existing rules are fetched, the user's IP rule is replaced if present (matched by IP) or appended if absent. The full updated rule set is sent via `setRules`. This is idempotent — no duplicate rules are created (FR-009, US5 scenario 3).

**Alternatives considered**:
- *Direct `fetch` against Hetzner REST API*: More explicit but requires manual auth headers, error mapping, and response parsing. SDK handles this with TypeScript types.

---

## 4. Cloudflare API Integration

### Decision: `cloudflare` npm SDK (official)

**Key operations**:

| Operation | SDK method |
|-----------|-----------|
| List DNS records in zone | `client.dns.records.list({ zone_id })` |
| Update A record | `client.dns.records.update(recordId, { content: newIp })` |

**Zone and record resolution**: On restore, the VM name is looked up in the `VM_DNS_MAP` environment variable (e.g., `myvm=myvm.example.com`). The domain is split into zone (`example.com`) and subdomain (`myvm`). The Cloudflare API is used to resolve `zone_id` by zone name, then find the A record for the full domain name. The record's `content` field is updated with the new server IP.

**Alternatives considered**:
- *Direct `fetch` against Cloudflare REST API*: Viable; Cloudflare's SDK is relatively thin. Chosen for type safety and to maintain consistency with Hetzner SDK pattern.

---

## 5. Public IP Detection

### Decision: `https://api.ipify.org?format=json` (primary) with `https://checkip.amazonaws.com` as fallback

**Rationale**: ipify returns `{ "ip": "x.x.x.x" }`, which is easy to parse. AWS checkip returns a plain-text IP. Both are reliable, free, and have long track records. The server-side API route (`GET /api/ip`) calls ipify and returns the detected IP to the browser.

**Security note**: IP detection is performed server-side (Next.js API route). The detected IP is the IP of the **server running Next.js** when the user is on localhost (local dev), or the **reverse-proxy/load-balancer IP** if deployed behind one. For self-hosted deployments where the UI runs on the same machine the user is accessing from (or where the proxy forwards `X-Forwarded-For`), the route reads `X-Forwarded-For` → falls back to `ipify`.

**Implementation**: API route checks `X-Forwarded-For` header first (set by reverse proxy), then calls ipify. Returns `{ ip: string }`.

---

## 6. Real-Time Progress for Long Operations

### Decision: Server-Sent Events (SSE) via Next.js Route Handler streaming response

**Rationale**: Archive (2 steps: create snapshot → delete server) and Restore (3 steps: create server → update DNS → update firewall) are sequential operations lasting 30–120 seconds. SSE delivers each step result to the browser as it completes without polling overhead. Next.js App Router route handlers support streaming responses via `ReadableStream` or `TransformStream`. The client uses the native `EventSource` API.

**Event format**:
```json
{ "step": "Creating snapshot", "status": "in-progress" }
{ "step": "Creating snapshot", "status": "done" }
{ "step": "Deleting server",   "status": "in-progress" }
{ "step": "Deleting server",   "status": "done" }
{ "step": "archive",           "status": "complete" }
```

On failure:
```json
{ "step": "Updating DNS", "status": "error", "message": "Cloudflare zone not found" }
```

The stream is closed after the final event. The UI `ProgressSteps` component renders each event as a step row with icon (spinner → check / x).

**Alternatives considered**:
- *Polling a status endpoint*: Simpler but requires a server-side state store to track operation progress per-request (adds complexity).
- *WebSockets*: Overkill for a one-directional progress feed.
- *Long-polling*: Fragile; no benefit over SSE for this use case.

---

## 7. Testing Strategy

### Decision: Vitest + React Testing Library + Playwright + msw

| Layer | Tool | Scope |
|-------|------|-------|
| Unit | Vitest | `lib/hetzner/*.ts`, `lib/cloudflare/*.ts`, `lib/ip.ts`, utility functions |
| Component | Vitest + React Testing Library | `VmCard`, `ProgressSteps`, `ErrorBanner` — all interactive states |
| Contract | msw (mock service worker) | Mock Hetzner and Cloudflare API shapes; assert request structure from `lib/` functions |
| Integration / E2E | Playwright | Full user story flows (US1–US5) against local Next.js server with msw active |

**Coverage gate**: Vitest `--coverage` enforced in CI with `lines: 80` threshold (Constitution II).  
**Test execution time**: Unit + component suite target < 60 s total; each unit test < 100 ms (Constitution II).

**TDD order**: For each story — write failing tests first → get reviewer sign-off → implement → green.

---

## 8. State Management

### Decision: React `useState` + `useContext` for operation lock state

**Rationale**: Single-user tool with ~20 VMs. Global state needs are minimal: which VM (if any) has an in-progress operation. A lightweight `OperationContext` (React context + reducer) tracks `{ vmName: string | null, operation: string | null }`. No Redux or Zustand overhead.

**Operation lock**: While `operationContext.vmName` is set, corresponding `VmCard` disables all action buttons and shows a spinner. This satisfies FR-013.

---

## 9. Environment Configuration Schema

**After the introduction of the database, environment variables are split into two tiers**:

**Tier 1 — Secrets (env vars, never in DB)**:

```env
# ── Hetzner Cloud API ────────────────────────────────────────────────
HETZNER_API_TOKEN=<token>

# ── Cloudflare API ───────────────────────────────────────────────────
CLOUDFLARE_API_TOKEN=<token>

# ── Database ─────────────────────────────────────────────────────────
DATABASE_URL=postgresql://postgres:password@localhost:5432/vmmanager

# ── Authentication ───────────────────────────────────────────────────
NEXTAUTH_SECRET=<random-32-byte-hex>       # Generate: openssl rand -hex 32
NEXTAUTH_URL=http://localhost:3000

# ── IP Detection ─────────────────────────────────────────────────────
# URL of a public IP reflection service returning JSON { "ip": "x.x.x.x" }
IP_REFLECTION_URL=https://api.ipify.org?format=json
```

**Tier 2 — Configuration (stored in DB, managed via seed or config API)**:

| Previously env var | Now stored in | DB table / key |
|--------------------|---------------|----------------|
| `HETZNER_FIREWALL_NAME` | `app_configs` | key: `hetzner_firewall_name` |
| `HETZNER_DEFAULT_SERVER_TYPE` | `app_configs` | key: `hetzner_default_server_type` |
| `HETZNER_DEFAULT_LOCATION` | `app_configs` | key: `hetzner_default_location` |
| `HETZNER_DEFAULT_SSH_KEY` | `app_configs` | key: `hetzner_default_ssh_key` |
| `VM_DNS_MAP` (per-VM entries) | `vm_configs` | rows: `vm_name`, `domain` |

These values are seeded by `prisma/seed.ts` on first deploy and can be updated via the `/api/config/*` routes.

---

## 10. Database

### Decision: PostgreSQL 16 + Prisma ORM

**Rationale**: PostgreSQL is the most robust open-source relational database, Docker-easy for local dev, and production-ready on any cloud provider. Prisma provides a TypeScript-first ORM with a declarative schema, auto-generated type-safe client, and a managed migration system (`prisma migrate dev`). The combination produces zero boilerplate for typed DB queries and eliminates an entire class of runtime type errors.

**Schema overview**:

```prisma
model User {
  id           Int      @id @default(autoincrement())
  username     String   @unique
  passwordHash String   @map("password_hash")
  createdAt    DateTime @default(now()) @map("created_at")
  updatedAt    DateTime @updatedAt @map("updated_at")
  @@map("users")
}

model VmConfig {
  id        Int      @id @default(autoincrement())
  vmName    String   @unique @map("vm_name")
  domain    String
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")
  @@map("vm_configs")
}

model AppConfig {
  id        Int      @id @default(autoincrement())
  key       String   @unique
  value     String
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")
  @@map("app_configs")
}

model OperationLog {
  id          Int       @id @default(autoincrement())
  vmName      String    @map("vm_name")
  operation   String    // 'start' | 'stop' | 'archive' | 'restore'
  status      String    // 'in-progress' | 'done' | 'error'
  stepsJson   String?   @map("steps_json")
  startedAt   DateTime  @default(now()) @map("started_at")
  completedAt DateTime? @map("completed_at")
  @@map("operation_logs")
}
```

**Testing strategy**: Integration tests use a separate `DATABASE_URL_TEST` PostgreSQL database seeded before each test run via `prisma migrate reset --skip-seed`. No Prisma client mocking — tests hit a real DB for correctness.

**Alternatives considered**:
- *SQLite*: Zero-infrastructure for local dev, but WAL-mode required for concurrent reads, no managed cloud offering, and operationally diverges from PostgreSQL in production edge cases. Rejected for a tool that could grow to multi-user.
- *Drizzle ORM*: Lighter, no Prisma Studio, less migration tooling maturity. Prisma chosen for better team familiarity and richer DX.
- *TypeORM*: Decorator-based, less ergonomic with Next.js App Router server components. Rejected.
- *PlanetScale (MySQL)*: Requires schema change workflow; MySQL dialect differences from PostgreSQL add friction. Rejected.

---

## 11. Authentication

### Decision: next-auth v5 (Auth.js) with Credentials provider + bcryptjs

**Rationale**: NextAuth.js is the canonical authentication library for Next.js. The Credentials provider allows username/password validation against the `users` table with bcrypt-hashed passwords. JWT sessions (stateless) are used — no session table required, reducing DB writes on every request. `src/middleware.ts` uses NextAuth's exported `auth()` middleware to protect all routes except `/login` and `/api/auth/*`.

**Password hashing**: `bcryptjs` with cost factor 12 (~200 ms on commodity hardware). This is within the 500 ms login SLO while being computationally expensive enough to resist brute-force.

**Session strategy**:
- JWT sessions with 24 h max-age and rolling expiry on activity.
- Session contains `{ id, username }` — no sensitive data in JWT payload.
- `NEXTAUTH_SECRET` (32-byte random) signs and encrypts the JWT.

**Initial user provisioning**: `prisma/seed.ts` creates an initial `admin` user with a hashed password read from the `ADMIN_PASSWORD` env var (required at seed time, not stored). Re-run seed is idempotent (upsert by username).

**Route protection middleware** (`src/middleware.ts`):
- Public paths: `/login`, `/api/auth/*`
- All other paths: redirect to `/login` if no valid session.

**Alternatives considered**:
- *Custom JWT implementation*: Higher risk (token forgery, rotation), more code. Rejected.
- *Lucia Auth*: Good TypeScript types but smaller ecosystem; less Next.js App Router documentation. Rejected.
- *Clerk / Auth0*: Hosted SaaS; adds external dependency for a private self-hosted tool. Rejected.
- *HTTP Basic Auth at reverse-proxy level*: No user management, no session, no audit trail. Rejected.

---

## 12. Configuration Migration (env vars → DB)

### Decision: Seed-based migration via `prisma/seed.ts`; runtime reads from DB via Prisma; config update API for operators

**Rationale**: Moving `HETZNER_FIREWALL_NAME`, `HETZNER_DEFAULT_*`, and `VM_DNS_MAP` from `.env.local` to the database decouples configuration from deployment. Operators can update VM-to-DNS mappings or server defaults without redeploying. A `GET /api/config/vm-configs` and `PUT /api/config/app` endpoint (authenticated) exposes config for management.

**Migration path from env-var config**:
1. On first deploy, run `prisma/seed.ts` which reads the previous env vars (`HETZNER_FIREWALL_NAME`, etc.) and inserts them into `app_configs` and `vm_configs` tables.
2. Remove those env vars from `.env.local` after seeding.
3. All runtime code reads config from DB via `db.appConfig.findUnique({ where: { key } })` and `db.vmConfig.findUnique({ where: { vmName } })`.

**Security**: Config values in DB are non-sensitive (firewall names, domain names, server types). Credentials (`HETZNER_API_TOKEN`, `CLOUDFLARE_API_TOKEN`, `NEXTAUTH_SECRET`) always remain in env vars. DB config is protected by LoginAuth (all config routes require authentication).

**Alternatives considered**:
- *Keep config in env vars*: Simpler but requires redeploy for any config change. Rejected given the user's explicit requirement.
- *Config file on disk*: Fragile across Docker restarts if not mounted. Rejected.

---

## Summary of Decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Stack | Next.js 14 + TypeScript | Full-stack single codebase; credentials server-side |
| UI | shadcn/ui + Tailwind CSS | WCAG 2.1 AA, design tokens, accessible |
| Hetzner client | `@hetzner-cloud/sdk` | Official SDK, typed |
| Cloudflare client | `cloudflare` npm SDK | Official SDK, typed |
| IP detection | ipify + X-Forwarded-For | Reliable, free, server-side |
| Progress streaming | SSE via Next.js streaming route | No polling, native EventSource, simple |
| Testing | Vitest + RTL + Playwright + msw | Full pyramid; meets Constitution II gates |
| State | React Context | Right-sized; minimal global state |
| Config (secrets) | `.env.local` | Credentials never in DB |
| Database | PostgreSQL 16 + Prisma ORM | Typed, migration-managed, Docker-easy |
| Authentication | NextAuth.js v5 Credentials + bcryptjs | JWT sessions; users table; route middleware |
| Config (non-secret) | PostgreSQL via `app_configs` + `vm_configs` | Live updates without redeploy |
