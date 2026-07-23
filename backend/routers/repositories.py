import os
import shutil
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session

from database import get_db, log_user_action
import models
import schemas
from routers.users import require_admin

router = APIRouter(prefix="/api/recipes", dependencies=[Depends(require_admin)])


@router.get("/{recipe_id}/repositories", response_model=List[schemas.AptRepositorySchema])
def get_recipe_repositories(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    return recipe.repositories or []


@router.put("/{recipe_id}/repositories", response_model=List[schemas.AptRepositorySchema])
def update_recipe_repositories(
    recipe_id: int,
    payload: List[schemas.AptRepositorySchema],
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    recipe.repositories = [r.model_dump() for r in payload]
    db.commit()
    db.refresh(recipe)

    log_user_action(db, current_user.username, "UPDATE_REPOSITORIES", f"Updated APT repositories for recipe ID {recipe_id}", request)
    return recipe.repositories or []


@router.post("/{recipe_id}/repositories/gpg")
async def upload_gpg_key(
    recipe_id: int,
    file: UploadFile = File(...),
    request: Request = None,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    filename = os.path.basename(file.filename)
    if not (filename.endswith(".asc") or filename.endswith(".gpg")):
        raise HTTPException(status_code=400, detail="GPG key file must have .asc or .gpg extension.")

    workspace_base = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
    gpg_dir = os.path.join(workspace_base, str(recipe_id), "gpg_keys")
    os.makedirs(gpg_dir, exist_ok=True)

    dest_path = os.path.join(gpg_dir, filename)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    log_user_action(db, current_user.username, "UPLOAD_GPG_KEY", f"Uploaded GPG key '{filename}' for recipe ID {recipe_id}", request)
    return {"filename": filename, "path": dest_path}
