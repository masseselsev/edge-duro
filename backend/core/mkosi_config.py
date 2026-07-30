import os
from models import Recipe


def generate_mkosi_conf(recipe: Recipe, workspace_path: str) -> str:
    """
    Generates mkosi.conf configuration for systemd image builder and
    injects custom APT repositories into mkosi.extra/etc/apt/sources.list.d/
    """
    pkgs = list(recipe.packages) if recipe.packages else ["systemd", "systemd-sysv", "dbus", "iproute2"]
    # "login" provides /bin/login, which agetty execs by default for BOTH manual
    # getty prompts and Autologin=yes (mkosi's autologin unit still shells out to
    # it with -f). With WithRecommends=no nothing pulls it in as a dependency of
    # systemd/bash/coreutils, so every console -- autologin or manual -- exec()s
    # a binary that doesn't exist: agetty prints the login prompt, the user types
    # a name, Enter is echoed by the kernel tty layer, and then nothing, because
    # there is no process left to read it.
    # "sudo" provides /usr/bin/sudo and the /etc/sudoers.d/ rule granting the
    # "sudo" group root access. Without it, adding a user to the "sudo" group
    # (via workspace.py's groupadd -f) creates an inert group -- nothing on the
    # system checks membership in it, so the recipe's sudo checkbox would
    # silently grant nothing on a recipe that happens not to list this package.
    for req_pkg in ["apt", "bash", "coreutils", "login", "sudo", "systemd-boot", "systemd-sysv", "initramfs-tools"]:
        if req_pkg not in pkgs:
            pkgs.append(req_pkg)

    distro = (recipe.distribution or "debian").lower()
    if "debian" in distro and not any("linux-image" in p.lower() for p in pkgs):
        pkgs.append("linux-image-amd64")
    elif "ubuntu" in distro and not any("linux-image" in p.lower() for p in pkgs):
        pkgs.append("linux-image-generic")

    # Standard distribution packages only for mkosi base build (Edge packages are pre-downloaded and installed via dpkg)
    std_pkgs = [p for p in pkgs if not p.lower().startswith("edge-")]
    
    # Ensure dracut-core is installed so mkosi delegates initrd generation to it
    # dracut builds non-hostonly initrds which include all generic storage modules (virtio_blk, etc)
    if "dracut-core" not in std_pkgs:
        std_pkgs.append("dracut-core")
        
    packages_formatted = "\n    ".join(std_pkgs)

    arch_map = {
        "amd64": "x86-64",
        "x86_64": "x86-64",
        "x86-64": "x86-64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    mkosi_arch = arch_map.get((recipe.architecture or "amd64").lower(), "x86-64")

    COMMON_REMOVE_FILES = [
        "/usr/lib/firmware/nvidia*",
        "/usr/lib/firmware/amdgpu*",
        "/usr/lib/firmware/radeon*",
        "/usr/lib/firmware/qcom*",
        "/usr/lib/firmware/mellanox*",
        "/usr/lib/firmware/mrvl*",
        "/usr/lib/firmware/mediatek*",
        "/usr/lib/firmware/broadcom*",
        "/usr/lib/firmware/brcm*",
        "/usr/lib/firmware/ath9k*",
        "/usr/lib/firmware/ath10k*",
        "/usr/lib/firmware/ath11k*",
        "/usr/lib/firmware/ath12k*",
        "/usr/lib/firmware/cxgb3*",
        "/usr/lib/firmware/cxgb4*",
        "/usr/lib/firmware/liquidio*",
        "/usr/lib/firmware/netronome*",
        "/usr/share/doc",
        "/usr/share/man",
        "/usr/share/info",
        "/usr/share/help",
        "/usr/share/gtk-doc",
        "/usr/share/locale/*",
        "/usr/share/sounds/*",
        "/usr/share/icons/*",
        "/var/cache/apt/*",
        "/var/lib/apt/lists/*",
    ]

    if "debian" in distro:
        mkosi_distro = "debian"
        components = "main contrib non-free non-free-firmware"
        pkg_map = {
            "linux-image-generic": "linux-image-amd64",
            "linux-firmware": "firmware-misc-nonfree intel-microcode firmware-sof-signed",
            "acpi-support": "acpi-support-base",
            "intel-media-driver": "intel-media-va-driver-non-free",
        }
        remove_files = COMMON_REMOVE_FILES
    elif "ubuntu" in distro:
        mkosi_distro = "ubuntu"
        components = "main restricted universe multiverse"
        pkg_map = {
            "linux-image-amd64": "linux-image-generic",
            "firmware-misc-nonfree": "intel-microcode firmware-sof-signed",
            "acpi-support-base": "",
            "acpi-support": "",
            "intel-media-va-driver-non-free": "intel-media-va-driver",
        }
        remove_files = COMMON_REMOVE_FILES
    else:
        mkosi_distro = recipe.distribution
        components = "main"
        pkg_map = {}
        remove_files = COMMON_REMOVE_FILES

    mapped_pkgs = []
    for p in std_pkgs:
        mapped_val = pkg_map.get(p.lower(), p)
        if mapped_val:
            mapped_pkgs.extend(mapped_val.split())
    std_pkgs = mapped_pkgs

    packages_formatted = "\n    ".join(std_pkgs)

    # Inject APT sources list into mkosi.extra tree
    extra_apt_dir = os.path.join(workspace_path, "mkosi.extra", "etc", "apt", "sources.list.d")
    os.makedirs(extra_apt_dir, exist_ok=True)

    sources_lines = []
    rel = recipe.release or "bookworm"

    # Custom APT repositories configured in Recipe UI
    if recipe.repositories and isinstance(recipe.repositories, list):
        for repo in recipe.repositories:
            if isinstance(repo, dict) and repo.get("url"):
                url = repo.get("url")
                suite = repo.get("suite") or rel
                comp = repo.get("components") or "main"
                sources_lines.append(f"deb [trusted=yes] {url} {suite} {comp}")

    if sources_lines:
        with open(os.path.join(extra_apt_dir, "custom.list"), "w") as f:
            f.write("\n".join(sources_lines) + "\n")

    # Force IPv4 for APT to prevent IPv6 blackhole hangs during package download
    apt_conf_dir = os.path.join(workspace_path, "mkosi.extra", "etc", "apt", "apt.conf.d")
    os.makedirs(apt_conf_dir, exist_ok=True)
    with open(os.path.join(apt_conf_dir, "99force-ipv4"), "w") as f:
        f.write('Acquire::ForceIPv4 "true";\n')

    # Package downloads must be cached on the persistent workspace volume.
    # CacheDirectory= is NOT the package cache -- it only holds the incremental
    # image cache and does nothing unless Incremental= is also enabled. The
    # distribution package manager's downloads go to PackageCacheDirectory=,
    # and when that is unset mkosi falls back to /var/cache/mkosi inside the
    # container. Only /app, /opt/data/duro_workspace and /proc are bind mounted
    # into the worker, so that fallback is container-local and every
    # "docker compose up --build" threw away the whole package cache (~1.2 GB
    # for ubuntu/resolute), forcing a full re-download on the next build.
    ws_root = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
    pkg_cache_dir = os.path.join(ws_root, "pkgcache")
    image_cache_dir = os.path.join(ws_root, "cache")
    for d in (pkg_cache_dir, image_cache_dir):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass

    config_lines = [
        "[Distribution]",
        f"Distribution={mkosi_distro}",
        f"Release={recipe.release}",
        f"Architecture={mkosi_arch}",
        f"Repositories={components}",
        "",
        "[Build]",
        f"PackageCacheDirectory={pkg_cache_dir}",
        f"CacheDirectory={image_cache_dir}",
        "WorkspaceDirectory=/opt/data/duro_workspace/mkosi_work",
        "BuildSources=",
        "WithNetwork=yes",
        "",
        "[Output]",
        f"ImageId={recipe.name.lower().replace(' ', '_')}",
        "Format=disk",
        "OutputDirectory=output",
        "",
        "[Content]",
        "Bootloader=systemd-boot",
        "Bootable=yes",
        "WithRecommends=no",
        f"Packages=\n    {packages_formatted}",
    ]

    if remove_files:
        remove_files_formatted = "\n    ".join(remove_files)
        config_lines.append(f"RemoveFiles=\n    {remove_files_formatted}")

    config_lines.extend([
        "Autologin=no",
        "SkeletonTrees=mkosi.skeleton",
    ])

    # Always ensure fsck.mode=skip is present to prevent recovery mode on fresh images
    kernel_params = (recipe.kernel_params or "").strip()
    if kernel_params:
        if "fsck.mode=skip" not in kernel_params and "fsck.mode" not in kernel_params:
            kernel_params = f"{kernel_params} fsck.mode=skip"
        if "quiet" not in kernel_params:
            kernel_params = f"quiet loglevel=3 {kernel_params}"
        config_lines.append(f"KernelCommandLine={kernel_params}")
    else:
        config_lines.append("KernelCommandLine=quiet loglevel=3 fsck.mode=skip console=ttyS0,115200 console=tty0 ipv6.disable=1 nohz=off")

    if recipe.raw_mkosi_conf and recipe.raw_mkosi_conf.strip():
        config_lines.append("\n# Custom Raw Override")
        config_lines.append(recipe.raw_mkosi_conf.strip())

    content = "\n".join(config_lines) + "\n"

    conf_path = os.path.join(workspace_path, "mkosi.conf")
    with open(conf_path, "w") as f:
        f.write(content)

    return content
