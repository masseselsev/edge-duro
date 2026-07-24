from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func
from database import Base

class Settings(Base):
    """
    Settings model for global Edge D.U.R.O. orchestrator configuration.
    """
    __tablename__ = 'settings'

    id = Column(Integer, primary_key=True, index=True)
    server_name = Column(String, default="Edge-D.U.R.O.", nullable=False)
    timezone = Column(String, default='Browser Local', nullable=False)
    language = Column(String, default='en', nullable=False)
    duro_workspace_path = Column(String, default='/opt/data/duro_workspace', nullable=False)


class User(Base):
    """
    Model for administrator and superadmin user accounts.
    """
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    telegram_id = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    is_superadmin = Column(Boolean, default=False, nullable=False)
    is_admin_plus = Column(Boolean, default=False, nullable=False)


class Recipe(Base):
    """
    Recipe model defining OS image build configurations for mkosi.
    """
    __tablename__ = 'recipes'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)

    distribution = Column(String, nullable=False, default="debian") # debian, ubuntu
    release = Column(String, nullable=False, default="bookworm")    # bookworm, trixie, jammy, noble
    architecture = Column(String, nullable=False, default="amd64")   # amd64, arm64

    output_formats = Column(JSON, nullable=False, default=lambda: ["raw_xz"]) # raw_xz, iso
    packages = Column(JSON, nullable=False, default=list) # ["nginx", "curl"]
    repositories = Column(JSON, nullable=False, default=list)
    # list of dicts: [{"name": "...", "url": "...", "suite": "...", "components": "...", "gpg_key_filename": "..."}]

    hostname = Column(String, default="edge-node", nullable=False)
    timezone = Column(String, default="UTC", nullable=False)
    network_config = Column(JSON, nullable=True)
    ssh_keys = Column(JSON, nullable=False, default=list)

    kernel_params = Column(String, nullable=True)
    raw_mkosi_conf = Column(Text, nullable=True)
    raw_preseed_cfg = Column(Text, nullable=True)
    raw_postinst = Column(Text, nullable=True)
    raw_firstboot = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    last_build_at = Column(DateTime, nullable=True)
    last_build_status = Column(String, nullable=True)


class Build(Base):
    """
    Build execution record and output tracking.
    """
    __tablename__ = 'builds'

    id = Column(String, primary_key=True, index=True) # UUID string
    recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    status = Column(String, default='PENDING', nullable=False) # PENDING, RUNNING, SUCCESS, FAILED, CANCELLED
    triggered_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    log_output = Column(Text, default='', nullable=False)
    artifact_path = Column(String, nullable=True)
    artifact_size = Column(BigInteger, nullable=True)
    output_format = Column(String, nullable=True) # raw_xz, iso
    duration_seconds = Column(Integer, nullable=True)


class RecipeAsset(Base):
    """
    Uploaded file assets (.deb, scripts, binaries) bound to a Recipe.
    """
    __tablename__ = 'recipe_assets'

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False) # deb, binary, script
    file_size = Column(BigInteger, nullable=False)
    file_path = Column(String, nullable=False)
    install_target = Column(String, nullable=True)
    is_postinst = Column(Boolean, default=False, nullable=False)
    uploaded_at = Column(DateTime, default=func.now(), nullable=False)


class SystemLog(Base):
    """
    General application logs model.
    """
    __tablename__ = 'system_logs'

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)


class AuditLog(Base):
    """
    Audit log for user actions.
    """
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
