from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


class UTCModel(BaseModel):
    """Base model: serializes naive datetime as UTC ('Z' suffix), supports ORM mode."""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: (
                v.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
                if v.tzinfo is None
                else v.isoformat().replace('+00:00', 'Z')
            )
        }
    )


class SettingsBase(BaseModel):
    server_name: str = Field(default='Edge-D.U.R.O.')
    timezone: str = Field(default='Browser Local')
    language: str = Field(default='en')
    duro_workspace_path: str = Field(default='/opt/data/duro_workspace')
    log_retention_days: int = Field(default=3, ge=1, le=365)

    @field_validator('server_name')
    @classmethod
    def validate_server_name(cls, v: str) -> str:
        import re
        if not re.match(r'^[a-zA-Z0-9_\-\. ]+$', v):
            raise ValueError("Server name must contain only letters, numbers, hyphens, dots, and underscores.")
        return v


class SettingsResponse(UTCModel, SettingsBase):
    id: int


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    telegram_id: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    comment: Optional[str] = None
    is_admin_plus: Optional[bool] = False


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    telegram_id: Optional[str] = None
    password: Optional[str] = None
    comment: Optional[str] = None
    is_admin_plus: Optional[bool] = None


class UserSelfUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    telegram_id: Optional[str] = None
    password: Optional[str] = None


class UserResponse(UTCModel, UserBase):
    id: int
    is_superadmin: bool
    is_admin_plus: bool
    comment: Optional[str] = None


class LoginPayload(BaseModel):
    username: str
    password: str


class AptRepositorySchema(BaseModel):
    name: Optional[str] = "custom-repo"
    url: Optional[str] = ""
    suite: Optional[str] = ""
    components: Optional[str] = "main"
    gpg_key_filename: Optional[str] = None


class PartitionSchema(BaseModel):
    mountpoint: str = Field(default="/")
    size: str = Field(default="2G")
    filesystem: str = Field(default="ext4")
    type: str = Field(default="root")
    label: Optional[str] = None


class UserAccountSchema(BaseModel):
    """Additional login account created in the image."""
    username: str = Field(..., min_length=1, max_length=32)
    password: Optional[str] = None
    groups: List[str] = Field(default_factory=list)
    shell: str = Field(default="/bin/bash")

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        import re
        v = v.strip()
        # Usernames are interpolated into useradd/chpasswd commands during the
        # build, so restrict them to the POSIX portable set rather than relying
        # on downstream quoting.
        if not re.fullmatch(r'[a-z_][a-z0-9_-]*', v):
            raise ValueError(
                "Username must start with a lowercase letter or underscore and "
                "contain only lowercase letters, digits, underscore or hyphen"
            )
        return v

    @field_validator('groups')
    @classmethod
    def validate_groups(cls, v: List[str]) -> List[str]:
        import re
        cleaned = []
        for g in v:
            g = (g or "").strip()
            if not g:
                continue
            if not re.fullmatch(r'[a-z_][a-z0-9_-]*', g):
                raise ValueError(f"Invalid group name: {g}")
            cleaned.append(g)
        return cleaned

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        return _validate_password_value(v)


def _validate_password_value(v: Optional[str]) -> Optional[str]:
    # Newlines and colons would corrupt the "user:password" chpasswd stream.
    if v and ('\n' in v or '\r' in v or ':' in v):
        raise ValueError("Password must not contain newlines or ':'")
    return v


class RecipeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    distribution: str = Field(default="debian")
    release: str = Field(default="bookworm")
    architecture: str = Field(default="amd64")
    output_formats: List[str] = Field(default_factory=lambda: ["raw_xz"])
    packages: List[str] = Field(default_factory=list)
    repositories: List[AptRepositorySchema] = Field(default_factory=list)
    hostname: str = Field(default="edge-node")
    hostname_from_netif: bool = Field(default=False)
    timezone: str = Field(default="UTC")
    locale: str = Field(default="C.UTF-8")
    network_config: Optional[Dict[str, Any]] = None
    ssh_keys: List[str] = Field(default_factory=list)
    ssh_port: int = Field(default=2222, ge=1, le=65535)
    root_password: Optional[str] = None
    users: List[UserAccountSchema] = Field(default_factory=list)
    is_dev: bool = Field(default=False)
    kernel_params: Optional[str] = "ipv6.disable=1 nohz=off"
    partitions: List[PartitionSchema] = Field(default_factory=lambda: [
        {"mountpoint": "/boot", "size": "512M", "filesystem": "vfat", "type": "esp", "label": "edgeboot"},
        {"mountpoint": "/", "size": "8G", "filesystem": "ext4", "type": "root", "label": "edgeroot"},
        {"mountpoint": "/var/log/edge", "size": "1G", "filesystem": "ext4", "type": "generic", "label": "edgelog"},
        {"mountpoint": "/var/opt/edge", "size": "max", "filesystem": "ext4", "type": "generic", "label": "edgestor"},
    ])
    raw_mkosi_conf: Optional[str] = None
    raw_preseed_cfg: Optional[str] = None
    raw_postinst: Optional[str] = None
    raw_firstboot: Optional[str] = None

    @field_validator('root_password')
    @classmethod
    def validate_root_password(cls, v: Optional[str]) -> Optional[str]:
        return _validate_password_value(v)


class RecipeCreate(RecipeBase):
    pass


class RecipeUpdate(RecipeBase):
    pass


class RecipeAssetResponse(UTCModel):
    id: int
    recipe_id: int
    filename: str
    file_type: str
    file_size: int
    file_path: str
    install_target: Optional[str] = None
    is_postinst: bool
    uploaded_at: datetime


class RecipeResponse(UTCModel, RecipeBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_build_at: Optional[datetime] = None
    last_build_status: Optional[str] = None
    assets: Optional[List[RecipeAssetResponse]] = None


class BuildResponse(UTCModel):
    id: str
    recipe_id: int
    status: str
    triggered_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    log_output: Optional[str] = None
    artifact_path: Optional[str] = None
    artifact_size: Optional[int] = None
    iso_artifact_path: Optional[str] = None
    iso_artifact_size: Optional[int] = None
    output_format: Optional[str] = None
    duration_seconds: Optional[int] = None
    recipe: Optional[RecipeResponse] = None


class PaginatedBuildsResponse(BaseModel):
    items: List[BuildResponse]
    total: int
    page: int
    limit: int
    pages: int


class SystemLogResponse(UTCModel):
    id: int
    level: str
    message: str
    created_at: datetime


class PaginatedSystemLogsResponse(BaseModel):
    items: List[SystemLogResponse]
    total: int
    page: int
    limit: int
    pages: int


class AuditLogResponse(UTCModel):
    id: int
    username: str
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime


class PaginatedAuditLogsResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    limit: int
    pages: int
