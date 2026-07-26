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

    # Clean stale hook scripts from previous runs
    for old_hook in ["mkosi.postinst", "mkosi.postinst.chroot", "mkosi.finalize", "mkosi.finalize.chroot", "mkosi.prepare", "mkosi.prepare.chroot"]:
        old_h_path = os.path.join(recipe_ws, old_hook)
        if os.path.exists(old_h_path):
            try:
                os.remove(old_h_path)
            except Exception:
                pass

    for d in subdirs:
        os.makedirs(os.path.join(recipe_ws, d), exist_ok=True)

    repart_dir = os.path.join(recipe_ws, "mkosi.repart")
    os.makedirs(repart_dir, exist_ok=True)
    with open(os.path.join(repart_dir, "10-esp.conf"), "w") as f:
        f.write("[Partition]\nType=esp\nFormat=vfat\nCopyFiles=/boot:/\nSizeMinBytes=512M\n")
    with open(os.path.join(repart_dir, "20-root.conf"), "w") as f:
        f.write("[Partition]\nType=root\nFormat=ext4\nCopyFiles=/\nSizeMinBytes=2G\n")

    os.makedirs(os.path.join(base_dir, "cache", "apt"), exist_ok=True)
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

    # 1.5. Static Hostname Overlay
    if recipe.hostname:
        etc_dir = os.path.join(extra_dir, "etc")
        os.makedirs(etc_dir, exist_ok=True)
        with open(os.path.join(etc_dir, "hostname"), "w") as f:
            f.write(recipe.hostname.strip().lower() + "\n")

    # 2. Custom APT Repositories (Populated into both mkosi.skeleton and mkosi.extra)
    rel = recipe.release or "bookworm"
    repo_lines = []
    if recipe.repositories and isinstance(recipe.repositories, list):
        for repo in recipe.repositories:
            if isinstance(repo, dict) and repo.get("url"):
                url = repo.get("url")
                suite = repo.get("suite") or rel
                comp = repo.get("components") or "main"
                repo_lines.append(f"deb [trusted=yes] {url} {suite} {comp}")

    if repo_lines:
        for base_tree in ["mkosi.skeleton", "mkosi.extra"]:
            sources_dir = os.path.join(workspace_path, base_tree, "etc", "apt", "sources.list.d")
            os.makedirs(sources_dir, exist_ok=True)
            with open(os.path.join(sources_dir, "custom.list"), "w") as f:
                f.write("\n".join(repo_lines) + "\n")

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

    # 3.4. Persistent APT Package Cache configuration
    for base_tree in ["mkosi.skeleton", "mkosi.extra"]:
        apt_conf_dir = os.path.join(workspace_path, base_tree, "etc", "apt", "apt.conf.d")
        os.makedirs(apt_conf_dir, exist_ok=True)
        with open(os.path.join(apt_conf_dir, "99duro-cache"), "w") as f:
            f.write('Dir::Cache::Archives "/opt/data/duro_workspace/cache/apt";\n')

    # 3.5. Prepare script — runs on HOST before package installation (mkosi v14)
    # Uses $BUILDROOT to access the rootfs. Writes custom repos and runs apt-get update
    # so that edge packages are resolvable when mkosi runs apt-get install.
    prepare_script_lines = [
        "#!/bin/bash",
        "set -e",
        'export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH',
        '',
        '# Determine rootfs path — mkosi v14 passes $BUILDROOT',
        'ROOT="${BUILDROOT:-/}"',
        '',
        '# Write custom APT repos into the rootfs',
        'mkdir -p "$ROOT/etc/apt/sources.list.d"',
        "cat << 'REPOEOF' > \"$ROOT/etc/apt/sources.list.d/custom.list\"",
    ]
    prepare_script_lines.extend(repo_lines)
    prepare_script_lines.extend([
        "REPOEOF",
        '',
        '# Run apt-get update inside the rootfs chroot',
        'if [ "$ROOT" != "/" ] && [ -d "$ROOT/usr" ]; then',
        '  chroot "$ROOT" apt-get update --allow-insecure-repositories --allow-unauthenticated || true',
        'elif command -v apt-get >/dev/null 2>&1; then',
        '  apt-get update --allow-insecure-repositories --allow-unauthenticated || true',
        'fi',
    ])

    prepare_path = os.path.join(workspace_path, "mkosi.prepare")
    with open(prepare_path, "w") as f:
        f.write("\n".join(prepare_script_lines) + "\n")
    os.chmod(prepare_path, 0o755)

    # 4. Post-install script hook & timezone setup
    # NOTE: In mkosi v14 (Debian package), mkosi.postinst runs on the HOST with $BUILDROOT
    # pointing to the rootfs. We must chroot into $BUILDROOT to modify the target image.
    # Edge packages are installed by mkosi itself via [Content] Packages= after
    # mkosi.prepare.chroot adds custom APT repos.
    postinst_commands = []

    if recipe.timezone and recipe.timezone.strip():
        tz = recipe.timezone.strip()
        postinst_commands.append(f"ln -sf /usr/share/zoneinfo/{tz} /etc/localtime 2>/dev/null && echo \"{tz}\" > /etc/timezone 2>/dev/null || true")

    hostname_mac_script = """
# Auto-configure hostname to equal active network interface MAC address (strictly lowercase, no colons/delimiters)
IFACE=$(ip -4 route show default 2>/dev/null | awk '/default/ {print $5}' | head -n 1)
if [ -z "$IFACE" ]; then
  IFACE=$(ip -o link show 2>/dev/null | awk -F': ' '$2 != "lo" {print $2; exit}')
fi
if [ -n "$IFACE" ]; then
  MAC=$(cat /sys/class/net/$IFACE/address 2>/dev/null | tr -d ':' | tr '[:upper:]' '[:lower:]')
  if [ -n "$MAC" ]; then
    echo "Setting hostname to MAC address: $MAC (interface: $IFACE)"
    hostnamectl set-hostname "$MAC" 2>/dev/null || echo "$MAC" > /etc/hostname
    if [ -f /etc/hosts ]; then
      sed -i "s/127.0.1.1.*/127.0.1.1\t$MAC/g" /etc/hosts 2>/dev/null || true
    fi
  fi
fi
"""

    if recipe.hostname_from_netif:
        postinst_commands.append(hostname_mac_script)

    if recipe.raw_postinst and recipe.raw_postinst.strip():
        postinst_commands.append(recipe.raw_postinst.strip())

    # Clean formatted postinst commands
    postinst_body = "\n".join(postinst_commands) if postinst_commands else "echo '[POSTINST] Complete.'"

    postinst_script = f"""#!/bin/bash
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH

ROOT="${{BUILDROOT:-/}}"

# 1. Install pre-downloaded Edge platform .deb packages inside chroot
if [ -d "$ROOT/opt/edge_packages" ] && [ -n "$(ls -A "$ROOT/opt/edge_packages"/*.deb 2>/dev/null)" ]; then
  echo "[POSTINST] Installing pre-downloaded Edge platform packages via dpkg..."
  chroot "$ROOT" /bin/bash -c "export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:\\$PATH; dpkg -i --force-depends /opt/edge_packages/*.deb || true"
  rm -rf "$ROOT/opt/edge_packages"
fi

# 2. Run recipe post-install hooks (timezone, hostname MAC, custom scripts)
if [ "$ROOT" != "/" ] && [ -d "$ROOT/tmp" ]; then
  cat << 'HOOKEOF' > "$ROOT/tmp/recipe_postinst.sh"
#!/bin/bash
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH
{postinst_body}
HOOKEOF
  chmod +x "$ROOT/tmp/recipe_postinst.sh"
  chroot "$ROOT" /bin/bash /tmp/recipe_postinst.sh || true
  rm -f "$ROOT/tmp/recipe_postinst.sh"
else
  {postinst_body}
fi
# 3. Clean up non-Intel firmware, docs, locales, and APT caches from rootfs
echo "[POSTINST] Stripping non-Intel firmware, documentation, and APT cache..."
rm -rf "$ROOT"/usr/lib/firmware/nvidia* "$ROOT"/usr/lib/firmware/amdgpu* "$ROOT"/usr/lib/firmware/radeon* "$ROOT"/usr/lib/firmware/qcom* "$ROOT"/usr/lib/firmware/mellanox* "$ROOT"/usr/lib/firmware/mrvl* "$ROOT"/usr/lib/firmware/mediatek* "$ROOT"/usr/lib/firmware/broadcom* "$ROOT"/usr/lib/firmware/brcm* "$ROOT"/usr/lib/firmware/ath9k* "$ROOT"/usr/lib/firmware/ath10k* "$ROOT"/usr/lib/firmware/ath11k* "$ROOT"/usr/lib/firmware/ath12k* "$ROOT"/usr/lib/firmware/cxgb3* "$ROOT"/usr/lib/firmware/cxgb4* "$ROOT"/usr/lib/firmware/liquidio* "$ROOT"/usr/lib/firmware/netronome* "$ROOT"/usr/share/doc/* "$ROOT"/usr/share/man/* "$ROOT"/usr/share/info/* "$ROOT"/usr/share/help/* "$ROOT"/usr/share/gtk-doc/* "$ROOT"/usr/share/locale/* "$ROOT"/usr/share/sounds/* "$ROOT"/usr/share/icons/* "$ROOT"/var/cache/apt/* "$ROOT"/var/lib/apt/lists/* || true
"""
    for hk in ["mkosi.postinst", "mkosi.finalize"]:
        postinst_path = os.path.join(workspace_path, hk)
        with open(postinst_path, "w") as f:
            f.write(postinst_script)
        os.chmod(postinst_path, 0o755)

    # 5. Firstboot script & systemd service
    firstboot_lines = ["#!/bin/bash", "set -e"]

    if recipe.hostname_from_netif:
        firstboot_lines.append(hostname_mac_script)

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
