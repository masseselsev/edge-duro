import os
import shutil
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session

from database import get_db, log_user_action
import models
import schemas
from core import repo_browser
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


@router.get("/{recipe_id}/repositories/browse")
def browse_repository(
    recipe_id: int,
    repo: int = 0,
    q: str = "",
    section: str = "",
    limit: int = 200,
    offset: int = 0,
    refresh: bool = False,
    db: Session = Depends(get_db),
):
    """
    Lists packages available in one of the recipe's configured repositories.

    Filtering happens server-side because a full Debian component carries tens
    of thousands of packages, which is far too many to ship to the browser.
    The parsed index is cached in-process so typing in the picker does not
    re-download it.
    """
    recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    repos = [r for r in (recipe.repositories or []) if isinstance(r, dict) and r.get("url")]
    if not repos:
        raise HTTPException(status_code=400, detail="This recipe has no APT repositories configured.")
    if repo < 0 or repo >= len(repos):
        raise HTTPException(status_code=404, detail="Repository index out of range.")

    entry = repos[repo]
    suite = entry.get("suite") or recipe.release or "bookworm"
    # A repo may declare several components; browse the first unless asked.
    components = (entry.get("components") or "main").split()
    component = components[0]

    arch_map = {"amd64": "amd64", "x86_64": "amd64", "x86-64": "amd64", "arm64": "arm64", "aarch64": "arm64"}
    arch = arch_map.get((recipe.architecture or "amd64").lower(), "amd64")

    packages = repo_browser.get_packages(
        entry["url"], suite, component, arch, force_refresh=refresh
    )

    if packages is None:
        # Distinguished from an empty repository so the UI can say "unreachable"
        # rather than silently showing nothing.
        return {
            "reachable": False,
            "repo": {"name": entry.get("name"), "url": entry.get("url"), "suite": suite,
                     "component": component, "architecture": arch},
            "error": "Repository index could not be fetched from the backend.",
            "packages": [], "total": 0, "sections": [],
        }

    page, total = repo_browser.search(packages, query=q, section=section, limit=limit, offset=offset)

    return {
        "reachable": True,
        "repo": {"name": entry.get("name"), "url": entry.get("url"), "suite": suite,
                 "component": component, "architecture": arch},
        "packages": page,
        "total": total,
        "available": len(packages),
        "sections": repo_browser.sections(packages),
    }


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
