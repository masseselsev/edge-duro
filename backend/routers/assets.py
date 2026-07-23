import os
import shutil
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session

from database import get_db, log_user_action
import models
import schemas
from routers.users import require_admin

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])

ALLOWED_EXTENSIONS = {".deb", ".sh", ".bash", ".bin", ".tar.gz", ".py", ".asc", ".gpg"}


def sanitize_filename(filename: str) -> str:
    cleaned = os.path.basename(filename)
    cleaned = cleaned.replace("..", "").replace("/", "").replace("\\", "")
    return cleaned


@router.post("/recipes/{recipe_id}/assets", response_model=schemas.RecipeAssetResponse)
async def upload_asset(
    recipe_id: int,
    file: UploadFile = File(...),
    install_target: str = Form(default=""),
    is_postinst: bool = Form(default=False),
    request: Request = None,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    filename = sanitize_filename(file.filename)
    if not filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    ext = os.path.splitext(filename)[1].lower()
    if filename.endswith(".tar.gz"):
        ext = ".tar.gz"

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Extension '{ext}' not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    file_type = "deb" if ext == ".deb" else ("script" if ext in ('.sh', '.bash', '.py') else "binary")

    workspace_base = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
    asset_dir = os.path.join(workspace_base, str(recipe_id), "assets")
    os.makedirs(asset_dir, exist_ok=True)

    dest_path = os.path.join(asset_dir, filename)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = os.path.getsize(dest_path)

    # Save to database
    asset = models.RecipeAsset(
        recipe_id=recipe_id,
        filename=filename,
        file_type=file_type,
        file_size=file_size,
        file_path=dest_path,
        install_target=install_target or None,
        is_postinst=is_postinst
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    log_user_action(db, current_user.username, "UPLOAD_ASSET", f"Uploaded asset '{filename}' for recipe ID {recipe_id}", request)
    return schemas.RecipeAssetResponse.model_validate(asset)


@router.get("/recipes/{recipe_id}/assets", response_model=List[schemas.RecipeAssetResponse])
def list_recipe_assets(recipe_id: int, db: Session = Depends(get_db)):
    assets = db.query(models.RecipeAsset).filter(models.RecipeAsset.recipe_id == recipe_id).all()
    return [schemas.RecipeAssetResponse.model_validate(a) for a in assets]


@router.delete("/assets/{asset_id}")
def delete_asset(
    asset_id: int,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    asset = db.query(models.RecipeAsset).filter(models.RecipeAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset file record not found.")

    filename = asset.filename
    if os.path.exists(asset.file_path):
        try:
            os.remove(asset.file_path)
        except Exception as e:
            print(f"Error removing asset file from disk: {e}")

    db.delete(asset)
    db.commit()

    log_user_action(db, current_user.username, "DELETE_ASSET", f"Deleted asset '{filename}' (ID: {asset_id})", request)
    return {"status": "success", "message": f"Asset '{filename}' deleted successfully."}
