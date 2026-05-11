"""Pydantic schemas for config routes — VmConfig and AppConfig."""

from pydantic import BaseModel


class VmConfigOut(BaseModel):
    id: int
    vm_name: str
    domain: str | None = None
    preferred_server_type: str | None = None

    model_config = {"from_attributes": True}


class VmConfigCreate(BaseModel):
    vm_name: str
    domain: str | None = None
    preferred_server_type: str | None = None


class VmConfigUpdate(BaseModel):
    domain: str | None = None
    preferred_server_type: str | None = None


class AppConfigOut(BaseModel):
    key: str
    value: str

    model_config = {"from_attributes": True}


class AppConfigUpdate(BaseModel):
    value: str


class VmFirewallTargetOut(BaseModel):
    id: int
    vm_name: str
    project_id: int
    project_name: str
    firewall_name: str

    model_config = {"from_attributes": True}


class VmFirewallTargetCreate(BaseModel):
    project_id: int
    firewall_name: str
