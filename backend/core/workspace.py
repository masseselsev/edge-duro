import os
import re
import shlex
import shutil
from typing import List
from models import Recipe, RecipeAsset


def prepare_workspace(recipe_id: int, recipe: Recipe = None) -> str:
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
        "mkosi.extra/etc/initramfs-tools",
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

    # Ensure initramfs-tools includes ISO9660 and CD-ROM modules in generated initrd
    initramfs_modules_file = os.path.join(recipe_ws, "mkosi.extra/etc/initramfs-tools/modules")
    with open(initramfs_modules_file, "w") as f:
        f.write("# Required storage & filesystem kernel modules for Edge OS Installer\n"
                "isofs\nsr_mod\ncdrom\nvfat\next4\nsd_mod\nahci\nloop\noverlay\n")

    repart_dir = os.path.join(recipe_ws, "mkosi.repart")
    if os.path.exists(repart_dir):
        shutil.rmtree(repart_dir, ignore_errors=True)
    os.makedirs(repart_dir, exist_ok=True)

    partitions = (recipe.partitions if (recipe and recipe.partitions) else None) or [
        {"mountpoint": "/boot", "size": "512M", "filesystem": "vfat", "type": "esp", "label": "edgeboot"},
        {"mountpoint": "/", "size": "8G", "filesystem": "ext4", "type": "root", "label": "edgeroot"},
        {"mountpoint": "/var/log/edge", "size": "1G", "filesystem": "ext4", "type": "generic", "label": "edgelog"},
        {"mountpoint": "/var/opt/edge", "size": "max", "filesystem": "ext4", "type": "generic", "label": "edgestor"},
    ]

    for idx, p in enumerate(partitions, start=1):
        p_type = (p.get("type") or "generic").lower()
        p_fs = (p.get("filesystem") or "ext4").lower()
        p_size = str(p.get("size") or "2G")
        p_mount = p.get("mountpoint") or "/"
        p_label = p.get("label") or f"part{idx}"

        conf_filename = f"{idx * 10:02d}-{p_type}-{p_label}.conf"
        conf_path = os.path.join(repart_dir, conf_filename)

        lines = ["[Partition]"]
        if p_type == "esp":
            lines.append("Type=esp")
            lines.append("Format=vfat")
            lines.append("CopyFiles=/boot:/")
        elif p_type == "root":
            lines.append("Type=root")
            lines.append(f"Format={p_fs}")
            lines.append("CopyFiles=/")
        elif p_type == "swap":
            lines.append("Type=swap")
            lines.append("Format=swap")
        else:
            lines.append("Type=linux-generic")
            lines.append(f"Format={p_fs}")
            if p_mount and p_mount != "/":
                lines.append(f"CopyFiles={p_mount}")

        if p_label:
            lines.append(f"Label={p_label}")

        if p_size and p_size.lower() not in ["max", "100%", "auto"]:
            size_val = p_size.upper()
            if not size_val.endswith("M") and not size_val.endswith("G") and not size_val.endswith("B"):
                size_val += "M"
            lines.append(f"SizeMinBytes={size_val}")

        with open(conf_path, "w") as f:
            f.write("\n".join(lines) + "\n")

    rel = (recipe.release if recipe else "bookworm") or "bookworm"
    cache_base = os.path.join(base_dir, "cache")
    os.makedirs(os.path.join(cache_base, "apt", "partial"), exist_ok=True)
    os.makedirs(os.path.join(cache_base, f"apt_{rel}", "partial"), exist_ok=True)
    if os.path.exists(cache_base):
        for item in os.listdir(cache_base):
            if item.startswith("apt"):
                os.makedirs(os.path.join(cache_base, item, "partial"), exist_ok=True)

    return recipe_ws


def populate_extra_tree(recipe: Recipe, assets: List[RecipeAsset], workspace_path: str):
    """
    Populates mkosi.extra/ overlay tree with SSH keys, custom APT repositories, assets, postinst, firstboot, and preseed files.
    """
    extra_dir = os.path.join(workspace_path, "mkosi.extra")

    # 1. SSH Keys & Custom SSH Port
    if recipe.ssh_keys:
        ssh_dir = os.path.join(extra_dir, "root", ".ssh")
        os.makedirs(ssh_dir, exist_ok=True)
        auth_keys_path = os.path.join(ssh_dir, "authorized_keys")
        with open(auth_keys_path, "w") as f:
            f.write("\n".join(recipe.ssh_keys) + "\n")

    ssh_port = getattr(recipe, 'ssh_port', 2222) or 2222
    sshd_conf_dir = os.path.join(extra_dir, "etc", "ssh", "sshd_config.d")
    os.makedirs(sshd_conf_dir, exist_ok=True)
    with open(os.path.join(sshd_conf_dir, "port.conf"), "w") as f:
        f.write(f"Port {ssh_port}\n")

    # systemd ssh.socket drop-in for socket-activated sshd
    ssh_sock_dir = os.path.join(extra_dir, "etc", "systemd", "system", "ssh.socket.d")
    os.makedirs(ssh_sock_dir, exist_ok=True)
    with open(os.path.join(ssh_sock_dir, "port.conf"), "w") as f:
        f.write(f"[Socket]\nListenStream=\nListenStream={ssh_port}\n")

    # 1.5. Static Hostname Overlay and /etc/fstab
    etc_dir = os.path.join(extra_dir, "etc")
    os.makedirs(etc_dir, exist_ok=True)
    if recipe.hostname:
        with open(os.path.join(etc_dir, "hostname"), "w") as f:
            f.write(recipe.hostname.strip().lower() + "\n")

    fstab_lines = [
        "# /etc/fstab: generated by D.U.R.O. image builder",
        "LABEL=edgeroot    /               ext4    defaults,rw          0    1",
        "LABEL=edgelog     /var/log/edge   ext4    defaults,nofail      0    2",
        "LABEL=edgestor    /var/opt/edge   ext4    defaults,nofail      0    2",
    ]
    with open(os.path.join(etc_dir, "fstab"), "w") as f:
        f.write("\n".join(fstab_lines) + "\n")

    # 1.6. Network configuration (systemd-networkd).
    # Without this the image ships no .network file matching a physical NIC, so
    # systemd-networkd (which is enabled but has nothing to manage) leaves the
    # interface DOWN and the machine has no network at all. The old simple-cdd
    # flow got this for free from debian-installer's netcfg, which has no
    # equivalent in the mkosi pipeline.
    #
    # The default Name= glob deliberately covers both the Debian-style eth0 and
    # the Ubuntu/systemd predictable enp0s3 naming, so one recipe works on both
    # distributions without knowing the NIC name at build time.
    net_dir = os.path.join(extra_dir, "etc", "systemd", "network")
    os.makedirs(net_dir, exist_ok=True)

    net_cfg = recipe.network_config if isinstance(recipe.network_config, dict) else {}
    net_ifaces = net_cfg.get("interfaces")
    if not isinstance(net_ifaces, list) or not net_ifaces:
        net_ifaces = [{"match": "en* eth*", "dhcp": True}]

    for idx, iface in enumerate(net_ifaces, start=1):
        if not isinstance(iface, dict):
            continue
        match = iface.get("name") or iface.get("match") or "en* eth*"
        lines = ["# Generated by D.U.R.O. image builder", "[Match]", f"Name={match}", "", "[Network]"]

        address = iface.get("address")
        use_dhcp = iface.get("dhcp", not address)
        if use_dhcp:
            lines.append("DHCP=yes")
        if address:
            # Accept either "10.0.0.5/24" or a bare address plus prefix/netmask.
            if "/" not in str(address):
                prefix = iface.get("prefix") or iface.get("netmask") or "24"
                address = f"{address}/{prefix}"
            lines.append(f"Address={address}")
        if iface.get("gateway"):
            lines.append(f"Gateway={iface['gateway']}")
        dns = iface.get("dns")
        if isinstance(dns, str):
            dns = [dns]
        if not dns or not isinstance(dns, list) or not any(dns):
            dns = ["77.88.8.8", "8.8.8.8", "1.1.1.1"]
        for server in dns:
            if server:
                lines.append(f"DNS={server}")

        # systemd-networkd applies the FIRST .network file (lexicographic order)
        # whose [Match] matches, so a catch-all glob must sort AFTER explicit
        # interface names -- otherwise "en* eth*" shadows every specific static
        # config that follows it and those NICs silently fall back to DHCP.
        safe = re.sub(r'[^A-Za-z0-9]+', '-', str(match)).strip('-') or f"if{idx}"
        prio = 70 + idx if any(c in str(match) for c in "*?[") else 10 + idx
        conf_name = f"{prio}-edge-{safe}.network"
        with open(os.path.join(net_dir, conf_name), "w") as f:
            f.write("\n".join(lines) + "\n")

    # Generate fallback /etc/resolv.conf so glibc getaddrinfo resolves DNS even before networkd/resolved initializes
    resolv_path = os.path.join(extra_dir, "etc", "resolv.conf")
    os.makedirs(os.path.dirname(resolv_path), exist_ok=True)
    if not os.path.exists(resolv_path) or os.path.getsize(resolv_path) == 0:
        with open(resolv_path, "w") as f:
            f.write("# Generated by D.U.R.O. image builder\nnameserver 77.88.8.8\nnameserver 8.8.8.8\nnameserver 1.1.1.1\n")

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
    # asset_hook_cmds collects assets flagged "Register as Post-Install Hook";
    # they are appended to the postinst body further below. Before this the
    # is_postinst flag was stored and returned by the API but never read by the
    # build, so ticking the box in the UI silently did nothing.
    asset_hook_cmds = []
    for asset in assets:
        if os.path.exists(asset.file_path):
            if asset.install_target:
                target_rel = asset.install_target.lstrip("/")
                dest_file = os.path.join(extra_dir, target_rel)
            else:
                dest_file = os.path.join(extra_dir, "opt", "custom", asset.filename)

            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            shutil.copy2(asset.file_path, dest_file)

            if getattr(asset, "is_postinst", False):
                # Path as seen from inside the image (mkosi.extra is overlaid
                # onto /), not the workspace path.
                in_image = "/" + os.path.relpath(dest_file, extra_dir)
                q_path = shlex.quote(in_image)
                if in_image.endswith(".deb"):
                    asset_hook_cmds.append(
                        f"echo '[POSTINST] Installing asset package {os.path.basename(in_image)}'\n"
                        f"dpkg -i {q_path} 2>/dev/null || apt-get -y -f install || true"
                    )
                else:
                    asset_hook_cmds.append(
                        f"echo '[POSTINST] Running asset hook {os.path.basename(in_image)}'\n"
                        f"chmod +x {q_path} 2>/dev/null || true\n"
                        f"{q_path} || true"
                    )

    # 3.4. Release-Isolated Persistent APT Package Cache configuration
    rel_clean = (recipe.release if recipe and recipe.release else "default").lower().replace(" ", "_")
    release_apt_cache = os.path.join(os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace"), "cache", f"apt_{rel_clean}")
    os.makedirs(release_apt_cache, exist_ok=True)

    # Pre-seed rootfs APT cache directory from persistent host cache
    extra_apt_archives = os.path.join(workspace_path, "mkosi.extra", "var", "cache", "apt", "archives")
    os.makedirs(extra_apt_archives, exist_ok=True)
    if os.path.exists(release_apt_cache):
        for cached_file in os.listdir(release_apt_cache):
            if cached_file.endswith(".deb"):
                src_p = os.path.join(release_apt_cache, cached_file)
                dst_p = os.path.join(extra_apt_archives, cached_file)
                if not os.path.exists(dst_p):
                    try:
                        shutil.copy2(src_p, dst_p)
                    except Exception:
                        pass

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
        '# Ensure host DNS resolv.conf is copied into rootfs so APT can resolve hosts',
        'cp -f /etc/resolv.conf "$ROOT/etc/resolv.conf" 2>/dev/null || true',
        'if [ "$ROOT" != "/" ] && [ -d "$ROOT/usr" ]; then',
        '  chroot "$ROOT" apt-get update --allow-insecure-repositories || true',
        'elif command -v apt-get >/dev/null 2>&1; then',
        '  apt-get update --allow-insecure-repositories || true',
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

    # System locale. C.UTF-8 is built into glibc and needs no generation; any
    # other locale has to be uncommented in /etc/locale.gen and compiled by
    # locale-gen (from the "locales" package) before update-locale can select
    # it. Note RemoveFiles strips /usr/share/locale/* (program translations),
    # not /usr/lib/locale (the compiled locale archive), so the locale itself
    # still works -- only translated program messages are absent.
    locale_val = (getattr(recipe, "locale", None) or "C.UTF-8").strip()
    if locale_val:
        q_locale = shlex.quote(locale_val)
        postinst_commands.append("\n".join([
            f"echo '[POSTINST] Configuring locale {locale_val}'",
            f"LOC={q_locale}",
            'if [ "$LOC" != "C.UTF-8" ] && [ "$LOC" != "C" ] && [ "$LOC" != "POSIX" ]; then',
            '  if [ -f /etc/locale.gen ]; then',
            '    grep -q "^$LOC " /etc/locale.gen 2>/dev/null || echo "$LOC UTF-8" >> /etc/locale.gen',
            '    sed -i "s/^# *\\($LOC \\)/\\1/" /etc/locale.gen 2>/dev/null || true',
            '  fi',
            '  command -v locale-gen >/dev/null 2>&1 && locale-gen "$LOC" 2>/dev/null || true',
            'fi',
            'if command -v update-locale >/dev/null 2>&1; then',
            '  update-locale LANG="$LOC" 2>/dev/null || true',
            'else',
            '  echo "LANG=$LOC" > /etc/default/locale',
            'fi',
        ]))

    # Credentials: root password and additional login accounts.
    # Without this the image ships root:* in /etc/shadow -- a locked account --
    # so password login is impossible on console, serial and SSH alike, leaving
    # only the console autologin and recipe ssh_keys as a way in.
    #
    # Passwords are piped to chpasswd inside the chroot, so the image stores
    # only the resulting crypt hash and never the plaintext. A value that
    # already looks like a crypt(3) hash ("$6$...") is installed verbatim with
    # "chpasswd -e" instead of being hashed a second time. Every interpolated
    # value is shell-quoted; usernames and group names are additionally
    # restricted to the POSIX portable set by the API schema.
    def _chpasswd_cmd(account: str, password: str) -> str:
        entry = shlex.quote(f"{account}:{password}")
        already_hashed = bool(re.match(r'^\$[0-9a-zA-Z]+\$', password))
        flag = " -e" if already_hashed else ""
        return f"echo {entry} | chpasswd{flag} || true"

    if recipe.root_password and recipe.root_password.strip():
        postinst_commands.append(
            "echo '[POSTINST] Setting root password'\n"
            + _chpasswd_cmd("root", recipe.root_password.strip())
        )

    if recipe.users and isinstance(recipe.users, list):
        for account in recipe.users:
            if not isinstance(account, dict):
                continue
            username = (account.get("username") or "").strip()
            if not username:
                continue
            shell_path = (account.get("shell") or "/bin/bash").strip()
            groups = [str(g).strip() for g in (account.get("groups") or []) if str(g).strip()]
            q_user = shlex.quote(username)

            lines = [f"echo '[POSTINST] Creating user {username}'"]
            lines.append(
                f"id -u {q_user} >/dev/null 2>&1 || "
                f"useradd -m -s {shlex.quote(shell_path)} {q_user} || true"
            )
            for group in groups:
                # -f makes this a no-op when the group already exists, and
                # creates it when it does not (netdev, for instance, is absent
                # from a minimal image even though the old preseed used it).
                lines.append(f"groupadd -f {shlex.quote(group)} 2>/dev/null || true")
            if groups:
                lines.append(f"usermod -aG {shlex.quote(','.join(groups))} {q_user} || true")
            password = account.get("password")
            if password:
                lines.append(_chpasswd_cmd(username, str(password)))
            postinst_commands.append("\n".join(lines))

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

    # Asset hooks run before the recipe's own raw postinst, so a custom script
    # can rely on anything the uploaded assets installed.
    postinst_commands.extend(asset_hook_cmds)

    if recipe.raw_postinst and recipe.raw_postinst.strip():
        postinst_commands.append(recipe.raw_postinst.strip())

    # Clean formatted postinst commands
    postinst_body = "\n".join(postinst_commands) if postinst_commands else "echo '[POSTINST] Complete.'"

    # Compose the systemd-boot loader entry cmdline from the recipe.
    # This entry is what actually boots (loader.conf sets "default edge.conf"),
    # so hardcoding the options here meant recipe.kernel_params only ever
    # reached mkosi's UKI and had no effect on a normal boot. Defaults are only
    # added when the recipe has not already specified an equivalent, so a recipe
    # can override the console or verbosity without ending up with duplicates.
    _kp = (recipe.kernel_params or "").strip()
    _loader_opts = ["root=LABEL=edgeroot", "rw"]
    if "quiet" not in _kp:
        _loader_opts += ["quiet", "loglevel=3"]
    if "fsck.mode" not in _kp:
        _loader_opts.append("fsck.mode=skip")
    if "console=" not in _kp:
        _loader_opts += ["console=tty0", "console=ttyS0,115200"]
    if _kp:
        _loader_opts.append(_kp)
    loader_options = " ".join(_loader_opts)

    postinst_script = f"""#!/bin/bash
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH

ROOT="${{BUILDROOT:-/}}"

# Copy host DNS configuration into rootfs for chroot network access
cp -f /etc/resolv.conf "$ROOT/etc/resolv.conf" 2>/dev/null || true

# 1. Install pre-downloaded Edge platform .deb packages inside chroot
if [ -d "$ROOT/opt/edge_packages" ] && [ -n "$(ls -A "$ROOT/opt/edge_packages"/*.deb 2>/dev/null)" ]; then
  echo "[POSTINST] Installing pre-downloaded Edge platform packages via dpkg..."
  # Mount pseudo-filesystems for apt/dpkg to work correctly
  mount -t proc proc "$ROOT/proc" 2>/dev/null || true
  mount -t sysfs sys "$ROOT/sys" 2>/dev/null || true
  mount --bind /dev "$ROOT/dev" 2>/dev/null || true

  chroot "$ROOT" /bin/bash -c "
    export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:\\$PATH
    ln -sf /bin/bash /bin/sh
    mkdir -p /opt/edge/venv/bin /opt/edge/bin /usr/bin
    if [ ! -f /opt/edge/venv/bin/python3.14 ]; then
      ln -sf /usr/bin/python3 /opt/edge/venv/bin/python3.14 2>/dev/null || true
      ln -sf /usr/bin/python3 /opt/edge/venv/bin/python3 2>/dev/null || true
      ln -sf /usr/bin/python3 /opt/edge/venv/bin/python 2>/dev/null || true
    fi

    if ! command -v apt-mark >/dev/null 2>&1; then
      echo '#!/bin/bash' > /usr/bin/apt-mark
      echo 'exit 0' >> /usr/bin/apt-mark
      chmod +x /usr/bin/apt-mark
    fi

    if [ ! -f /opt/edge/bin/ctrl-cli ] || [ ! -x /opt/edge/bin/ctrl-cli ]; then
      echo '#!/bin/bash' > /opt/edge/bin/ctrl-cli
      echo 'exit 0' >> /opt/edge/bin/ctrl-cli
      chmod +x /opt/edge/bin/ctrl-cli
    fi

    # 1. Unpack all deb packages without running postinst scripts
    dpkg --unpack --force-depends --force-overwrite /opt/edge_packages/*.deb || true

    # 2. Pre-create directories and files expected by edge-base postinst
    mkdir -p /etc/edge/webserver.0 /etc/edge /opt/edge/bin /opt/edge/venv/bin
    touch /etc/edge/webserver.0/htpasswd 2>/dev/null || true

    # 3. Fix bash double bracket syntax in autosdk script if present
    if [ -f /opt/edge/share/etc/environment.d/02-autosdk.sh ]; then
      sed -i 's/\\[\\[/\\[/g; s/\\]\\]/\\]/g' /opt/edge/share/etc/environment.d/02-autosdk.sh 2>/dev/null || true
    fi

    # 4. Convert strict 'set -e' to non-blocking 'set +e' in all postinst scripts for chroot build safety
    for pscript in /var/lib/dpkg/info/*.postinst /var/lib/dpkg/info/*.preinst; do
      if [ -f \"\\$pscript\" ]; then
        sed -i 's/^set -e/set +e/g' \"\\$pscript\" 2>/dev/null || true
        sed -i 's|/opt/edge/bin/ctrl-cli|/bin/true|g' \"\\$pscript\" 2>/dev/null || true
      fi
    done

    # 5. Overwrite ctrl-cli executable with a clean stub if it fails at runtime in chroot
    echo '#!/bin/bash' > /opt/edge/bin/ctrl-cli
    echo 'exit 0' >> /opt/edge/bin/ctrl-cli
    chmod +x /opt/edge/bin/ctrl-cli

    # 6. Fetch missing dependencies and configure all unpacked packages
    export DEBIAN_FRONTEND=noninteractive
    rm -f /etc/apt/apt.conf.d/*mkosi* /etc/apt/apt.conf.d/*cache* 2>/dev/null || true
    mkdir -p /var/cache/apt/archives/partial /var/lib/apt/lists/partial
    apt-get update --allow-insecure-repositories || true
    apt-get install -f -y --allow-unauthenticated || true
    dpkg --configure --pending --force-depends || true
  "

  # Unmount pseudo-filesystems
  umount "$ROOT/proc" 2>/dev/null || true
  umount "$ROOT/sys" 2>/dev/null || true
  umount -l "$ROOT/dev" 2>/dev/null || true

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
# 3. Clean up non-Intel firmware, docs, locales, machine-id for ConditionFirstBoot, and APT caches from rootfs
echo "[POSTINST] Stripping non-Intel firmware, documentation, and uninitializing machine-id for firstboot..."
rm -f "$ROOT"/etc/machine-id || true
rm -rf "$ROOT"/usr/lib/firmware/nvidia* "$ROOT"/usr/lib/firmware/amdgpu* "$ROOT"/usr/lib/firmware/radeon* "$ROOT"/usr/lib/firmware/qcom* "$ROOT"/usr/lib/firmware/mellanox* "$ROOT"/usr/lib/firmware/mrvl* "$ROOT"/usr/lib/firmware/mediatek* "$ROOT"/usr/lib/firmware/broadcom* "$ROOT"/usr/lib/firmware/brcm* "$ROOT"/usr/lib/firmware/ath9k* "$ROOT"/usr/lib/firmware/ath10k* "$ROOT"/usr/lib/firmware/ath11k* "$ROOT"/usr/lib/firmware/ath12k* "$ROOT"/usr/lib/firmware/cxgb3* "$ROOT"/usr/lib/firmware/cxgb4* "$ROOT"/usr/lib/firmware/liquidio* "$ROOT"/usr/lib/firmware/netronome* "$ROOT"/usr/share/doc/* "$ROOT"/usr/share/man/* "$ROOT"/usr/share/info/* "$ROOT"/usr/share/help/* "$ROOT"/usr/share/gtk-doc/* "$ROOT"/usr/share/locale/* "$ROOT"/usr/share/sounds/* "$ROOT"/usr/share/icons/* || true

# 4. Ensure systemd-boot bootloader, vmlinuz, and initrd are prepared in /boot (ESP partition)
echo "[POSTINST] Initializing systemd-boot and copying kernel/initrd into /boot..."
if [ "$ROOT" != "/" ] && [ -d "$ROOT/tmp" ]; then
  # Re-mount pseudo-filesystems for bootctl and update-initramfs to work correctly
  mount -t proc proc "$ROOT/proc" 2>/dev/null || true
  mount -t sysfs sys "$ROOT/sys" 2>/dev/null || true
  mount --bind /dev "$ROOT/dev" 2>/dev/null || true
  mount -t devpts devpts "$ROOT/dev/pts" 2>/dev/null || true

  chroot "$ROOT" /bin/bash -c '
    export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH
    # Install the bootloader into /boot, not the bootctl default of /efi. The
    # ESP repart definition copies /boot into the ESP root (CopyFiles=/boot:/),
    # so anything bootctl writes to /efi never reaches the ESP -- which left the
    # installed disk with no /EFI/BOOT/BOOTX64.EFI and made UEFI firmware report
    # "No bootable option or device was found" once the install ISO was removed.
    bootctl install --esp-path=/boot --no-variables 2>/dev/null || true

    # bootctl may refuse a non-FAT --esp-path, so place the EFI binaries
    # directly as well. Both destinations are what UEFI firmware looks for:
    # EFI/BOOT/BOOT<arch>.EFI is the removable-media fallback path.
    mkdir -p /boot/EFI/BOOT /boot/EFI/systemd
    for sb in /usr/lib/systemd/boot/efi/systemd-boot*.efi; do
      [ -f "$sb" ] || continue
      cp -f "$sb" /boot/EFI/systemd/ 2>/dev/null || true
      sb_arch=$(basename "$sb" .efi | sed s/^systemd-boot//)
      sb_upper=$(echo "$sb_arch" | tr "[:lower:]" "[:upper:]")
      cp -f "$sb" "/boot/EFI/BOOT/BOOT$sb_upper.EFI" 2>/dev/null || true
      echo "[POSTINST] Installed $sb as /boot/EFI/BOOT/BOOT$sb_upper.EFI"
    done

    KVER=$(ls /lib/modules 2>/dev/null | sort -V | tail -n1)

    # Ensure initramfs is generated with all required modules for VirtualBox/virtio
    # AND ISO installer boot (isofs/sr_mod/cdrom for CD-ROM boot media mounting)
    if [ -n "$KVER" ] && command -v update-initramfs >/dev/null 2>&1; then
      echo "[POSTINST] Adding virtio + ISO boot modules to initramfs-tools/modules..."
      for m in virtio_blk virtio_pci virtio_net virtio_scsi virtio_console \
               vfat fat ext4 ahci sd_mod scsi_mod \
               isofs sr_mod cdrom loop usbcore usb-storage; do
        grep -qxF "$m" /etc/initramfs-tools/modules 2>/dev/null || echo "$m" >> /etc/initramfs-tools/modules
      done
      echo "[POSTINST] Regenerating initramfs for kernel $KVER with virtio+ISO modules..."
      update-initramfs -u -k "$KVER" || true
    fi

    for f in /boot/vmlinuz-$KVER /boot/vmlinuz* /vmlinuz*; do
      if [ -f "$f" ] && [ "$f" != "/boot/vmlinuz" ]; then
        cp -f "$f" /boot/vmlinuz 2>/dev/null || true
        break
      fi
    done
    for f in /boot/initrd.img-$KVER /boot/initrd* /boot/initramfs* /initrd* /initramfs*; do
      if [ -f "$f" ] && [ "$f" != "/boot/initrd.img" ]; then
        cp -f "$f" /boot/initrd.img 2>/dev/null || true
        break
      fi
    done
    # Point the loader entry at kernel/initrd paths that actually exist in the
    # ESP. The plain /boot/vmlinuz copy above is not always produced, and an
    # entry referencing a missing file makes systemd-boot fail on its default
    # entry, so prefer the versioned names and fall back to the plain ones.
    KIMG=""
    IIMG=""
    if [ -f "/boot/vmlinuz-$KVER" ]; then
      KIMG="/vmlinuz-$KVER"
    elif [ -f /boot/vmlinuz ]; then
      KIMG="/vmlinuz"
    fi
    if [ -f "/boot/initrd.img-$KVER" ]; then
      IIMG="/initrd.img-$KVER"
    elif [ -f /boot/initrd.img ]; then
      IIMG="/initrd.img"
    fi

    mkdir -p /boot/loader/entries
    echo "timeout 3" > /boot/loader/loader.conf
    echo "console-mode max" >> /boot/loader/loader.conf
    if [ -n "$KIMG" ] && [ -n "$IIMG" ]; then
      echo "default edge.conf" >> /boot/loader/loader.conf
      echo "title Edge OS" > /boot/loader/entries/edge.conf
      echo "linux $KIMG" >> /boot/loader/entries/edge.conf
      echo "initrd $IIMG" >> /boot/loader/entries/edge.conf
      echo "options {loader_options}" >> /boot/loader/entries/edge.conf
      echo "[POSTINST] Loader entry edge.conf -> linux $KIMG, initrd $IIMG"
    else
      # No loose kernel/initrd: drop the entry and let systemd-boot
      # auto-discover the UKI that mkosi generated in EFI/Linux.
      rm -f /boot/loader/entries/edge.conf
      echo "[POSTINST] WARNING: no kernel/initrd in /boot (KVER=$KVER); relying on UKI in EFI/Linux"
    fi

    echo "[POSTINST] ESP staging /boot contents:"
    ls -la /boot 2>/dev/null || true
    echo "[POSTINST] ESP staging /boot/EFI/BOOT contents:"
    ls -la /boot/EFI/BOOT 2>/dev/null || true

    # mkosi'"'"'s Autologin=yes writes getty overrides ending in a bare "$TERM"
    # token (see getty@tty1.service.d and console-getty.service.d). That is
    # only meaningful under systemd-nspawn, which imports TERM from the host;
    # on a real boot (this disk image booted as a VM/bare metal) nothing ever
    # sets TERM in PID 1'"'"'s environment, so agetty inherits an undefined
    # terminal type. Force a known-good "linux" TERM so autologin does not
    # depend on that substitution succeeding.
    for gdrop in /etc/systemd/system/getty@tty1.service.d/*.conf \
                 /etc/systemd/system/console-getty.service.d/*.conf; do
      [ -f "$gdrop" ] || continue
      sed -i "s/ \\$TERM/ linux/" "$gdrop"
      grep -q "^Environment=TERM=" "$gdrop" || sed -i "/^\\[Service\\]/a Environment=TERM=linux" "$gdrop"
      echo "[POSTINST] Pinned TERM=linux in $gdrop"
    done
  ' || true

  # Unmount pseudo-filesystems
  umount "$ROOT/dev/pts" 2>/dev/null || true
  umount "$ROOT/proc" 2>/dev/null || true
  umount "$ROOT/sys" 2>/dev/null || true
  umount -l "$ROOT/dev" 2>/dev/null || true
fi
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

    # 5b. Disk expansion service (always installed, independent of the optional
    # firstboot script above). The installer deploys images with a byte-for-byte
    # dd, so the backup GPT header and last-usable-LBA still describe the smaller
    # source image rather than the target disk. Until those are corrected the
    # trailing partition cannot claim the extra capacity, stranding most of a
    # large disk (a 9.5 GiB image on a 25 GiB disk leaves ~15 GiB unusable).
    growfs_bin_dir = os.path.join(extra_dir, "opt", "edge", "bin")
    os.makedirs(growfs_bin_dir, exist_ok=True)
    growfs_script_path = os.path.join(growfs_bin_dir, "growfs.sh")
    with open(growfs_script_path, "w") as f:
        f.write("""#!/bin/sh
# Expand the last GPT partition of the boot disk to fill the physical device.
# Runs once, then drops a stamp file so subsequent boots are no-ops.
# Only uses util-linux + e2fsprogs tooling, both present in a base install.
STAMP=/var/lib/edge/growfs.done
[ -e "$STAMP" ] && exit 0

log() { echo "[GROWFS] $*"; }

ROOT_SRC=$(findmnt -n -o SOURCE / 2>/dev/null)
ROOT_DEV=$(readlink -f "$ROOT_SRC" 2>/dev/null)
case "$ROOT_DEV" in
    /dev/*) ;;
    *) log "cannot resolve root device from '$ROOT_SRC', skipping"; exit 0 ;;
esac

PK=$(lsblk -no PKNAME "$ROOT_DEV" 2>/dev/null | head -n1 | tr -d ' ')
[ -n "$PK" ] || { log "root $ROOT_DEV is not on a partitioned disk, skipping"; exit 0; }
DISK="/dev/$PK"
[ -b "$DISK" ] || { log "$DISK is not a block device, skipping"; exit 0; }

LAST_PART=$(lsblk -nrpo NAME,TYPE "$DISK" 2>/dev/null | awk '$2=="part" {p=$1} END {print p}')
[ -n "$LAST_PART" ] || { log "no partitions found on $DISK, skipping"; exit 0; }
LAST_NR=$(echo "$LAST_PART" | grep -o '[0-9]*$')
[ -n "$LAST_NR" ] || { log "cannot parse partition number from $LAST_PART, skipping"; exit 0; }

# Move the backup GPT header and last-usable-LBA to the true end of the disk.
log "relocating backup GPT header on $DISK"
if ! sfdisk --relocate gpt-bak-std "$DISK" >/dev/null 2>&1; then
    log "GPT relocation reported an error (continuing)"
fi

# Extend the trailing partition over the space that just became addressable.
log "growing partition $LAST_NR of $DISK"
if ! echo ", +" | sfdisk -N "$LAST_NR" --no-reread --force "$DISK" >/dev/null 2>&1; then
    log "partition grow failed, leaving disk untouched"
    exit 0
fi

partx -u "$DISK" >/dev/null 2>&1 || partprobe "$DISK" >/dev/null 2>&1 || true
udevadm settle >/dev/null 2>&1 || true

FSTYPE=$(blkid -o value -s TYPE "$LAST_PART" 2>/dev/null)
case "$FSTYPE" in
    ext2|ext3|ext4)
        log "resizing $FSTYPE on $LAST_PART"
        resize2fs "$LAST_PART" || { log "resize2fs failed, will retry next boot"; exit 0; }
        ;;
    xfs)
        MP=$(findmnt -n -o TARGET "$LAST_PART" 2>/dev/null | head -n1)
        [ -n "$MP" ] || { log "xfs on $LAST_PART not mounted, cannot grow"; exit 0; }
        log "growing xfs mounted at $MP"
        xfs_growfs "$MP" || { log "xfs_growfs failed, will retry next boot"; exit 0; }
        ;;
    *)
        log "unsupported filesystem '$FSTYPE' on $LAST_PART, grew partition only"
        ;;
esac

mkdir -p /var/lib/edge
: > "$STAMP"
log "completed"
""")
    os.chmod(growfs_script_path, 0o755)

    growfs_systemd_dir = os.path.join(extra_dir, "etc", "systemd", "system")
    os.makedirs(growfs_systemd_dir, exist_ok=True)
    with open(os.path.join(growfs_systemd_dir, "edge-growfs.service"), "w") as f:
        f.write("""[Unit]
Description=Edge OS Expand Last Partition To Fill Disk
Documentation=man:sfdisk(8)
After=local-fs.target
Before=edge-firstboot.service
ConditionPathExists=!/var/lib/edge/growfs.done

[Service]
Type=oneshot
ExecStart=/opt/edge/bin/growfs.sh
RemainAfterExit=yes
StandardOutput=journal+console
StandardError=journal+console

[Install]
WantedBy=multi-user.target
""")

    growfs_wants_dir = os.path.join(extra_dir, "etc", "systemd", "system", "multi-user.target.wants")
    os.makedirs(growfs_wants_dir, exist_ok=True)
    growfs_link = os.path.join(growfs_wants_dir, "edge-growfs.service")
    if not os.path.exists(growfs_link):
        try:
            os.symlink("/etc/systemd/system/edge-growfs.service", growfs_link)
        except Exception:
            pass

    # 5c. Edge network firstboot (systemd-networkd port of networking-cli).
    # The Edge platform's own /opt/edge/bin/networking-cli is built entirely on
    # ifupdown -- it calls "ifup" and "systemctl restart networking" and writes
    # /etc/network/interfaces.d/. ifupdown is not installed in mkosi images and
    # would fight systemd-networkd, so this reproduces the same result natively.
    #
    # Behaviour mirrored from edge.support.networking:
    #   primary NIC  = first interface with a live link (operstate/carrier),
    #                  DHCP plus the static alias 192.168.222.<last MAC octet>
    #   camera NICs  = remaining interfaces sorted, 192.168.<index+2>4.1/24
    #                  with MTU 6000 (jumbo frames)
    #   /etc/network/management-mac = primary MAC, required by the Edge web UI
    #                  (webserver/sysconf/api_network.py), the elevator hook
    #                  elevator.d/*/01-network and setup-cam-networks.py.
    netconf_script_path = os.path.join(growfs_bin_dir, "edge-netconf.sh")
    with open(netconf_script_path, "w") as f:
        f.write("""#!/bin/sh
# Configure networking the way the Edge platform expects, on systemd-networkd.
# Runs once, then stamps itself so later boots are no-ops.
STAMP=/var/lib/edge/netconf.done
[ -e "$STAMP" ] && exit 0

# Only meaningful on Edge images; a plain base image keeps the build-time
# DHCP catch-all and needs none of the camera/management-mac handling.
[ -d /opt/edge ] || exit 0

log() { echo "[EDGE-NET] $*"; }

NETDIR=/etc/systemd/network
mkdir -p "$NETDIR" /var/lib/edge /etc/network

# Physical NICs only: a real device has a /sys/class/net/<if>/device symlink,
# which excludes lo, bridges, veth and other virtual interfaces.
IFACES=""
for d in /sys/class/net/*; do
    n=$(basename "$d")
    [ "$n" = "lo" ] && continue
    [ -e "$d/device" ] || continue
    IFACES="$IFACES $n"
done
IFACES=$(echo $IFACES | tr ' ' '\\n' | sort | tr '\\n' ' ')
if [ -z "$IFACES" ]; then
    log "no physical interfaces found, leaving build-time defaults in place"
    exit 0
fi
log "physical interfaces:$IFACES"

# Links must be up before carrier can be read.
for n in $IFACES; do
    ip link set "$n" up 2>/dev/null || true
done

# Primary = first interface with a live link, same criterion networking-cli
# used (it polled for operstate UP / LOWER_UP for up to 60 seconds).
PRIMARY=""
attempt=0
while [ "$attempt" -lt 60 ]; do
    for n in $IFACES; do
        if [ "$(cat /sys/class/net/$n/carrier 2>/dev/null || echo 0)" = "1" ]; then
            PRIMARY="$n"
            break
        fi
    done
    [ -n "$PRIMARY" ] && break
    attempt=$((attempt + 1))
    sleep 1
done

if [ -z "$PRIMARY" ]; then
    PRIMARY=$(echo $IFACES | cut -d' ' -f1)
    log "no link detected after 60s, defaulting primary to $PRIMARY"
fi
log "primary interface: $PRIMARY"

MAC=$(cat "/sys/class/net/$PRIMARY/address" 2>/dev/null)
if [ -n "$MAC" ]; then
    echo "$MAC" > /etc/network/management-mac
    log "management-mac: $MAC"
fi

BYTE4=$(printf "%d" "0x$(echo "$MAC" | awk -F: '{print $6}')" 2>/dev/null || echo 1)
[ -n "$BYTE4" ] || BYTE4=1

cat > "$NETDIR/20-edge-primary-$PRIMARY.network" <<PRIMEOF
# Generated by D.U.R.O. edge-netconf
[Match]
Name=$PRIMARY

[Network]
DHCP=yes
Address=192.168.222.$BYTE4/24
PRIMEOF
log "primary $PRIMARY: DHCP + 192.168.222.$BYTE4/24"

idx=0
for n in $IFACES; do
    [ "$n" = "$PRIMARY" ] && continue
    oct=$((idx + 2))
    cat > "$NETDIR/30-edge-cam$idx-$n.network" <<CAMEOF
# Generated by D.U.R.O. edge-netconf
[Match]
Name=$n

[Network]
Address=192.168.${oct}4.1/24

[Link]
MTUBytes=6000
CAMEOF
    log "camera $n: 192.168.${oct}4.1/24 mtu 6000"
    idx=$((idx + 1))
done

systemctl restart systemd-networkd 2>/dev/null || true
: > "$STAMP"
log "completed"
""")
    os.chmod(netconf_script_path, 0o755)

    with open(os.path.join(growfs_systemd_dir, "edge-netconf.service"), "w") as f:
        f.write("""[Unit]
Description=Edge OS Network Configuration (systemd-networkd)
After=local-fs.target systemd-networkd.service
Before=network-online.target edge-firstboot.service
ConditionPathExists=!/var/lib/edge/netconf.done

[Service]
Type=oneshot
ExecStart=/opt/edge/bin/edge-netconf.sh
RemainAfterExit=yes
StandardOutput=journal+console
StandardError=journal+console

[Install]
WantedBy=multi-user.target
""")

    netconf_link = os.path.join(growfs_wants_dir, "edge-netconf.service")
    if not os.path.exists(netconf_link):
        try:
            os.symlink("/etc/systemd/system/edge-netconf.service", netconf_link)
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