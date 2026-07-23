from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db, log_user_action
import models
import schemas
from routers.users import require_admin

router = APIRouter(prefix="/api/recipes", dependencies=[Depends(require_admin)])


@router.get("", response_model=List[schemas.RecipeResponse])
def list_recipes(db: Session = Depends(get_db)):
    recipes = db.query(models.Recipe).all()
    result = []
    for r in recipes:
        resp = schemas.RecipeResponse.model_validate(r)
        assets = db.query(models.RecipeAsset).filter(models.RecipeAsset.recipe_id == r.id).all()
        resp.assets = [schemas.RecipeAssetResponse.model_validate(a) for a in assets]
        result.append(resp)
    return result


@router.post("", response_model=schemas.RecipeResponse)
def create_recipe(
    payload: schemas.RecipeCreate,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    existing = db.query(models.Recipe).filter(models.Recipe.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Recipe with name '{payload.name}' already exists.")

    recipe_data = payload.model_dump()
    if "repositories" in recipe_data:
        recipe_data["repositories"] = [r if isinstance(r, dict) else r.dict() for r in payload.repositories]

    recipe = models.Recipe(**recipe_data)
    db.add(recipe)
    db.commit()
    db.refresh(recipe)

    log_user_action(db, current_user.username, "CREATE_RECIPE", f"Created recipe '{recipe.name}' (ID: {recipe.id})", request)
    resp = schemas.RecipeResponse.model_validate(recipe)
    resp.assets = []
    return resp


@router.get("/{recipe_id}", response_model=schemas.RecipeResponse)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    resp = schemas.RecipeResponse.model_validate(recipe)
    assets = db.query(models.RecipeAsset).filter(models.RecipeAsset.recipe_id == recipe.id).all()
    resp.assets = [schemas.RecipeAssetResponse.model_validate(a) for a in assets]
    return resp


@router.put("/{recipe_id}", response_model=schemas.RecipeResponse)
def update_recipe(
    recipe_id: int,
    payload: schemas.RecipeUpdate,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    name_check = db.query(models.Recipe).filter(models.Recipe.name == payload.name, models.Recipe.id != recipe_id).first()
    if name_check:
        raise HTTPException(status_code=400, detail=f"Recipe name '{payload.name}' is already used by another recipe.")

    update_data = payload.model_dump()
    for key, value in update_data.items():
        if key == "repositories":
            setattr(recipe, key, [r if isinstance(r, dict) else r.dict() for r in payload.repositories])
        else:
            setattr(recipe, key, value)

    db.commit()
    db.refresh(recipe)

    log_user_action(db, current_user.username, "UPDATE_RECIPE", f"Updated recipe '{recipe.name}' (ID: {recipe_id})", request)
    resp = schemas.RecipeResponse.model_validate(recipe)
    assets = db.query(models.RecipeAsset).filter(models.RecipeAsset.recipe_id == recipe.id).all()
    resp.assets = [schemas.RecipeAssetResponse.model_validate(a) for a in assets]
    return resp


@router.delete("/{recipe_id}")
def delete_recipe(
    recipe_id: int,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    name = recipe.name
    # Delete workspace directory if exists
    import shutil, os
    workspace_path = os.path.join(os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace"), str(recipe_id))
    if os.path.exists(workspace_path):
        try:
            shutil.rmtree(workspace_path)
        except Exception as e:
            print(f"Failed to delete workspace directory: {e}")

    db.delete(recipe)
    db.commit()

    log_user_action(db, current_user.username, "DELETE_RECIPE", f"Deleted recipe '{name}' (ID: {recipe_id})", request)
    return {"status": "success", "message": f"Recipe '{name}' deleted successfully."}


@router.post("/{recipe_id}/clone", response_model=schemas.RecipeResponse)
def clone_recipe(
    recipe_id: int,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    original = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    new_name = f"Copy of {original.name}"
    counter = 1
    while db.query(models.Recipe).filter(models.Recipe.name == new_name).first():
        counter += 1
        new_name = f"Copy ({counter}) of {original.name}"

    cloned = models.Recipe(
        name=new_name,
        description=f"Cloned from {original.name}. {original.description or ''}".strip(),
        distribution=original.distribution,
        release=original.release,
        architecture=original.architecture,
        output_formats=original.output_formats,
        packages=original.packages,
        repositories=original.repositories,
        hostname=original.hostname,
        network_config=original.network_config,
        ssh_keys=original.ssh_keys,
        raw_mkosi_conf=original.raw_mkosi_conf,
        raw_preseed_cfg=original.raw_preseed_cfg,
        raw_postinst=original.raw_postinst
    )

    db.add(cloned)
    db.commit()
    db.refresh(cloned)

    log_user_action(db, current_user.username, "CLONE_RECIPE", f"Cloned recipe ID {recipe_id} to '{new_name}' (ID: {cloned.id})", request)
    resp = schemas.RecipeResponse.model_validate(cloned)
    resp.assets = []
    return resp
