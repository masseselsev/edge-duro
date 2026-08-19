import os
from models import Recipe
from core.packages import (
    ARMBIAN_REPO_URL,
    armbian_source_line,
    base_distribution,
    is_armbian,
    resolve_package_list,
)


def generate_mkosi_conf(recipe: Recipe, workspace_path: str, exclude=frozenset(),
                        skip_repo_urls=frozenset()) -> str:
    """
    Generates mkosi.conf configuration for systemd image builder and
    injects custom APT repositories into mkosi.extra/etc/apt/sources.list.d/

    exclude -- имена пакетов, которых нет под архитектуру рецепта; их вычеркнула
    предполётная проверка (core/arch_check.py).
    skip_repo_urls -- репозитории, не публикующие индекс под эту архитектуру;
    в sources.list.d образа они не попадают.
    """
    # Only standard distribution packages reach mkosi -- Edge packages are
    # pre-downloaded and installed via dpkg. dracut-core is in the list so mkosi
    # delegates initrd generation to it: dracut builds non-hostonly initrds which
    # include all generic storage modules (virtio_blk, etc).
    std_pkgs, _ = resolve_package_list(recipe, exclude=exclude)
    packages_formatted = "\n    ".join(std_pkgs)

    # Armbian -- слой поверх Debian или Ubuntu, самому mkosi такое имя ничего не
    # говорит, поэтому вниз уходит базовый дистрибутив.
    distro = base_distribution(recipe.distribution, recipe.release)

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
        remove_files = COMMON_REMOVE_FILES
    elif "ubuntu" in distro:
        mkosi_distro = "ubuntu"
        components = "main restricted universe multiverse"
        remove_files = COMMON_REMOVE_FILES
    else:
        mkosi_distro = recipe.distribution
        components = "main"
        remove_files = COMMON_REMOVE_FILES

    # Inject APT sources list into mkosi.extra tree
    extra_apt_dir = os.path.join(workspace_path, "mkosi.extra", "etc", "apt", "sources.list.d")
    os.makedirs(extra_apt_dir, exist_ok=True)

    sources_lines = []
    rel = recipe.release or "bookworm"

    # Ядро, DTB и U-Boot под RK3588 приезжают отсюда: в самих Debian и Ubuntu
    # поддержки этих плат нет. Репозиторий добавляется сам, а не руками в UI,
    # иначе выбор платы собирал бы образ без ядра для неё.
    if is_armbian(recipe.distribution) and ARMBIAN_REPO_URL not in skip_repo_urls:
        sources_lines.append(armbian_source_line(rel))

    # Custom APT repositories configured in Recipe UI
    if recipe.repositories and isinstance(recipe.repositories, list):
        for repo in recipe.repositories:
            if isinstance(repo, dict) and repo.get("url"):
                url = repo.get("url")
                if url in skip_repo_urls:
                    continue
                suite = repo.get("suite") or rel
                comp = repo.get("components") or "main"
                sources_lines.append(f"deb [trusted=yes] {url} {suite} {comp}")

    custom_list = os.path.join(extra_apt_dir, "custom.list")
    if sources_lines:
        with open(custom_list, "w") as f:
            f.write("\n".join(sources_lines) + "\n")
    elif os.path.exists(custom_list):
        # The workspace is reused between builds: without this, sources written
        # by an earlier run would survive into an image that must not have them.
        os.remove(custom_list)

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

    # RK3588 стартует не через UEFI: boot ROM читает загрузчик по фиксированным
    # смещениям на носителе, EFI-раздела в этой цепочке нет вовсе. systemd-boot
    # тут не просто лишний -- с Bootable=yes mkosi собирал бы загрузочную схему,
    # которой плата никогда не воспользуется. Загрузку обеспечивают U-Boot в SPI
    # и extlinux от Armbian.
    rk3588 = is_armbian(recipe.distribution)

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
        # systemd-repart иначе берёт размер сектора у loop-устройства сборочного
        # хоста -- на этом воркере это 4096, а не 512. Встроенный в образ FAT
        # с 4K-секторами не читает загрузчик RK3588 (2017.09), он ждёт носитель
        # с 512-байтными секторами, каким и будет настоящая SD-карта/NVMe.
        "SectorSize=512",
        "",
        "[Content]",
    ]

    if rk3588:
        config_lines.append("Bootable=no")
    else:
        config_lines.append("Bootloader=systemd-boot")
        config_lines.append("Bootable=yes")

    config_lines.append("WithRecommends=no")
    config_lines.append(f"Packages=\n    {packages_formatted}")

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
