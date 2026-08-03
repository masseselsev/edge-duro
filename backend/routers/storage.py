import os
import shutil
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, defer

from database import get_db, log_user_action
import models
from routers.users import require_admin

router = APIRouter(prefix="/api/storage", dependencies=[Depends(require_admin)])


def get_outputs_dir() -> str:
    ws_base = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
    outputs_dir = os.path.join(ws_base, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    return outputs_dir


import schemas
from typing import Optional

class ArtifactInfo(BaseModel):
    filename: str
    filepath: str
    size_bytes: int
    size_human: str
    format: str  # raw_xz, iso, raw, other
    modified_at: str
    recipe: Optional[schemas.RecipeResponse] = None
    build_id: Optional[str] = None


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

    total, used, free = shutil.disk_usage(outputs_dir)

    return StorageSummaryResponse(
        outputs_dir=outputs_dir,
        total_files=total_files,
        total_bytes=total_bytes,
        total_human=format_bytes(total_bytes),
        free_bytes=free,
        free_human=format_bytes(free)
    )


class PaginatedArtifactsResponse(BaseModel):
    items: List[ArtifactInfo]
    total: int
    page: int
    limit: int
    pages: int


@router.get("/artifacts", response_model=PaginatedArtifactsResponse)
def list_artifacts(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    outputs_dir = get_outputs_dir()
    items = []

    # Map build artifact paths & log filenames to builds for fast recipe lookup
    builds = db.query(models.Build).options(defer(models.Build.log_output)).all()
    build_map = {}
    for b in builds:
        if b.artifact_path:
            build_map[os.path.basename(b.artifact_path)] = b
        if b.iso_artifact_path:
            build_map[os.path.basename(b.iso_artifact_path)] = b

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

                matched_build = build_map.get(fn)
                recipe_schema = None
                b_id = None
                if matched_build:
                    b_id = matched_build.id
                    if matched_build.recipe:
                        recipe_schema = schemas.RecipeResponse.model_validate(matched_build.recipe)

                items.append(ArtifactInfo(
                    filename=fn,
                    filepath=entry.path,
                    size_bytes=stat.st_size,
                    size_human=format_bytes(stat.st_size),
                    format=fmt,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                    recipe=recipe_schema,
                    build_id=b_id
                ))

    items.sort(key=lambda x: x.modified_at, reverse=True)
    total = len(items)
    start = (page - 1) * limit
    end = start + limit
    paginated_items = items[start:end]
    pages = (total + limit - 1) // limit if total > 0 else 1

    return PaginatedArtifactsResponse(
        items=paginated_items,
        total=total,
        page=page,
        limit=limit,
        pages=pages
    )


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
        raise HTTPException(status_code=500, detail=f"Failed to delete artifact: {e}") from e


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
