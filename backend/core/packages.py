"""
Единый источник правды о том, какие пакеты получит сборка.

Раньше список собирался внутри generate_mkosi_conf. Предполётная проверка
архитектуры должна смотреть ровно на тот же список, иначе они разъедутся при
первой же правке, и проверка начнёт врать.
"""
from typing import Any, Dict, List, Tuple

# mkosi не соберёт загружаемый образ без этого, поэтому такие пакеты не
# пропускаются никогда -- ни по галочке, ни как-либо ещё. Список ровно тот,
# что бекенд добавляет сам; всё, что выбрал пользователь (включая edge-base),
# критичным не считается: arm64-образ должен собираться, пока arm64-версий
# платформенных пакетов ещё не существует.
CRITICAL_PACKAGES = frozenset({
    "apt",
    "bash",
    "coreutils",
    "login",
    "sudo",
    "systemd-boot",
    "systemd-sysv",
    "initramfs-tools",
    "dracut-core",
})

_KERNEL_PREFIX = "linux-image"

# Пакеты, которые предзагрузчик тянет всегда, даже если их нет в рецепте.
ALWAYS_EDGE_PACKAGES = ("edge-base", "edge-python3-core")

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
_REQUIRED_PACKAGES = (
    "apt", "bash", "coreutils", "login", "sudo",
    "systemd-boot", "systemd-sysv", "initramfs-tools",
)

_DEBIAN_PKG_MAP: Dict[str, str] = {
    "linux-image-generic": "linux-image-amd64",
    "linux-firmware": "firmware-misc-nonfree intel-microcode firmware-sof-signed",
    "acpi-support": "acpi-support-base",
    "intel-media-driver": "intel-media-va-driver-non-free",
}

_UBUNTU_PKG_MAP: Dict[str, str] = {
    "linux-image-amd64": "linux-image-generic",
    "firmware-misc-nonfree": "intel-microcode firmware-sof-signed",
    "acpi-support-base": "",
    "acpi-support": "",
    "intel-media-va-driver-non-free": "intel-media-va-driver",
}


def is_critical(name: str) -> bool:
    return name in CRITICAL_PACKAGES or name.startswith(_KERNEL_PREFIX)


def distro_family(distribution: Any) -> str:
    distro = (distribution or "debian").lower()
    if "ubuntu" in distro:
        return "ubuntu"
    if "debian" in distro:
        return "debian"
    return distro


def package_map(distribution: Any) -> Dict[str, str]:
    family = distro_family(distribution)
    if family == "ubuntu":
        return _UBUNTU_PKG_MAP
    if family == "debian":
        return _DEBIAN_PKG_MAP
    return {}


def kernel_package(distribution: Any, architecture: Any) -> str:
    """
    Ubuntu собирает linux-image-generic под обе архитектуры, у Debian имя
    несёт архитектуру в себе -- на arm64 linux-image-amd64 просто не существует.
    """
    if distro_family(distribution) == "ubuntu":
        return "linux-image-generic"
    arch = (architecture or "amd64").lower()
    return "linux-image-arm64" if arch in ("arm64", "aarch64") else "linux-image-amd64"


def resolve_package_list(recipe, exclude=frozenset()) -> Tuple[List[str], List[str]]:
    """
    Возвращает (std_pkgs, edge_pkgs).

    std_pkgs -- имена после distro-маппинга, ровно то, что уходит в Packages=
    mkosi, поэтому и exclude применяется к ним, а не к тому, что ввёл
    пользователь: развёрнутое linux-firmware даёт три разных имени, и
    недоступным под архитектуру может оказаться только одно из них.
    """
    requested = list(recipe.packages) if recipe.packages else [
        "systemd", "systemd-sysv", "dbus", "iproute2"
    ]

    pkgs = list(requested)
    for req_pkg in _REQUIRED_PACKAGES:
        if req_pkg not in pkgs:
            pkgs.append(req_pkg)

    if not any(_KERNEL_PREFIX in p.lower() for p in pkgs):
        pkgs.append(kernel_package(recipe.distribution, recipe.architecture))

    edge_pkgs = [p for p in pkgs if p.lower().startswith("edge-")]
    for always in ALWAYS_EDGE_PACKAGES:
        if always not in edge_pkgs:
            edge_pkgs.append(always)

    std_pkgs = [p for p in pkgs if not p.lower().startswith("edge-")]
    if "dracut-core" not in std_pkgs:
        std_pkgs.append("dracut-core")

    pkg_map = package_map(recipe.distribution)
    mapped: List[str] = []
    for p in std_pkgs:
        mapped_val = pkg_map.get(p.lower(), p)
        if not mapped_val:
            continue
        for name in mapped_val.split():
            if name not in mapped:
                mapped.append(name)

    std_pkgs = [p for p in mapped if p not in exclude]
    edge_pkgs = [p for p in edge_pkgs if p not in exclude]
    return std_pkgs, edge_pkgs
