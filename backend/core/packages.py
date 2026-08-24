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
# "zstd" is not here for the format itself: initramfs.conf asks for
# COMPRESS=zstd, but without the binary mkinitramfs silently falls back to gzip
# ("W: No zstd in ..., using gzip"), and its gzip is single-threaded. With zstd
# installed the command is built as "zstd -q -1 -T0", i.e. initramfs
# compression runs on every core -- this is the longest single-threaded stage
# of a build. It also makes the initrd faster to unpack on the board itself.
# "openssh-server" -- workspace.py writes /etc/ssh/sshd_config.d/edge.conf and
# lays out authorized_keys regardless of the recipe's package list, but without
# the package itself that is configuration for a daemon the image does not
# carry: the board brings up the network and the port (2222 by default) sits
# there answering "connection refused". Same class of bug as described for
# "sudo" above -- just a different package.
# "fdisk" -- provides sfdisk/cfdisk. On Debian util-linux still pulls them in,
# but as of Ubuntu 24.04 they live in a package of their own; the provisioning
# script (rk3588.py) and growfs (workspace.py) both call
# "sfdisk -N ... --force" to extend the last partition after the move to NVMe.
# Without the package the command fails silently ("command not found" under
# "|| true") -- the partition never grows, while neither the build nor the
# provisioning run reports anything wrong.
# "gpgv" -- apt needs it to verify a repo's Release signature. Without it, any
# chroot apt-get against a signed repo (custom repositories, and previously
# the now-removed linux-firmware fetch) fails with "gpgv, gpgv2 or gpgv1
# required for verification, but neither seems installed" regardless of
# --allow-insecure-repositories -- that flag governs trusting an unsigned
# repo, not the absence of the verifier binary itself. Caught live in a
# build log: the custom-repo apt-get update wrapped in "|| true" was silently
# failing on every build that used one.
# "ca-certificates" -- without the CA bundle, apt inside the rootfs cannot
# fetch anything over HTTPS. apt.armbian.com redirects to an HTTPS mirror, so
# the chroot's apt-get update ended every build with "No system certificates
# available. Try installing ca-certificates" followed by "Certificate
# verification failed: The certificate is NOT trusted", i.e. the Armbian index
# was never actually read inside the image -- neither at build time nor on the
# board afterwards, which quietly cuts the device off from kernel updates.
_REQUIRED_PACKAGES = (
    "apt", "bash", "coreutils", "login", "sudo",
    "systemd-boot", "systemd-sysv", "initramfs-tools", "zstd", "openssh-server",
    "fdisk", "gpgv", "ca-certificates",
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

# Отладочный UART у каждой платы свой -- RK3588 слушает ttyS2 на 1.5 Мбод,
# а не стандартные ttyS0/115200. Без этого серийная консоль ядра молчит даже
# когда U-Boot успешно передаёт ему управление.
ARMBIAN_BOARD_CONSOLE: Dict[str, str] = {
    "opi5-plus": "ttyS2,1500000",
}

ARMBIAN_REPO_URL = "http://apt.armbian.com"


def board_dtb(board: Any) -> str:
    return ARMBIAN_BOARD_DTB.get((board or "").lower(), "")


def board_console(board: Any) -> str:
    return ARMBIAN_BOARD_CONSOLE.get((board or "").lower(), "ttyS0,115200")


# Where the Armbian repo signing key is dropped inside every tree that carries
# the sources.list line. apt reads armoured keys from trusted.gpg.d directly,
# so no gpg --dearmor step is involved.
ARMBIAN_KEYRING_PATH = "/etc/apt/trusted.gpg.d/armbian.asc"


def armbian_source_line(release: Any, signed_by: str = "") -> str:
    """
    sources.list line for the Armbian repository.

    Needed in two trees at once: mkosi.skeleton is what apt reads during the
    build, mkosi.extra is what ends up in the finished image. Skipping skeleton
    used to produce "Unable to locate package linux-image-vendor-rk35xx" -- the
    index check found the packages, but apt inside mkosi knew no such repo.

    With signed_by set, apt verifies the repo against that key. Without it the
    source falls back to [trusted=yes]: the key is fetched over the network at
    build time, and a repo that cannot be reached at all is worse than one that
    is trusted blindly, so a failed fetch must not break the build.
    """
    options = f"signed-by={signed_by}" if signed_by else "trusted=yes"
    return f"deb [{options}] {ARMBIAN_REPO_URL} {release or 'noble'} main"

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

    # "mtd-utils" -- provides flashcp, used by edge_rk3588_write_spi() in
    # rk3588.py to write the SPI bootloader through the raw MTD device.
    # Armbian's own platform_install.sh writes rkspi_loader.img via plain dd
    # to /dev/mtdblock0 (the block-device compatibility layer), which was
    # timed at 4+ minutes for a 16 MB image on real hardware; flashcp uses
    # the native MEMERASE/MEMWRITE ioctls instead and is dramatically
    # faster. Every current and planned armbian board targets RK3588, which
    # always carries SPI-NOR, so this is armbian-wide rather than per-board.
    if is_armbian(recipe.distribution) and "mtd-utils" not in pkgs:
        pkgs.append("mtd-utils")

    # "wireless-regdb" -- the regulatory database cfg80211 loads to know which
    # channels and transmit powers are legal in the configured country. The
    # driver is built into the Armbian vendor kernel, so update-initramfs
    # reported "Possible missing firmware /lib/firmware/regulatory.db for
    # built-in driver cfg80211" on every build. The package is a few kilobytes
    # of Architecture: all data; without it any wireless adapter plugged into
    # the board falls back to the most restrictive world-roaming profile.
    if is_armbian(recipe.distribution) and "wireless-regdb" not in pkgs:
        pkgs.append("wireless-regdb")

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
