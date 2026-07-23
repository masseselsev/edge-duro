from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db, log_user_action
import models
import schemas
from routers.users import require_admin

router = APIRouter(prefix="/api/settings", dependencies=[Depends(require_admin)])


@router.get("", response_model=schemas.SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    settings = db.query(models.Settings).first()
    if not settings:
        settings = models.Settings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.post("", response_model=schemas.SettingsResponse)
def update_settings(
    payload: schemas.SettingsBase,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    settings = db.query(models.Settings).first()
    if not settings:
        settings = models.Settings()
        db.add(settings)

    settings.server_name = payload.server_name
    settings.timezone = payload.timezone
    if payload.language:
        settings.language = payload.language
    if payload.duro_workspace_path:
        settings.duro_workspace_path = payload.duro_workspace_path

    db.commit()
    db.refresh(settings)
    log_user_action(db, current_user.username, "UPDATE_SETTINGS", "Updated global settings", request)
    return settings
