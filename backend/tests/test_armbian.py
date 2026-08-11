from conftest import make_recipe
from core.netnames import rename_script
from core.packages import (
    architecture_for_distribution,
    base_distribution,
    board_packages,
    distro_family,
    is_armbian,
    kernel_package,
    package_map,
    resolve_package_list,
)
from core.rk3588 import provision_script


def test_architecture_follows_the_distribution():
    # Архитектуру не выбирают руками: Armbian существует только под платы.
    assert architecture_for_distribution("armbian") == "arm64"
    assert architecture_for_distribution("debian") == "amd64"
    assert architecture_for_distribution("ubuntu") == "amd64"
    assert architecture_for_distribution(None) == "amd64"


def test_armbian_base_follows_the_release():
    # mkosi про armbian не знает, вниз должен уходить базовый дистрибутив.
    assert base_distribution("armbian", "noble") == "ubuntu"
    assert base_distribution("armbian", "jammy") == "ubuntu"
    assert base_distribution("armbian", "bookworm") == "debian"
    assert base_distribution("armbian", "trixie") == "debian"
    assert base_distribution("debian", "bookworm") == "debian"


def test_armbian_uses_the_base_distros_package_map():
    assert distro_family("armbian", "noble") == "ubuntu"
    assert package_map("armbian", "noble") == package_map("ubuntu")
    assert package_map("armbian", "bookworm") == package_map("debian")


def test_is_armbian_recognises_only_armbian():
    assert is_armbian("armbian")
    assert is_armbian("Armbian")
    assert not is_armbian("debian")
    assert not is_armbian(None)


def test_rk3588_kernel_comes_from_armbian():
    # В самих Debian/Ubuntu ядра под RK3588 нет.
    assert kernel_package("armbian", "arm64", "noble", "opi5-plus") == "linux-image-vendor-rk35xx"


def test_board_packages_carry_dtb_and_uboot():
    pkgs = board_packages("armbian", "opi5-plus")
    assert "linux-dtb-vendor-rk35xx" in pkgs
    assert "linux-u-boot-orangepi5-plus-vendor" in pkgs


def test_board_packages_are_empty_off_armbian():
    assert board_packages("debian", "opi5-plus") == []
    assert board_packages("armbian", "generic") == []


def test_opi5_recipe_resolves_kernel_dtb_and_uboot():
    std, _ = resolve_package_list(
        make_recipe(distribution="armbian", release="noble", architecture="arm64", board="opi5-plus")
    )
    assert "linux-image-vendor-rk35xx" in std
    assert "linux-dtb-vendor-rk35xx" in std
    assert "linux-u-boot-orangepi5-plus-vendor" in std
    assert "linux-image-generic" not in std


def test_dtb_and_kernel_stay_on_the_same_branch():
    """
    DTB из другой ветки, чем ядро, оставит плату без дерева устройств -- она
    не поднимется. Обе записи обязаны нести один и тот же суффикс ветки.
    """
    std, _ = resolve_package_list(
        make_recipe(distribution="armbian", release="noble", architecture="arm64", board="opi5-plus")
    )
    kernels = [p for p in std if p.startswith("linux-image-")]
    dtbs = [p for p in std if p.startswith("linux-dtb-")]
    assert len(kernels) == 1 and len(dtbs) == 1
    assert kernels[0].removeprefix("linux-image-") == dtbs[0].removeprefix("linux-dtb-")


def test_provision_script_never_touches_the_boot_device():
    """
    Перепутать карту с целью -- значит затереть систему, с которой идёт работа.
    """
    script = provision_script()
    assert "findmnt -no SOURCE /" in script
    assert 'return 0' in script


def test_rk3588_image_carries_no_uefi_bootloader():
    """
    EFI-раздела в цепочке загрузки RK3588 нет, systemd-boot там никогда не
    запустится -- в образе ему делать нечего.
    """
    std, _ = resolve_package_list(
        make_recipe(distribution="armbian", release="noble", architecture="arm64", board="opi5-plus")
    )
    assert "systemd-boot" not in std
    # На amd64 он по-прежнему обязателен.
    std_amd, _ = resolve_package_list(make_recipe())
    assert "systemd-boot" in std_amd


def test_provision_refuses_a_target_smaller_than_the_card():
    # Оборванный на середине dd оставил бы цель незагружаемой.
    script = provision_script()
    assert "blockdev --getsize64" in script
    assert '"$tgt_size" -lt "$src_size"' in script


def test_provision_refuses_when_the_boot_device_is_unknown():
    script = provision_script()
    assert '[ -z "$boot_disk" ]' in script


def test_provision_marker_lives_on_the_target_not_the_card():
    """
    Карта переезжает с платы на плату, поэтому "уже сделано" не может
    храниться на ней -- иначе она отработала бы ровно один раз.
    """
    script = provision_script(marker_path="/var/opt/edge/.done")
    assert '"$mnt$marker"' in script
    assert 'marker="/var/opt/edge/.done"' in script


def test_provision_regenerates_identity_before_first_boot():
    script = provision_script()
    assert "machine-id" in script
    assert "ssh-keygen -A" in script
    assert "ssh_host_" in script


def test_provision_writes_the_loader_via_armbians_own_script():
    # Смещения загрузчика -- забота апстрима; свои копии однажды разойдутся.
    script = provision_script()
    assert "/usr/lib/u-boot/platform_install.sh" in script
    assert "write_uboot_platform_mtd" in script
    assert "/dev/mtdblock0" in script


def test_interface_rename_binds_to_mac_not_kernel_name():
    script = rename_script("edge", 0)
    assert "MACAddress=" in script
    assert "[Link]" in script


def test_interface_numbering_honours_the_start_index():
    assert "idx=0" in rename_script("edge", 0)
    assert "idx=1" in rename_script("edge", 1)
    assert 'prefix="net"' in rename_script("net", 0)


def test_interface_rename_is_idempotent():
    # Второй проход после подключения ещё одного кабеля сдвинул бы номера.
    assert '10-edge-*.link' in rename_script()


def _armbian_recipe(**over):
    base = dict(
        distribution="armbian", release="noble", architecture="arm64", board="opi5-plus",
        hostname="edge", hostname_from_netif=False, timezone="UTC", locale="C.UTF-8",
        network_config=None, ssh_keys=[], ssh_port=2222, users=[], partitions=[],
        root_password=None, raw_postinst=None, raw_firstboot=None, kernel_params=None,
        raw_preseed_cfg=None, raw_mkosi_conf=None, is_dev=False, output_formats=["raw_xz"],
    )
    base.update(over)
    return make_recipe(**base)


def test_armbian_repo_reaches_the_package_manager_sandbox(tmp_path):
    """
    Реальное падение: репозиторий лежал в mkosi.extra и mkosi.skeleton, но apt
    их не читает -- mkosi запускает пакетный менеджер снаружи образа. Пакеты
    находились предполётной проверкой и тут же не находились самим apt
    ("Unable to locate package linux-image-vendor-rk35xx"). Работает только
    mkosi.sandbox.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)

    sandbox = os.path.join(ws, "mkosi.sandbox", "etc", "apt", "sources.list.d", "armbian.list")
    assert os.path.exists(sandbox), "apt при сборке не увидит репозиторий Armbian"
    assert "apt.armbian.com" in open(sandbox).read()

    # В образе он тоже нужен -- ради apt update на самой плате.
    image = os.path.join(ws, "mkosi.extra", "etc", "apt", "sources.list.d", "custom.list")
    assert "apt.armbian.com" in open(image).read()


def test_initramfs_conf_exists_before_packages_are_installed(tmp_path):
    """
    postinst ядра Armbian под `set -e` сразу зовёт update-initramfs, а
    initramfs.conf -- conffile initramfs-tools-core, который dpkg кладёт только
    при конфигурации пакета. Порядок конфигурации у mkosi не гарантирован, и
    сборка падала на "cannot open /etc/initramfs-tools/initramfs.conf".
    Файл обязан лежать в mkosi.skeleton -- он копируется до установки пакетов.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)

    conf = os.path.join(ws, "mkosi.skeleton", "etc", "initramfs-tools", "initramfs.conf")
    assert os.path.exists(conf), "хук ядра не найдёт initramfs.conf и уронит сборку"
    body = open(conf).read()
    assert "MODULES=" in body and "BUSYBOX=" in body


def test_conffile_prompt_cannot_stall_the_build(tmp_path):
    """
    Подложенный initramfs.conf dpkg считает "существующим, но ничьим" и
    спрашивает, чью версию оставить. Stdin в сборке нет, и вопрос валит пакет:
    "end of file on stdin at conffile prompt".
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)

    cfg = os.path.join(ws, "mkosi.sandbox", "etc", "dpkg", "dpkg.cfg.d", "edge-noninteractive")
    assert os.path.exists(cfg), "dpkg спросит про conffile и уронит сборку"
    body = open(cfg).read()
    assert "force-confold" in body and "force-confdef" in body


def test_armbian_artifacts_are_dropped_when_recipe_leaves_armbian(tmp_path):
    """
    Воркспейс переиспользуется между сборками -- файлы от прошлого прогона
    собирали бы Debian-образ с чужим репозиторием и чужими флагами dpkg.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)
    leftovers = [
        os.path.join(ws, "mkosi.sandbox", "etc", "apt", "sources.list.d", "armbian.list"),
        os.path.join(ws, "mkosi.sandbox", "etc", "dpkg", "dpkg.cfg.d", "edge-noninteractive"),
        os.path.join(ws, "mkosi.skeleton", "etc", "initramfs-tools", "initramfs.conf"),
    ]
    assert all(os.path.exists(p) for p in leftovers)

    populate_extra_tree(_armbian_recipe(distribution="debian", release="bookworm"), [], ws)
    for p in leftovers:
        assert not os.path.exists(p), f"{os.path.basename(p)} утёк в не-Armbian сборку"


def test_armbian_checks_indexes_of_its_base_distro():
    """
    Реальное падение: проверка ходила на deb.debian.org за суитом noble,
    которого там нет, получала "индекса нет" по всем компонентам и молча
    отключалась целиком.
    """
    from core.arch_check import official_index_sources

    noble = official_index_sources("armbian", "noble", "arm64")
    assert all("ubuntu" in url for url, _, _ in noble)
    bookworm = official_index_sources("armbian", "bookworm", "arm64")
    assert all("debian" in url for url, _, _ in bookworm)


def test_armbian_repo_is_part_of_the_availability_check():
    """
    Репозиторий Armbian подставляется автоматически и в recipe.repositories не
    лежит -- без него ядро и U-Boot платы считались бы отсутствующими.
    """
    import inspect

    from core import arch_check

    src = inspect.getsource(arch_check.check_recipe_packages)
    assert "is_armbian(recipe.distribution)" in src
    assert "ARMBIAN_REPO_URL" in src


def test_iso_generation_is_never_triggered_for_armbian():
    """
    RK3588 не грузится через UEFI (Bootable=no, ESP нет вовсе). generate_iso.py
    при отсутствии ESP не падает -- он умеет вытащить vmlinuz/initrd из
    корневого раздела через debugfs и всё равно собрать ISO через
    grub-mkrescue (x86_64-efi/BIOS), которым RK3588 попросту не пользуется.
    Получился бы "успешно собранный", но нерабочий на плате ISO, поэтому
    триггер обязан быть выключен для Armbian ещё до вызова generate_iso_task.
    """
    import os

    # Читается из файла, а не импортируется: tasks.build_image тянет модели,
    # и в этом файле есть тест, подсовывающий в sys.modules урезанную заглушку
    # models без Build -- порядок запуска тестов тогда решал бы, пройдёт ли
    # обычный import.
    path = os.path.join(os.path.dirname(__file__), "..", "tasks", "build_image.py")
    with open(path) as f:
        src = f.read()
    assert 'is_armbian(recipe.distribution)' in src
    iso_trigger_idx = src.index('generate_iso_task.delay')
    guard_idx = src.index('is_armbian(recipe.distribution)')
    assert guard_idx < iso_trigger_idx


def test_interface_rename_skips_virtual_devices():
    # lo, bridge и veth не имеют /sys/class/net/*/device.
    assert '/sys/class/net/$iface/device' in rename_script()
