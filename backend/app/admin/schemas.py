from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    username: str
    is_superadmin: bool
    is_active: bool
    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str
    password: str
    is_superadmin: bool = False


class UserUpdate(BaseModel):
    password: str | None = None
    is_superadmin: bool | None = None
    is_active: bool | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    firewall_name: str
    firewall_internal: str
    cloudflare_zone_id: str
    cloudflare_api_token: str
    is_active: bool
    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str
    api_token: str
    firewall_name: str = ""
    firewall_internal: str = ""
    cloudflare_zone_id: str = ""
    cloudflare_api_token: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    api_token: str | None = None
    firewall_name: str | None = None
    firewall_internal: str | None = None
    cloudflare_zone_id: str | None = None
    cloudflare_api_token: str | None = None
    is_active: bool | None = None


class PermissionOut(BaseModel):
    user_id: int
    project_id: int
    username: str
    model_config = {"from_attributes": True}
