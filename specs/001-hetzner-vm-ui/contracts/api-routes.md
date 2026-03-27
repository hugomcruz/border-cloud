# API Route Contracts: Hetzner Cloud VM Management UI

**Branch**: `001-hetzner-vm-ui` | **Date**: 2026-03-26 (revised)  
**Phase**: 1 — Design  
**Technology**: Python 3.12 FastAPI (backend service)  
**Base URL**: FastAPI serves at `http://localhost:8000` (dev) / `http://backend:8000` (Docker). The Next.js frontend proxies all browser requests: `next.config.ts` rewrites `/api/:path*` → `{API_URL}/:path*`. From the browser’s perspective every call is same-origin at `/api/*` — no CORS configuration needed.  
**Auth**: All routes require a valid `access_token` `httpOnly` cookie set by `POST /auth/token` **except** `/auth/token` (login) and `/auth/logout` which are public. FastAPI validates the cookie via the `get_current_user()` dependency (`python-jose` JWT, `HS256`, 24 h TTL). Unauthenticated requests to protected routes return `401 Unauthorized`. Route protection is also enforced by Next.js `middleware.ts` (redirects to `/login` if cookie is absent).

All request/response bodies are `application/json`. SSE endpoints use `text/event-stream`.

---

## Route 1 — List VMs

```
GET /api/vms
```

Returns the merged view of live Hetzner servers and archived (snapshot-only) VMs.

### Response `200 OK`

```typescript
{
  vms: VirtualMachine[]   // see data-model.md
}
```

**Derivation**:
1. Fetch all Hetzner servers → live VMs (`running` / `stopped`).
2. Fetch all Hetzner snapshots with label `vm-name` → potential archived VMs.
3. Any VM name appearing in snapshots but NOT in the live servers list is added as `status: 'archived'` with its latest snapshot.
4. Live VMs also have their `latestSnapshot` populated if a labeled snapshot exists for them.

**Caching**: Next.js `fetch` revalidation of 30 s on the Hetzner list calls (server-side TTL) to stay within Hetzner API rate limits while meeting SC-001 (< 3 s load).

### Response `500 Internal Server Error`

```typescript
{ error: string }  // user-friendly message; never raw API error
```

### Errors handled
- Hetzner API unavailable → `500` with `"Unable to reach Hetzner Cloud. Please try again."`

---

## Route 2 — Start a VM

```
POST /api/vms/:name/start
```

Powers on a stopped Hetzner server identified by its name.

### Path Parameters
| Param | Type | Description |
|-------|------|-------------|
| `name` | `string` | VM name as shown on dashboard |

### Response `200 OK`

```typescript
{ status: 'running' }
```

### Response `404 Not Found`

```typescript
{ error: string }  // e.g., "VM 'myvm' not found or is not in a stopped state"
```

### Response `500 Internal Server Error`

```typescript
{ error: string }
```

---

## Route 3 — Stop a VM

```
POST /api/vms/:name/stop
```

Powers off a running Hetzner server (graceful shutdown).

### Path Parameters
| Param | Type | Description |
|-------|------|-------------|
| `name` | `string` | VM name |

### Response `200 OK`

```typescript
{ status: 'stopped' }
```

### Response `404 Not Found`

```typescript
{ error: string }
```

### Response `500 Internal Server Error`

```typescript
{ error: string }
```

---

## Route 4 — Archive a VM (SSE)

```
POST /api/vms/:name/archive
Content-Type: application/json  (request body empty)
Accept: text/event-stream
```

Multi-step operation: creates a Hetzner snapshot (labeled `vm-name=<name>`), then deletes the server. Progress is streamed via Server-Sent Events.

### Path Parameters
| Param | Type | Description |
|-------|------|-------------|
| `name` | `string` | VM name |

### SSE Event Stream (response `text/event-stream`)

Events are newline-delimited JSON objects prefixed with `data: `.

**Step event** (emitted at start and completion of each step):
```typescript
data: { "kind": "step", "step": { "step": string, "status": OperationStepStatus } }
```

**Complete event** (emitted after all steps succeed):
```typescript
data: { "kind": "complete", "summary": "VM 'myvm' archived successfully." }
```

**Error event** (emitted on failure; stream closes):
```typescript
data: {
  "kind": "error",
  "message": string,           // user-friendly
  "completedSteps": string[]   // names of steps that succeeded before the error
}
```

**Archive step sequence**:
```
step: "Creating snapshot"   status: in-progress
step: "Creating snapshot"   status: done
step: "Deleting server"     status: in-progress
step: "Deleting server"     status: done
complete
```

### Error Behaviour
- If snapshot creation fails: `error` event emitted; server is NOT deleted (FR-006).
- If server deletion fails after snapshot success: `error` event emitted; snapshot is retained; `completedSteps: ["Creating snapshot"]`.

---

## Route 5 — Restore a VM (SSE)

```
POST /api/vms/:name/restore
Accept: text/event-stream
```

Multi-step operation: find latest snapshot by `vm-name` label, create new server, update Cloudflare DNS A record, update Hetzner firewall with user IP. Progress streamed via SSE.

### Path Parameters
| Param | Type | Description |
|-------|------|-------------|
| `name` | `string` | VM name (must have a snapshot with `vm-name=<name>` label) |

### Request Headers
| Header | Required | Description |
|--------|----------|-------------|
| `X-Forwarded-For` | Optional | Set by reverse proxy; used for IP detection if present |

### SSE Event Stream (response `text/event-stream`)

**Restore step sequence**:
```
step: "Creating server from snapshot"   status: in-progress
step: "Creating server from snapshot"   status: done
step: "Updating DNS"                    status: in-progress
step: "Updating DNS"                    status: done
step: "Updating firewall"               status: in-progress
step: "Updating firewall"               status: done
complete: { "summary": "VM 'myvm' restored. IP: 1.2.3.4" }
```

**Error event** (no rollback — FR-015):
```typescript
data: {
  "kind": "error",
  "message": string,
  "completedSteps": string[]  // e.g., ["Creating server from snapshot"] if DNS failed
}
```

### Error Behaviour
- No snapshot found for `vm-name=<name>` → `error` event immediately; no server is created.
- Server creation fails → `error` event; `completedSteps: []`.
- DNS update fails → `error` event; `completedSteps: ["Creating server from snapshot"]`; server NOT deleted.
- Firewall update fails → `error` event; `completedSteps: ["Creating server from snapshot", "Updating DNS"]`; server and DNS NOT rolled back.

---

## Route 6 — Detect Public IP

```
GET /api/ip
```

Returns the caller's detected public IPv4. Used by the browser on load to display the current IP and trigger firewall sync (US5).

### Response `200 OK`

```typescript
{ ip: string }  // e.g., { "ip": "203.0.113.42" }
```

**Detection logic** (server-side):
1. Read `X-Forwarded-For` header (first IP in list if behind proxy).
2. If not present, call `IP_REFLECTION_URL` (default: `https://api.ipify.org?format=json`).

### Response `503 Service Unavailable`

```typescript
{ error: "Unable to detect your public IP at this time." }
```

---

## Route 7 — Sync Firewall IP

```
POST /api/firewall/sync
Content-Type: application/json
```

Upserts the caller's public IP into the shared Hetzner Cloud firewall. Idempotent — if the IP is already present, no change is made.

### Request Body

```typescript
{
  ip: string   // IPv4 address to allow (from GET /api/ip)
}
```

### Response `200 OK`

```typescript
{
  ip: string;
  alreadyPresent: boolean;
}
```

### Response `400 Bad Request`

```typescript
{ error: "Invalid IP address format." }
```

### Response `500 Internal Server Error`

```typescript
{ error: string }
```

**Firewall update logic**:
1. Fetch the firewall by `app_configs` key `hetzner_firewall_name` (from DB).
2. Find any existing rule whose `source_ips` contains `<ip>/32`.
3. If found → no change, return `alreadyPresent: true`.
4. If not found → append new `ALLOW` rule for `<ip>/32` (TCP+UDP inbound), call `setRules` with full updated set.
5. Return `alreadyPresent: false`.

---

## Route 8 — Authentication (FastAPI JWT)

```
POST /auth/token    # Login — issues JWT access token cookie
POST /auth/logout   # Logout — clears the access_token cookie
```

These routes are **public** (no token required). They are served by FastAPI and proxied by Next.js as `/api/auth/token` and `/api/auth/logout`.

### Login — `POST /auth/token`

**Request body** (`application/json`):

```typescript
{
  username: string;   // plaintext — transmitted over HTTPS only; never logged
  password: string;   // plaintext — transmitted over HTTPS only; never logged
}
```

FastAPI verifies `password` against `users.password_hash` via `passlib.context.CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)`. JWT is signed with `SECRET_KEY` using `HS256`; TTL = `ACCESS_TOKEN_EXPIRE_MINUTES` (default 1440 = 24 h).

**Response `200 OK`**:

```typescript
{ access_token: string; token_type: "bearer" }
```

FastAPI also sets:

```
Set-Cookie: access_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/
```

The Next.js proxy forwards this `Set-Cookie` header to the browser. The browser stores the cookie automatically. All subsequent requests include it.

**Response `401 Unauthorized`** (wrong password or unknown user):

```typescript
{ detail: "Incorrect username or password" }
```

The `LoginForm` component reads this error and displays an inline error message without exposing which of the two fields was wrong.

### Logout — `POST /auth/logout`

**Response `200 OK`**:

```typescript
{ message: "Logged out" }
```

FastAPI responds with:

```
Set-Cookie: access_token=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0
```

This instructs the browser to delete the `access_token` cookie. Next.js `middleware.ts` will redirect the next request to `/login` because the cookie is gone.

### Security Notes
- Password never logged: the `verify_password()` function never logs the plaintext password.
- CSRF: `SameSite=Lax` mitigates CSRF for state-changing requests from cross-origin top-level navigation. SSE endpoints and mutation routes also benefit from this policy.
- Brute-force: bcrypt cost-12 makes brute-force expensive (≈ 200 ms/attempt). Rate-limiting (e.g. `slowapi`) can be added as a follow-up hardening step.
- The `access_token` cookie is `HttpOnly` — not readable by JavaScript. Next.js `middleware.ts` reads it server-side via `request.cookies.get('access_token')`.

---

## Route 9 — VM Config (DNS Mappings)

```
GET  /api/config/vm-configs
POST /api/config/vm-configs
PUT  /api/config/vm-configs/:id
DELETE /api/config/vm-configs/:id
```

Manages `VmConfig` rows (VM name → Cloudflare domain mappings). All endpoints **require authentication**.

### GET /api/config/vm-configs — List all VM configs

**Response `200 OK`**:

```typescript
{
  vmConfigs: Array<{
    id: number;
    vmName: string;
    domain: string;
    createdAt: string;
    updatedAt: string;
  }>
}
```

### POST /api/config/vm-configs — Create VM config

**Request body**:

```typescript
{
  vmName: string;  // unique; must match Hetzner VM name exactly
  domain: string;  // full domain, e.g., "myvm.example.com"
}
```

**Response `201 Created`**: The created `VmConfig` object.

**Response `409 Conflict`**: `{ error: "A config for VM 'myvm' already exists." }`

**Response `400 Bad Request`**: `{ error: string }` — missing required fields.

### PUT /api/config/vm-configs/:id — Update VM config

**Request body**: `{ domain: string }` 

**Response `200 OK`**: Updated `VmConfig` object.

**Response `404 Not Found`**: `{ error: string }`

### DELETE /api/config/vm-configs/:id — Remove VM config

**Response `204 No Content`**: (empty body)

**Response `404 Not Found`**: `{ error: string }`

---

## Route 10 — App Config (Operational Settings)

```
GET /api/config/app
PUT /api/config/app
```

Manages `AppConfig` key-value rows for operational settings. All endpoints **require authentication**.

### GET /api/config/app — Get all app settings

**Response `200 OK`**:

```typescript
{
  config: {
    hetzner_firewall_name: string;
    hetzner_default_server_type: string;
    hetzner_default_location: string;
    hetzner_default_ssh_key: string;
  }
}
```

### PUT /api/config/app — Update app settings

**Request body**: Partial object — only supplied keys are updated.

```typescript
{
  hetzner_firewall_name?: string;
  hetzner_default_server_type?: string;
  hetzner_default_location?: string;
  hetzner_default_ssh_key?: string;
}
```

**Response `200 OK`**: Full updated config object (same shape as GET).

**Response `400 Bad Request`**: Unknown key supplied or empty value. `{ error: string }`

---

## Contract Test Coverage (msw handlers)

Each externally-callable route MUST have a corresponding msw handler in `tests/contract/mocks/`:

| Route | msw handler file | Notes |
|-------|-----------------|-------|
| `GET /api/vms` | `vms-list.handler.ts` | mocks Hetzner servers + images API |
| `POST /api/vms/:name/start` | `vms-start.handler.ts` | mocks Hetzner power-on |
| `POST /api/vms/:name/stop` | `vms-stop.handler.ts` | mocks Hetzner power-off |
| `POST /api/vms/:name/archive` | `vms-archive.handler.ts` | SSE mock |
| `POST /api/vms/:name/restore` | `vms-restore.handler.ts` | SSE mock |
| `GET /api/ip` | `ip.handler.ts` | mocks ipify |
| `POST /api/firewall/sync` | `firewall-sync.handler.ts` | mocks Hetzner firewall API |
| `GET /api/config/vm-configs` | `config-vm-configs.handler.ts` | uses test DB |
| `PUT /api/config/app` | `config-app.handler.ts` | uses test DB |

Auth routes (`/api/auth/*`) are tested via Playwright E2E (`us6-login.spec.ts`) against the real Next.js server with a seeded test database — not via msw.

Contract tests assert:
- **Request shape**: correct HTTP method, path, and headers sent by `lib/` functions to Hetzner/Cloudflare.
- **Response mapping**: correct `VirtualMachine[]` / `OperationEvent` / `FirewallSyncResult` produced from mocked API responses.
- **Error mapping**: Hetzner/Cloudflare error responses are translated to user-friendly messages before reaching the client.
- **Auth enforcement**: requests to protected routes without a session cookie return `401`.
