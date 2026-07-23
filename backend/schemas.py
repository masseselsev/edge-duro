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
    name: str
    url: str
    suite: str
    components: str = "main"
    gpg_key_filename: Optional[str] = None


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
    network_config: Optional[Dict[str, Any]] = None
    ssh_keys: List[str] = Field(default_factory=list)
    raw_mkosi_conf: Optional[str] = None
    raw_preseed_cfg: Optional[str] = None
    raw_postinst: Optional[str] = None


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
    log_output: str
    artifact_path: Optional[str] = None
    artifact_size: Optional[int] = None
    output_format: Optional[str] = None
    duration_seconds: Optional[int] = None


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


class AuditLogResponse(UTCModel):
    id: int
    username: str
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
