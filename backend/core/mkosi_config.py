import os
from models import Recipe


def generate_mkosi_conf(recipe: Recipe, workspace_path: str) -> str:
    """
    Generates mkosi.conf configuration for systemd image builder and
    injects custom APT repositories into mkosi.extra/etc/apt/sources.list.d/
    """
    pkgs = list(recipe.packages) if recipe.packages else ["systemd", "systemd-sysv", "dbus", "iproute2"]
    if "systemd-boot" not in pkgs:
        pkgs.append("systemd-boot")
    # Standard distribution packages only for mkosi base build (Edge packages are pre-downloaded and installed via dpkg)
    std_pkgs = [p for p in pkgs if not p.lower().startswith("edge-")]
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

    distro = (recipe.distribution or "debian").lower()
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
            "systemd-sysv": "",
            "coreutils": "",
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

    config_lines = [
        "[Distribution]",
        f"Distribution={mkosi_distro}",
        f"Release={recipe.release}",
        f"Architecture={mkosi_arch}",
        f"Repositories={components}",
        "",
        "[Build]",
        "CacheDirectory=/opt/data/duro_workspace/cache",
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
        "WithRecommends=no",
        f"Packages=\n    {packages_formatted}",
    ]

    if remove_files:
        remove_files_formatted = "\n    ".join(remove_files)
        config_lines.append(f"RemoveFiles=\n    {remove_files_formatted}")

    config_lines.extend([
        "Autologin=yes",
        "SkeletonTrees=mkosi.skeleton",
    ])

    if recipe.kernel_params and recipe.kernel_params.strip():
        config_lines.append(f"KernelCommandLine={recipe.kernel_params.strip()}")

    if recipe.raw_mkosi_conf and recipe.raw_mkosi_conf.strip():
        config_lines.append("\n# Custom Raw Override")
        config_lines.append(recipe.raw_mkosi_conf.strip())

    content = "\n".join(config_lines) + "\n"

    conf_path = os.path.join(workspace_path, "mkosi.conf")
    with open(conf_path, "w") as f:
        f.write(content)

    return content
