from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project_permissions: Mapped[list["UserProjectPermission"]] = relationship(
        "UserProjectPermission", back_populates="user", cascade="all, delete-orphan"
    )


class HetznerProject(Base):
    __tablename__ = "hetzner_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    api_token: Mapped[str] = mapped_column(String, nullable=False)
    firewall_name: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    firewall_internal: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    cloudflare_zone_id: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user_permissions: Mapped[list["UserProjectPermission"]] = relationship(
        "UserProjectPermission", back_populates="project", cascade="all, delete-orphan"
    )


class UserProjectPermission(Base):
    __tablename__ = "user_project_permissions"
    __table_args__ = (UniqueConstraint("user_id", "project_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hetzner_projects.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="project_permissions")
    project: Mapped["HetznerProject"] = relationship(
        "HetznerProject", back_populates="user_permissions"
    )


class VmConfig(Base):
    __tablename__ = "vm_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preferred_server_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AppConfig(Base):
    __tablename__ = "app_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VmArchivedState(Base):
    """Snapshot of a VM's live configuration captured at archive time."""
    __tablename__ = "vm_archived_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    server_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    server_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    public_ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    firewalls_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    networks_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    enable_ipv4: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    enable_ipv6: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_name: Mapped[str] = mapped_column(String, nullable=False)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    initiated_by: Mapped[str] = mapped_column(String, nullable=False, server_default="system")
    steps_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
