import os
import logging
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from routers.users import require_admin

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)


@router.get("/health")
def get_system_health(db: Session = Depends(get_db)):
    warnings = []
    try:
        workspace_path = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
        if not os.path.exists(workspace_path):
            warnings.append({
                "code": "WORKSPACE_DIR_MISSING",
                "type": "WARNING",
                "message": f"D.U.R.O. workspace directory ({workspace_path}) does not exist yet."
            })
    except Exception as e:
        logger.error(f"System health check failed: {e}")

    return {"warnings": warnings}


@router.get("/system/metrics")
def get_system_metrics():
    cpu_usage = 0.0
    ram_usage = 0.0
    try:
        import psutil
        cpu_usage = psutil.cpu_percent(interval=None)
        ram_usage = psutil.virtual_memory().percent
    except Exception:
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                mem_total = 0
                mem_free = 0
                for line in lines:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_available = int(line.split()[1])
                if mem_total > 0:
                    ram_usage = round((1 - (mem_available / mem_total)) * 100, 1)
        except Exception:
            pass

    return {
        "cpu_usage": cpu_usage,
        "ram_usage": ram_usage,
        "rx_speed": 0,
        "tx_speed": 0,
        "rx_percent": 0.0,
        "tx_percent": 0.0,
    }


@router.get("/logs/system", response_model=List[schemas.SystemLogResponse])
def get_system_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    return db.query(models.SystemLog).order_by(models.SystemLog.created_at.desc()).limit(limit).all()


@router.get("/logs/audit", response_model=List[schemas.AuditLogResponse])
def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    return db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(limit).all()
