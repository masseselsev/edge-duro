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

# Armbian публикует репозиторий и под Debian-, и под Ubuntu-суиты; по release
# определяется, какой userland лежит в основе.
_UBUNTU_SUITES = frozenset({"noble", "jammy"})

# Имена сверены с живым индексом apt.armbian.com (dists/*/main/binary-arm64).
# Ветка vendor -- ядро Rockchip BSP 6.1.x: под RK3588 оно поддерживает
# периферию полнее, чем mainline-ветка current.
_ARMBIAN_DEFAULT_KERNEL = "linux-image-vendor-rk35xx"

ARMBIAN_KERNEL_PACKAGES: Dict[str, str] = {
    "opi5-plus": "linux-image-vendor-rk35xx",
}

# DTB обязан идти из той же ветки, что и ядро, иначе плата не поднимется.
ARMBIAN_BOARD_PACKAGES: Dict[str, Tuple[str, ...]] = {
    "opi5-plus": ("linux-dtb-vendor-rk35xx", "linux-u-boot-orangepi5-plus-vendor"),
}

# U-Boot грузит ядро по extlinux.conf и берёт из него device tree платы. Путь
# указывается относительно каталога DTB конкретного ядра.
ARMBIAN_BOARD_DTB: Dict[str, str] = {
    "opi5-plus": "rockchip/rk3588-orangepi-5-plus.dtb",
}

ARMBIAN_REPO_URL = "http://apt.armbian.com"


def board_dtb(board: Any) -> str:
    return ARMBIAN_BOARD_DTB.get((board or "").lower(), "")


def armbian_source_line(release: Any) -> str:
    """
    Строка sources.list для репозитория Armbian.

    Нужна в двух деревьях сразу: mkosi.skeleton читает apt во время сборки,
    mkosi.extra уезжает в готовый образ. Пропуск skeleton уже приводил к
    "Unable to locate package linux-image-vendor-rk35xx" -- проверка индекса
    пакеты находила, а apt внутри mkosi о репозитории не знал.
    """
    return f"deb [trusted=yes] {ARMBIAN_REPO_URL} {release or 'noble'} main"

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


def was_deliberately_skipped(name: str, missing_packages) -> bool:
    """
    Пропущен ли пакет предполётной проверкой намеренно.

    Отличает "под эту архитектуру сборки нет, и мы согласились собирать без
    него" от "должен был встать и не встал". Записи с reason="dependency"
    добавляет разбор ошибок apt уже после падения сборки -- это отказ, а не
    осознанный пропуск.
    """
    for entry in (missing_packages or []):
        if entry.get("name") == name and entry.get("reason") in ("not_in_index", "critical"):
            return True
    return False


def architecture_for_distribution(distribution: Any) -> str:
    """
    Архитектура следует из дистрибутива, отдельно её не выбирают: Armbian мы
    собираем только под arm64-платы, Debian и Ubuntu -- только под amd64.
    """
    return "arm64" if is_armbian(distribution) else "amd64"


def is_armbian(distribution: Any) -> bool:
    return (distribution or "").lower() == "armbian"


def base_distribution(distribution: Any, release: Any = None) -> str:
    """
    Дистрибутив, который получит mkosi.

    Armbian -- это не самостоятельный дистрибутив, а слой ядра, U-Boot и
    firmware поверх Debian или Ubuntu (mkosi про armbian не знает вовсе), и
    репозиторий apt.armbian.com публикуется под оба userland сразу. Базу
    выбирает release, поэтому отдельного поля под неё не нужно.
    """
    if not is_armbian(distribution):
        return (distribution or "debian").lower()
    return "ubuntu" if (release or "").lower() in _UBUNTU_SUITES else "debian"


def distro_family(distribution: Any, release: Any = None) -> str:
    distro = base_distribution(distribution, release)
    if "ubuntu" in distro:
        return "ubuntu"
    if "debian" in distro:
        return "debian"
    return distro


def package_map(distribution: Any, release: Any = None) -> Dict[str, str]:
    family = distro_family(distribution, release)
    if family == "ubuntu":
        return _UBUNTU_PKG_MAP
    if family == "debian":
        return _DEBIAN_PKG_MAP
    return {}


def kernel_package(distribution: Any, architecture: Any, release: Any = None,
                   board: Any = None) -> str:
    """
    Ubuntu собирает linux-image-generic под обе архитектуры, у Debian имя
    несёт архитектуру в себе -- на arm64 linux-image-amd64 просто не существует.
    Ядро для RK3588 приезжает из Armbian и называется по семейству SoC.
    """
    if is_armbian(distribution):
        return ARMBIAN_KERNEL_PACKAGES.get(board_key(board), _ARMBIAN_DEFAULT_KERNEL)
    if distro_family(distribution, release) == "ubuntu":
        return "linux-image-generic"
    arch = (architecture or "amd64").lower()
    return "linux-image-arm64" if arch in ("arm64", "aarch64") else "linux-image-amd64"


def board_key(board: Any) -> str:
    return (board or "generic").lower()


def board_packages(distribution: Any, board: Any) -> List[str]:
    """
    Платозависимые пакеты сверх ядра: DTB и U-Boot конкретной платы.

    U-Boot нужен в образе не для загрузки с него, а как источник
    idbloader.img/u-boot.itb: firstboot пишет их в SPI, чтобы плата грузилась
    с NVMe (см. core/rk3588.py).
    """
    if not is_armbian(distribution):
        return []
    return list(ARMBIAN_BOARD_PACKAGES.get(board_key(board), ()))


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
        # RK3588 грузится через U-Boot, EFI-раздела в этой цепочке нет, поэтому
        # systemd-boot встал бы в образ загрузчиком, который никогда не запустят.
        if is_armbian(recipe.distribution) and req_pkg == "systemd-boot":
            continue
        if req_pkg not in pkgs:
            pkgs.append(req_pkg)

    release = getattr(recipe, "release", None)
    board = getattr(recipe, "board", None)

    if not any(_KERNEL_PREFIX in p.lower() for p in pkgs):
        pkgs.append(kernel_package(recipe.distribution, recipe.architecture, release, board))

    for board_pkg in board_packages(recipe.distribution, board):
        if board_pkg not in pkgs:
            pkgs.append(board_pkg)

    edge_pkgs = [p for p in pkgs if p.lower().startswith("edge-")]
    for always in ALWAYS_EDGE_PACKAGES:
        if always not in edge_pkgs:
            edge_pkgs.append(always)

    std_pkgs = [p for p in pkgs if not p.lower().startswith("edge-")]
    if "dracut-core" not in std_pkgs:
        std_pkgs.append("dracut-core")

    pkg_map = package_map(recipe.distribution, release)
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
