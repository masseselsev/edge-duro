import os
import shutil
from typing import List
from models import Recipe, RecipeAsset


def prepare_workspace(recipe_id: int) -> str:
    """
    Creates isolated workspace directory structure for mkosi build.
    """
    base_dir = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
    recipe_ws = os.path.join(base_dir, str(recipe_id))

    subdirs = [
        "output",
        "assets",
        "gpg_keys",
        "mkosi.extra/etc/apt/sources.list.d",
        "mkosi.extra/etc/apt/trusted.gpg.d",
        "mkosi.extra/root/.ssh",
        "mkosi.extra/etc/network/interfaces.d",
        "mkosi.extra/opt/custom"
    ]

    for d in subdirs:
        os.makedirs(os.path.join(recipe_ws, d), exist_ok=True)

    return recipe_ws


def populate_extra_tree(recipe: Recipe, assets: List[RecipeAsset], workspace_path: str):
    """
    Populates mkosi.extra/ overlay tree with SSH keys, custom APT repositories, assets, and scripts.
    """
    extra_dir = os.path.join(workspace_path, "mkosi.extra")

    # 1. SSH Keys
    if recipe.ssh_keys:
        ssh_dir = os.path.join(extra_dir, "root", ".ssh")
        os.makedirs(ssh_dir, exist_ok=True)
        auth_keys_path = os.path.join(ssh_dir, "authorized_keys")
        with open(auth_keys_path, "w") as f:
            f.write("\n".join(recipe.ssh_keys) + "\n")

    # 2. Custom APT Repositories
    if recipe.repositories:
        sources_dir = os.path.join(extra_dir, "etc", "apt", "sources.list.d")
        os.makedirs(sources_dir, exist_ok=True)
        for repo in recipe.repositories:
            if isinstance(repo, dict):
                r_name = repo.get("name", "custom")
                r_url = repo.get("url", "")
                r_suite = repo.get("suite", "")
                r_comp = repo.get("components", "main")
                if r_url and r_suite:
                    list_file = os.path.join(sources_dir, f"{r_name}.list")
                    with open(list_file, "w") as f:
                        f.write(f"deb {r_url} {r_suite} {r_comp}\n")

    # 3. Assets overlay
    for asset in assets:
        if os.path.exists(asset.file_path):
            if asset.install_target:
                target_rel = asset.install_target.lstrip("/")
                dest_file = os.path.join(extra_dir, target_rel)
            else:
                dest_file = os.path.join(extra_dir, "opt", "custom", asset.filename)

            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            shutil.copy2(asset.file_path, dest_file)

    # 4. Post-install script hook
    if recipe.raw_postinst:
        postinst_path = os.path.join(workspace_path, "mkosi.postinst.chroot")
        with open(postinst_path, "w") as f:
            f.write("#!/bin/bash\nset -e\n" + recipe.raw_postinst + "\n")
        os.chmod(postinst_path, 0o755)


def cleanup_workspace(recipe_id: int):
    """
    Removes workspace directory for a deleted recipe.
    """
    base_dir = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
    recipe_ws = os.path.join(base_dir, str(recipe_id))
    if os.path.exists(recipe_ws):
        shutil.rmtree(recipe_ws, ignore_errors=True)
