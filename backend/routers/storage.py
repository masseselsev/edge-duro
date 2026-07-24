import os
import shutil
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, log_user_action
import models
from routers.users import require_admin

router = APIRouter(prefix="/api/storage", dependencies=[Depends(require_admin)])


def get_outputs_dir() -> str:
    ws_base = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
    outputs_dir = os.path.join(ws_base, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    return outputs_dir


class ArtifactInfo(BaseModel):
    filename: str
    filepath: str
    size_bytes: int
    size_human: str
    format: str  # raw_xz, iso, raw, other
    modified_at: str


class StorageSummaryResponse(BaseModel):
    outputs_dir: str
    total_files: int
    total_bytes: int
    total_human: str
    free_bytes: int
    free_human: str


class BulkDeleteRequest(BaseModel):
    filenames: List[str]


def format_bytes(size: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


@router.get("/summary", response_model=StorageSummaryResponse)
def get_storage_summary():
    outputs_dir = get_outputs_dir()
    total_files = 0
    total_bytes = 0

    if os.path.exists(outputs_dir):
        for entry in os.scandir(outputs_dir):
            if entry.is_file():
                total_files += 1
                total_bytes += entry.stat().st_size

    total_stat = shutil.disk_usage(outputs_dir)

    return StorageSummaryResponse(
        outputs_dir=outputs_dir,
        total_files=total_files,
        total_bytes=total_bytes,
        total_human=format_bytes(total_bytes),
        free_bytes=total_stat.free,
        free_human=format_bytes(total_stat.free)
    )


@router.get("/artifacts", response_model=List[ArtifactInfo])
def list_artifacts():
    outputs_dir = get_outputs_dir()
    items = []

    if os.path.exists(outputs_dir):
        for entry in os.scandir(outputs_dir):
            if entry.is_file():
                stat = entry.stat()
                fn = entry.name
                if fn.endswith(".raw.xz"):
                    fmt = "raw_xz"
                elif fn.endswith(".iso"):
                    fmt = "iso"
                elif fn.endswith(".raw"):
                    fmt = "raw"
                else:
                    fmt = "other"

                items.append(ArtifactInfo(
                    filename=fn,
                    filepath=entry.path,
                    size_bytes=stat.st_size,
                    size_human=format_bytes(stat.st_size),
                    format=fmt,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                ))

    items.sort(key=lambda x: x.modified_at, reverse=True)
    return items


@router.get("/artifacts/{filename}/download")
def download_artifact(filename: str):
    outputs_dir = get_outputs_dir()
    file_path = os.path.abspath(os.path.join(outputs_dir, filename))

    if not file_path.startswith(os.path.abspath(outputs_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename path.")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found in storage.")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.delete("/artifacts/{filename}")
def delete_single_artifact(
    filename: str,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    outputs_dir = get_outputs_dir()
    file_path = os.path.abspath(os.path.join(outputs_dir, filename))

    if not file_path.startswith(os.path.abspath(outputs_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename path.")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found in storage.")

    try:
        os.remove(file_path)
        log_user_action(db, current_user.username, "DELETE_STORAGE_ARTIFACT", f"Deleted storage artifact '{filename}'", request)
        return {"status": "success", "message": f"Artifact '{filename}' deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete artifact: {e}")


@router.post("/artifacts/bulk-delete")
def delete_bulk_artifacts(
    body: BulkDeleteRequest,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    outputs_dir = get_outputs_dir()
    deleted = []
    failed = []

    for fn in body.filenames:
        file_path = os.path.abspath(os.path.join(outputs_dir, fn))
        if file_path.startswith(os.path.abspath(outputs_dir)) and os.path.exists(file_path):
            try:
                os.remove(file_path)
                deleted.append(fn)
            except Exception as e:
                failed.append({"filename": fn, "error": str(e)})

    log_user_action(db, current_user.username, "BULK_DELETE_STORAGE_ARTIFACTS", f"Deleted {len(deleted)} storage artifacts", request)
    return {"status": "success", "deleted": deleted, "failed": failed}
