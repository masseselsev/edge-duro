import os
import uuid
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from database import get_db, log_user_action
import models
import schemas
from routers.users import require_admin
from celery_app import REDIS_URL
import redis.asyncio as aioredis

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


@router.post("/recipes/{recipe_id}/build")
def trigger_build(
    recipe_id: int,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    build_id = str(uuid.uuid4())
    build = models.Build(
        id=build_id,
        recipe_id=recipe.id,
        status="PENDING",
        triggered_by=current_user.username,
        log_output=f"[SYSTEM] Build initialized for recipe '{recipe.name}'\n"
    )
    db.add(build)

    recipe.last_build_at = build.created_at
    recipe.last_build_status = "PENDING"

    db.commit()

    # Dispatch Celery task
    try:
        from tasks.build_image import build_image_task
        build_image_task.delay(build_id, recipe.id)
    except Exception as e:
        build.status = "FAILED"
        build.log_output += f"[ERROR] Failed to dispatch Celery worker task: {e}\n"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to dispatch build task: {e}")

    log_user_action(db, current_user.username, "TRIGGER_BUILD", f"Triggered build '{build_id}' for recipe '{recipe.name}'", request)
    return {"build_id": build_id, "status": "PENDING", "message": "Build task dispatched successfully."}


@router.get("/builds", response_model=schemas.PaginatedBuildsResponse)
def list_builds(
    recipe_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(models.Build)
    if recipe_id is not None:
        query = query.filter(models.Build.recipe_id == recipe_id)
    if status:
        query = query.filter(models.Build.status == status)

    total = query.count()
    items = query.order_by(models.Build.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    pages = (total + limit - 1) // limit if total > 0 else 1

    return schemas.PaginatedBuildsResponse(
        items=[schemas.BuildResponse.model_validate(b) for b in items],
        total=total,
        page=page,
        limit=limit,
        pages=pages
    )


@router.get("/builds/{build_id}", response_model=schemas.BuildResponse)
def get_build(build_id: str, db: Session = Depends(get_db)):
    build = db.query(models.Build).filter(models.Build.id == build_id).first()
    if not build:
        raise HTTPException(status_code=404, detail="Build record not found.")
    return schemas.BuildResponse.model_validate(build)


@router.get("/builds/{build_id}/stream")
async def stream_build_logs(build_id: str, request: Request):
    """
    SSE Endpoint streaming live build logs from Redis PubSub channel.
    Includes 5-second keepalive pings to keep TCP stream active across proxies.
    """
    async def event_generator():
        r = aioredis.from_url(REDIS_URL)
        pubsub = r.pubsub()
        channel_name = f"build:{build_id}"
        await pubsub.subscribe(channel_name)

        idle_ticks = 0
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    idle_ticks = 0
                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield {"event": "log", "data": str(data)}
                else:
                    idle_ticks += 1
                    if idle_ticks >= 5:
                        idle_ticks = 0
                        yield {"event": "ping", "data": "keepalive"}
                await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(channel_name)
            await r.close()

    return EventSourceResponse(event_generator())


@router.post("/builds/{build_id}/cancel")
def cancel_build(
    build_id: str,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    build = db.query(models.Build).filter(models.Build.id == build_id).first()
    if not build:
        raise HTTPException(status_code=404, detail="Build record not found.")

    if build.status not in ("PENDING", "RUNNING"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel build in status '{build.status}'.")

    build.status = "CANCELLED"
    build.log_output += "\n[SYSTEM] Build cancellation requested by administrator.\n"
    db.commit()

    log_user_action(db, current_user.username, "CANCEL_BUILD", f"Cancelled build '{build_id}'", request)
    return {"status": "success", "message": "Build marked as CANCELLED."}


@router.get("/builds/{build_id}/download")
def download_build_artifact(
    build_id: str,
    format: Optional[str] = Query("raw_xz"),
    db: Session = Depends(get_db)
):
    build = db.query(models.Build).filter(models.Build.id == build_id).first()
    if not build:
        raise HTTPException(status_code=404, detail="Build record not found.")

    target_path = None
    if format == "iso":
        target_path = build.iso_artifact_path
        if not target_path and build.artifact_path:
            possible_iso = build.artifact_path.replace(".raw.xz", ".iso").replace(".raw", ".iso")
            if os.path.exists(possible_iso):
                target_path = possible_iso
    else:
        target_path = build.artifact_path

    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail=f"Artifact format '{format}' file does not exist on server storage.")

    filename = os.path.basename(target_path)
    return FileResponse(
        path=target_path,
        filename=filename,
        media_type="application/octet-stream"
    )
