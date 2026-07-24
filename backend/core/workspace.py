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
    Populates mkosi.extra/ overlay tree with SSH keys, custom APT repositories, assets, postinst, firstboot, and preseed files.
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

    # 4. Post-install script hook & timezone setup
    postinst_commands = []
    if recipe.timezone and recipe.timezone.strip():
        tz = recipe.timezone.strip()
        postinst_commands.append(f"ln -sf /usr/share/zoneinfo/{tz} /etc/localtime && echo \"{tz}\" > /etc/timezone")

    if recipe.raw_postinst and recipe.raw_postinst.strip():
        postinst_commands.append(recipe.raw_postinst.strip())

    if postinst_commands:
        postinst_path = os.path.join(workspace_path, "mkosi.postinst.chroot")
        with open(postinst_path, "w") as f:
            f.write("#!/bin/bash\nset -e\n" + "\n".join(postinst_commands) + "\n")
        os.chmod(postinst_path, 0o755)

    # 5. Firstboot script & systemd service
    firstboot_lines = ["#!/bin/bash", "set -e"]

    if recipe.hostname_from_netif:
        base_hn = (recipe.hostname or "edge-node").lower().strip()
        firstboot_lines.append(f"""
# Auto-configure hostname based on active network interface MAC (strictly lowercase)
IFACE=$(ip -4 route show default 2>/dev/null | awk '/default/ {{print $5}}' | head -n 1)
if [ -z "$IFACE" ]; then
  IFACE=$(ip -o link show 2>/dev/null | awk -F': ' '$2 != "lo" {{print $2; exit}}')
fi
if [ -n "$IFACE" ]; then
  MAC=$(cat /sys/class/net/$IFACE/address 2>/dev/null | tr -d ':' | tr '[:upper:]' '[:lower:]' | tail -c 7)
  if [ -n "$MAC" ]; then
    BASE_PREFIX=$(echo "{base_hn}" | tr '[:upper:]' '[:lower:]')
    DYNAMIC_HN="${{BASE_PREFIX}}${{MAC}}"
    echo "Setting hostname to $DYNAMIC_HN (interface: $IFACE)"
    hostnamectl set-hostname "$DYNAMIC_HN" 2>/dev/null || echo "$DYNAMIC_HN" > /etc/hostname
    if [ -f /etc/hosts ]; then
      sed -i "s/127.0.1.1.*/127.0.1.1\t$DYNAMIC_HN/g" /etc/hosts 2>/dev/null || true
    fi
  fi
fi
""")

    if recipe.raw_firstboot and recipe.raw_firstboot.strip():
        firstboot_lines.append(recipe.raw_firstboot.strip())

    if len(firstboot_lines) > 2:
        fb_bin_dir = os.path.join(extra_dir, "opt", "edge", "bin")
        os.makedirs(fb_bin_dir, exist_ok=True)
        fb_script_path = os.path.join(fb_bin_dir, "firstboot.sh")
        with open(fb_script_path, "w") as f:
            f.write("\n".join(firstboot_lines) + "\n")
        os.chmod(fb_script_path, 0o755)

        systemd_dir = os.path.join(extra_dir, "etc", "systemd", "system")
        os.makedirs(systemd_dir, exist_ok=True)
        fb_svc_path = os.path.join(systemd_dir, "edge-firstboot.service")
        with open(fb_svc_path, "w") as f:
            f.write("""[Unit]
Description=Edge Firstboot Initialization Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/edge/bin/firstboot.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
""")

        wants_dir = os.path.join(extra_dir, "etc", "systemd", "system", "multi-user.target.wants")
        os.makedirs(wants_dir, exist_ok=True)
        link_path = os.path.join(wants_dir, "edge-firstboot.service")
        if not os.path.exists(link_path):
            try:
                os.symlink("/etc/systemd/system/edge-firstboot.service", link_path)
            except Exception:
                pass

    # 6. Debian Preseed file
    if recipe.raw_preseed_cfg and recipe.raw_preseed_cfg.strip():
        preseed_path = os.path.join(workspace_path, "preseed.cfg")
        with open(preseed_path, "w") as f:
            f.write(recipe.raw_preseed_cfg.strip() + "\n")


def cleanup_workspace(recipe_id: int):
    """
    Removes workspace directory for a deleted recipe.
    """
    base_dir = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
    recipe_ws = os.path.join(base_dir, str(recipe_id))
    if os.path.exists(recipe_ws):
        shutil.rmtree(recipe_ws, ignore_errors=True)
