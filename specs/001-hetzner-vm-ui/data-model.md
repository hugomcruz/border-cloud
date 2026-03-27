# Data Model: Hetzner Cloud VM Management UI

**Branch**: `001-hetzner-vm-ui` | **Date**: 2026-03-26 (revised)  
**Phase**: 1 — Design  
**Source**: `spec.md` (Key Entities) + `research.md` (tech stack decisions)  
**Frontend types**: `frontend/src/types/index.ts` | **Backend models**: `backend/app/models/db.py` | **Pydantic schemas**: `backend/app/vms/schemas.py`, `backend/app/auth/schemas.py`, `backend/app/config/schemas.py`

---

## Core Types

### `VmStatus`

Represents the computed display state of a virtual machine on the dashboard. This is a derived value — not stored in any database.

```typescript
type VmStatus = 'running' | 'stopped' | 'archived';
```

| Value | Source | Meaning |
|-------|--------|---------|
| `running` | Hetzner server `status === 'running'` | Server exists and is powered on |
| `stopped` | Hetzner server `status === 'off'` | Server exists but is powered off |
| `archived` | No live server; snapshot with `vm-name=<name>` label exists | Server deleted; only snapshot remains |

---

### `VirtualMachine`

The unified dashboard entity. For live servers (`running`/`stopped`) it is populated from the Hetzner Servers API. For archived VMs it is synthesised from snapshot label data.

```typescript
interface VirtualMachine {
  /** VM name as stored in Hetzner (live) or in snapshot label `vm-name` (archived) */
  name: string;

  /** Computed display status */
  status: VmStatus;

  /** Hetzner server ID — present only for live (running/stopped) VMs */
  serverId?: number;

  /** Public IPv4 address — present only for live VMs with an assigned IP */
  publicIp?: string;

  /** Latest snapshot associated with this VM via label `vm-name=<name>` — present if any snapshot exists */
  latestSnapshot?: Snapshot;

  /** True if a Restore action is available (archived AND latestSnapshot is present) */
  canRestore: boolean;

  /** True if an Archive action is available (running or stopped) */
  canArchive: boolean;

  /** True if Start is available (stopped) */
  canStart: boolean;

  /** True if Stop is available (running) */
  canStop: boolean;
}
```

**Derivation rules**:
- `canRestore` = `status === 'archived' && latestSnapshot !== undefined`
- `canArchive` = `status === 'running' || status === 'stopped'`
- `canStart`   = `status === 'stopped'`
- `canStop`    = `status === 'running'`

---

### `Snapshot`

Represents a Hetzner Cloud server image of type `snapshot`, associated with a VM via the `vm-name` label.

```typescript
interface Snapshot {
  /** Hetzner image ID */
  id: number;

  /** Human-readable image description (set by the system at archive time) */
  description: string;

  /** ISO 8601 creation timestamp from Hetzner API — used to determine "latest" */
  createdAt: string;

  /** The VM name stored as `labels['vm-name']` on the Hetzner image */
  vmName: string;
}
```

**Latest snapshot selection**: Among all `Snapshot[]` for a given `vmName`, the one with the lexicographically greatest `createdAt` (ISO 8601 strings sort correctly) is selected. No clock drift risk since Hetzner timestamps are server-authoritative.

---

### `OperationStep`

One step within a multi-step operation (archive or restore). Streamed via SSE to the client.

```typescript
type OperationStepStatus = 'pending' | 'in-progress' | 'done' | 'error';

interface OperationStep {
  /** Human-readable step label displayed in ProgressSteps component */
  step: string;

  /** Current status of this step */
  status: OperationStepStatus;

  /** Error message — present only when status === 'error'; user-friendly, no raw API text */
  message?: string;
}
```

**Archive steps** (in order):
1. `"Creating snapshot"`
2. `"Deleting server"`

**Restore steps** (in order):
1. `"Creating server from snapshot"`
2. `"Updating DNS"`
3. `"Updating firewall"`

---

### `OperationEvent`

The SSE event payload shape. The final event signals overall completion or failure.

```typescript
type OperationEventKind = 'step' | 'complete' | 'error';

interface OperationEvent {
  kind: OperationEventKind;

  /** Present when kind === 'step' */
  step?: OperationStep;

  /** Present when kind === 'complete' — summarises what was done */
  summary?: string;

  /** Present when kind === 'error' — top-level user-friendly error */
  message?: string;

  /**
   * Present when kind === 'error' on restore — lists steps that completed
   * before the failure, so the user can assess partial state (FR-015).
   */
  completedSteps?: string[];
}
```

---

### `FirewallSyncResult`

Response from `POST /api/firewall/sync`.

```typescript
interface FirewallSyncResult {
  /** The IP that was upserted into the firewall rule */
  ip: string;

  /** True if the IP was already present (no change made); false if a rule was added/updated */
  alreadyPresent: boolean;
}
```

---

### `IpDetectionResult`

Response from `GET /api/ip`.

```typescript
interface IpDetectionResult {
  ip: string;
}
```

---

## Entity Relationships

```text
Dashboard render:
  GET /api/vms  (authenticated)
    → [Hetzner servers list] + [Hetzner snapshots with label 'vm-name']
    → merged into VirtualMachine[]

Archive flow:
  VirtualMachine (running|stopped)
    → createSnapshot → Snapshot (with vm-name label)
    → deleteServer
    → OperationLog record written (status: done | error)
    → VirtualMachine becomes archived

Restore flow:
  VirtualMachine (archived, canRestore=true)
    → latestSnapshot (Snapshot with highest createdAt)
    → createServerFromSnapshot → new serverId + publicIp
    → VmConfig (DB) → domain for Cloudflare DNS update
    → AppConfig (DB, key: hetzner_firewall_name) → firewall upsert
    → OperationLog record written
    → VirtualMachine becomes running

Firewall auto-update on load:
  GET /api/ip → IpDetectionResult
  POST /api/firewall/sync → FirewallSyncResult
    → AppConfig (DB, key: hetzner_firewall_name) → firewall upsert

Authentication:
  POST /api/auth/token (FastAPI)
    → User (DB) → passlib bcrypt verify → python-jose JWT issued → Set-Cookie httpOnly
```

---

## State Transitions

```text
[running] ──stop──► [stopped] ──start──► [running]
[running] ──archive──► [archived]
[stopped] ──archive──► [archived]
[archived] ──restore──► [running]   (new server, same VM name)
```

All transitions are guarded by `VirtualMachine.can*` flags. The UI disables actions that are not valid in the current state. Concurrent operations on a single VM are prevented by the `OperationContext` lock (FR-013).

---

## Validation Rules

| Rule | Source |
|------|--------|
| Archive requires snapshot creation success before server deletion | FR-006 |
| Restore requires `latestSnapshot` to exist (`canRestore === true`) | FR-007 |
| Restore halt on step failure; no rollback; completed steps reported | FR-015 |
| Firewall upsert is idempotent — existing IP rule replaced, not duplicated | US5 scenario 3 |
| A `VmConfig` row must exist for a VM before Cloudflare DNS update is attempted | DB constraint |
| `app_configs` must contain `hetzner_default_server_type`, `hetzner_default_location`, `hetzner_default_ssh_key` before restore | FR-014 |
| `User.password_hash` must be a passlib bcrypt hash with cost ≥ 12; plain-text passwords are never stored | Auth security |
| JWT access token TTL is 24 h; expired tokens cause `get_current_user()` to raise `401`; `middleware.ts` redirects to `/login` | Auth contract |

---

## Database Models (SQLAlchemy)

**File**: `backend/app/models/db.py`

These models define the PostgreSQL schema. SQLAlchemy generates the DDL; Alembic tracks migrations. All Python backend code accesses the DB through an `AsyncSession` — see the async session dependency below.

```python
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    username      = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)       # passlib bcrypt, cost factor 12
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class VmConfig(Base):
    __tablename__ = "vm_configs"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    vm_name    = Column(String, unique=True, nullable=False)  # exact Hetzner VM name
    domain     = Column(String, nullable=False)               # full Cloudflare domain
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AppConfig(Base):
    __tablename__ = "app_configs"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    key        = Column(String, unique=True, nullable=False)
    value      = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class OperationLog(Base):
    __tablename__ = "operation_logs"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    vm_name      = Column(String, nullable=False)
    operation    = Column(String, nullable=False)   # 'start'|'stop'|'archive'|'restore'
    status       = Column(String, nullable=False)   # 'in-progress'|'done'|'error'
    steps_json   = Column(String, nullable=True)    # JSON-serialised OperationStep list
    started_at   = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
```

**`User` provisioning**: `backend/scripts/seed.py` creates the initial `admin` user using `ADMIN_PASSWORD` env var (seed-time only — not stored). Re-running is idempotent (`INSERT ... ON CONFLICT DO NOTHING`).

**`VmConfig` read path**: `backend/app/lib/cloudflare.py` queries `VmConfig` via `AsyncSession` to resolve `domain` before calling the Cloudflare DNS API.

**`AppConfig` known keys**:

| Key | Description | Example value |
|-----|-------------|---------------|
| `hetzner_firewall_name` | Hetzner shared firewall name | `my-shared-firewall` |
| `hetzner_default_server_type` | Server type for restore | `cx22` |
| `hetzner_default_location` | Data-centre location for restore | `nbg1` |
| `hetzner_default_ssh_key` | SSH key name/ID for restore | `my-ssh-key` |

**`AppConfig` seeding**: `seed.py` reads legacy env vars (if present) and inserts them as `AppConfig` rows. After seeding those env vars can be removed.

**`OperationLog` write path**: Each FastAPI route handler inserts a record at operation start (`status='in-progress'`) and updates it on completion or error.

---

## Pydantic API Schemas

Pydantic v2 schemas are separate from SQLAlchemy models. They define request validation and response serialisation for each FastAPI router.

### `backend/app/auth/schemas.py`

```python
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

### `backend/app/vms/schemas.py`

```python
from pydantic import BaseModel

class SnapshotOut(BaseModel):
    id: int
    description: str
    created_at: str
    vm_name: str

class VirtualMachineOut(BaseModel):
    name: str
    status: str          # 'running' | 'stopped' | 'archived'
    server_id: int | None = None
    public_ip: str | None = None
    latest_snapshot: SnapshotOut | None = None
    can_restore: bool
    can_archive: bool
    can_start: bool
    can_stop: bool

class OperationEventOut(BaseModel):
    kind: str            # 'step' | 'complete' | 'error'
    step: dict | None = None
    summary: str | None = None
    message: str | None = None
    completed_steps: list[str] | None = None
```

### `backend/app/config/schemas.py`

```python
from pydantic import BaseModel

class VmConfigOut(BaseModel):
    id: int
    vm_name: str
    domain: str
    created_at: str
    updated_at: str

class VmConfigCreate(BaseModel):
    vm_name: str
    domain: str

class VmConfigUpdate(BaseModel):
    domain: str

class AppConfigOut(BaseModel):
    hetzner_firewall_name: str
    hetzner_default_server_type: str
    hetzner_default_location: str
    hetzner_default_ssh_key: str

class AppConfigUpdate(BaseModel):
    hetzner_firewall_name: str | None = None
    hetzner_default_server_type: str | None = None
    hetzner_default_location: str | None = None
    hetzner_default_ssh_key: str | None = None
```

---

## SQLAlchemy Async Session Dependency

**File**: `backend/app/database.py`

```python
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
```

FastAPI routes receive a session via `Depends(get_db)`. A new session is opened per request and automatically closed (and rolled back on error) by the async context manager. All migrations are managed by Alembic (`alembic upgrade head`).
