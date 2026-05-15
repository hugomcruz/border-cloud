from pydantic import BaseModel


class SnapshotOut(BaseModel):
    id: int
    description: str
    created_at: str
    vm_name: str
    server_type: str | None = None
    location: str | None = None


class VirtualMachineOut(BaseModel):
    name: str
    status: str  # 'running' | 'stopped' | 'archived'
    server_id: int | None = None
    public_ip: str | None = None
    server_type: str | None = None
    location: str | None = None
    domain: str | None = None
    protected: bool = False
    latest_snapshot: SnapshotOut | None = None
    can_restore: bool
    can_archive: bool
    can_start: bool
    can_stop: bool
    can_delete_image: bool = False


class OperationEventOut(BaseModel):
    kind: str  # 'step' | 'complete' | 'error'
    step: dict | None = None
    summary: str | None = None
    message: str | None = None
    completed_steps: list[str] | None = None
