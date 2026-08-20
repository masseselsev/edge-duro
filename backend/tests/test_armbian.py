from conftest import make_recipe
from core.netnames import rename_script
from core.packages import (
    architecture_for_distribution,
    base_distribution,
    board_console,
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


def test_board_console_overrides_the_generic_default():
    # RK3588 слушает ttyS2 на 1.5 Мбод -- на ttyS0/115200 серийная консоль
    # ядра молчит даже когда U-Boot успешно передаёт ему управление.
    assert board_console("opi5-plus") == "ttyS2,1500000"
    assert board_console("generic") == "ttyS0,115200"
    assert board_console(None) == "ttyS0,115200"


def test_extlinux_append_carries_the_boards_console(tmp_path):
    """
    Живой захват serial-консоли показал: до этой правки extlinux.conf нёс
    ttyS0,115200 для любой платы, включая opi5-plus, поэтому вывод ядра
    никогда не доходил до отладочного UART платы.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)

    postinst = open(os.path.join(ws, "mkosi.postinst")).read()
    assert "console=ttyS2,1500000" in postinst
    assert "console=ttyS0,115200" not in postinst


def test_provision_refuses_a_target_smaller_than_the_data():
    # Оборванный на середине dd оставил бы цель незагружаемой. Сравнивается
    # именно объём данных, а не физический размер карты: NVMe меньше карты, но
    # больше занятых разделов -- это рабочий случай, а не отказ.
    script = provision_script()
    assert "blockdev --getsize64" in script
    assert '"$tgt_size" -lt "$payload_bytes"' in script


def test_provision_copies_only_up_to_the_last_partition():
    """
    Карта переезжает с платы на плату и бывает в разы больше занятых разделов.
    Посекторная копия целиком гнала бы её полный объём на каждую плату и падала
    бы на NVMe меньшего размера, хотя данные туда заведомо влезают.
    """
    script = provision_script()
    assert "partx -g -o END" in script
    assert "count=$(( (payload_bytes + 4194303) / 4194304 ))" in script


def test_provision_is_not_killed_mid_clone(tmp_path):
    """
    Реальный отказ: со штатным DefaultTimeoutStartSec (90 с) systemd убивал
    firstboot посреди dd. На NVMe уезжала таблица разделов и первые разделы,
    корень оставался пустым, SPI не прошивался -- ядро падало в initramfs с
    "LABEL=edgeroot does not exist".
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)
    unit = open(os.path.join(ws, "mkosi.extra", "etc", "systemd", "system", "edge-firstboot.service")).read()
    assert "TimeoutStartSec=30min" in unit


def test_incomplete_clone_does_not_look_provisioned():
    """
    Прошить SPI и поставить маркер по недокопированной цели -- значит выдать
    полурабочую плату за готовую и не повторить попытку на следующей загрузке.
    """
    script = provision_script()
    check_at = script.index("blkid -t LABEL=edgeroot")
    spi_at = script.index("edge_rk3588_write_spi\n  edge_rk3588_individualize")
    assert check_at < spi_at, "проверка обязана идти до прошивки SPI и маркера"


def test_target_is_reprovisioned_even_when_already_written():
    """
    На этапе отладки цель перезаписывается каждый раз, когда виден NVMe:
    иначе проверка нового образа требовала бы ручной зачистки диска.
    """
    script = provision_script()
    assert "is already provisioned" not in script


def test_completion_is_signalled_on_the_led():
    """
    Красный светодиод припаян к линии питания и ничего не значит. Ровное
    мигание зелёного -- единственный признак успеха, видимый без serial.
    """
    script = provision_script()
    assert "edge_rk3588_led_done" in script
    assert "/sys/class/leds" in script
    # Имя каталога зависит от device tree, жёсткое имя сломалось бы на другом ядре.
    assert "delay_on" in script and "delay_off" in script

    led_at = script.index("  edge_rk3588_led_done\n")
    done_at = script.index("[PROVISION] Done.")
    assert led_at < done_at


def test_result_is_announced_on_the_active_console():
    """
    Светодиод виден, только если на плату смотрят. Тот же результат словами
    должен попасть на активную консоль и остаться над приглашением логина.
    """
    script = provision_script()
    assert "/dev/tty1" in script and "/dev/console" in script
    assert "/etc/issue" in script
    # Строка переписывается, а не копится: провижининг повторяется каждую загрузку.
    assert "sed -i '/^\\[EDGE\\]/d' /etc/issue" in script
    # Отказ обязан быть виден так же, как успех.
    assert "NVMe provisioning FAILED" in script
    assert "NVMe provisioned OK" in script


def test_provision_rebuilds_the_backup_gpt_on_the_target():
    """
    Копия обрывается на конце последнего раздела, а резервный заголовок GPT
    лежал в конце карты -- на цели его нет вовсе, пока он не построен заново.
    """
    script = provision_script()
    assert "sfdisk --relocate gpt-bak-std" in script


def test_provision_grows_without_cloud_guest_utils():
    """
    growpart lives in cloud-guest-utils, which is not in the image's package
    list -- calling it silently failed to grow anything. resize2fs comes with
    the base install (e2fsprogs); for sfdisk see
    test_fdisk_package_ships_sfdisk_for_growfs below -- on Ubuntu 24.04 it is
    not part of util-linux by default.
    """
    script = provision_script()
    # The invocation is checked, not the mention: the package name still
    # appears in a comment.
    assert 'growpart "' not in script
    assert "sfdisk -N" in script
    assert "resize2fs" in script


def test_fdisk_package_ships_sfdisk_for_growfs():
    """
    provision_script() and growfs (workspace.py) both call "sfdisk -N ...
    --force" on the last partition after the move to NVMe. On Ubuntu 24.04
    sfdisk is split out of util-linux into a package of its own, "fdisk" --
    without it the command fails silently under "|| true": the partition never
    grows while provisioning reports nothing wrong. That is exactly how it was
    caught on real hardware -- "[PROVISION] WARNING: could not rebuild the
    backup GPT" in the board's log.
    """
    std, _ = resolve_package_list(
        make_recipe(distribution="armbian", release="noble", architecture="arm64",
                    board="opi5-plus", packages=[])
    )
    assert "fdisk" in std


def test_card_partitions_never_grow(tmp_path):
    """
    The copy onto NVMe runs up to the end of the last partition, so a grown card
    would mean a card-sized copy on every next board.

    On armbian only provisioning grows anything -- offline, on a target that is
    not mounted yet. There is no edge-growfs unit here at all: it would redo the
    same work a second time, and its gate (ConditionPathExists on the marker)
    never fired anyway while the marker was written into a shadowed mount-point
    directory.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)
    systemd_dir = os.path.join(ws, "mkosi.extra", "etc", "systemd", "system")

    assert not os.path.exists(os.path.join(systemd_dir, "edge-growfs.service"))
    assert not os.path.exists(
        os.path.join(systemd_dir, "multi-user.target.wants", "edge-growfs.service")
    )

    # Growing has not gone anywhere -- it lives inside provisioning and is
    # aimed at the target.
    script = provision_script()
    assert "sfdisk -N" in script
    assert "resize2fs" in script


def test_provision_marker_is_not_shadowed_by_a_mount(tmp_path):
    """
    The marker used to be written into /var/opt/edge inside the clone's mounted
    root, i.e. into a mount-point directory: on a running system the separate
    edgestor partition is mounted over it and the marker became invisible --
    `cat` on the board returned "No such file or directory" even though the file
    was there in the image.

    The separate partitions are read from the generated fstab rather than from a
    list in the test: add a fourth partition and this check catches it by itself.
    """
    import os

    from core.rk3588 import MARKER_PATH
    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)
    fstab = open(os.path.join(ws, "mkosi.extra", "etc", "fstab")).read()

    separate = [
        parts[1]
        for parts in (line.split() for line in fstab.splitlines())
        if len(parts) >= 2 and parts[0].startswith("LABEL=") and parts[1] != "/"
    ]
    assert separate, "fstab must describe the separate partitions"

    for mountpoint in separate:
        assert not MARKER_PATH.startswith(mountpoint.rstrip("/") + "/"), (
            f"marker {MARKER_PATH} sits on separate partition {mountpoint} "
            f"and will be shadowed by the mount"
        )


def test_growfs_is_unconditional_where_nothing_migrates(tmp_path):
    """Без клонирования расти должен сам загрузочный диск, как и раньше."""
    import os

    from core.rk3588 import MARKER_PATH
    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(distribution="debian", release="bookworm"), [], ws)
    unit = open(os.path.join(ws, "mkosi.extra", "etc", "systemd", "system", "edge-growfs.service")).read()
    assert "Before=edge-firstboot.service" in unit
    assert MARKER_PATH not in unit


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


def test_names_are_applied_live_not_only_through_link_files():
    """
    On-board NICs (r8169 on RK3588) are named by udev while still in the
    initramfs, which never carries /etc/systemd/network/*.link at all, and after
    switch_root udev no longer renames interfaces that already exist. Verified on
    the board: the .link file was there with the correct MAC, `udevadm
    test-builtin net_setup_link` resolved edge0, and the live name stayed
    enP4p65s0. So the name has to be forced by hand.
    """
    script = rename_script()
    assert "ip link set dev" in script
    assert 'name "$want"' in script
    # Only a downed interface can be renamed.
    down_at = script.index('ip link set dev "$cur" down')
    rename_at = script.index('ip link set dev "$cur" name "$want"')
    assert down_at < rename_at, "the interface must be downed before renaming"


def test_live_naming_repeats_even_after_names_are_decided():
    """
    The netnames.done stamp stops only the CHOICE of names. The rename itself
    has to repeat on every boot: the kernel hands its own names back after each
    start, and on the clone (where the stamp is already set) it would otherwise
    never happen at all.
    """
    script = rename_script()
    assert script.rstrip().endswith("edge_apply_live_names")
    # Live application lives outside the function the stamp switches off.
    decide = script.index("edge_rename_interfaces() {")
    apply_fn = script.index("edge_apply_live_names() {")
    assert apply_fn > decide
    assert '[ -e "$stamp" ]' not in script[apply_fn:]


def test_interface_numbering_honours_the_start_index():
    assert "idx=0" in rename_script("edge", 0)
    assert "idx=1" in rename_script("edge", 1)
    assert 'prefix="net"' in rename_script("net", 0)


def test_interface_rename_is_idempotent():
    # Второй проход после подключения ещё одного кабеля сдвинул бы номера.
    # Страж -- именно метка: наличие .link для этого не годится, потому что
    # загрузка без активного порта не пишет их вовсе (см. тест ниже).
    script = rename_script()
    assert '[ -e "$stamp" ] && return 0' in script
    assert 'stamp="/var/lib/edge/netnames.done"' in script


def test_naming_is_deferred_until_a_port_has_a_link():
    """
    Без линка неизвестно, какой интерфейс должен стать первым. Раздача имён по
    алфавиту закрепила бы первое имя за разъёмом, в который никто не включался.
    """
    script = rename_script()
    assert 'if [ -z "$active" ]; then' in script
    # Ни .link, ни метка не пишутся -- проверка обязана повториться позже.
    body = script.split('if [ -z "$active" ]; then', 1)[1].split("fi", 1)[0]
    assert "return 0" in body
    assert "edge_write_link" not in body
    assert "$stamp" not in body


def test_first_name_goes_to_the_port_with_a_link():
    script = rename_script("edge", 1)
    active_at = script.index('edge_write_link "$active" "$prefix$idx"')
    rest_at = script.index('[ "$iface" = "$active" ] && continue')
    assert active_at < rest_at, "активный порт должен получить имя раньше остальных"
    assert "idx=1" in script


def test_hotplug_finishes_deferred_naming(tmp_path):
    """
    firstboot -- oneshot с RemainAfterExit, повторно он не стартует, поэтому
    доигрывать отложенное переименование обязан отдельный юнит.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(network_config={"prefix": "edge", "start_index": 0}), [], ws)

    rule = open(os.path.join(ws, "mkosi.extra", "etc", "udev", "rules.d", "80-edge-netnames.rules")).read()
    assert 'ATTR{carrier}=="1"' in rule
    assert "edge-netnames.service" in rule

    unit = open(os.path.join(ws, "mkosi.extra", "etc", "systemd", "system", "edge-netnames.service")).read()
    assert "RemainAfterExit" not in unit, "юнит должен запускаться повторно на каждый линк"
    assert "ConditionPathExists=!/var/lib/edge/netnames.done" in unit

    script = os.path.join(ws, "mkosi.extra", "opt", "edge", "bin", "netnames.sh")
    assert os.access(script, os.X_OK)
    assert open(script).read().startswith("#!/bin/bash")


def test_addresses_survive_the_rename(tmp_path):
    """
    edge-netconf runs Before=edge-firstboot, i.e. it writes .network files BEFORE
    netnames renames the interface. With [Match] Name=enP4p65s0 the file stopped
    matching after the rename and the interface was left without any address at
    all -- the board fell off the network for good. The MAC never changes.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(network_config={"prefix": "edge", "start_index": 0}), [], ws)
    netconf = open(os.path.join(ws, "mkosi.extra", "opt", "edge", "bin", "edge-netconf.sh")).read()

    assert 'PRIMARY_MATCH="MACAddress=$MAC"' in netconf
    assert 'CAM_MATCH="MACAddress=$CAM_MAC"' in netconf
    # What goes into the .network file is the variable, not the interface name.
    assert "\nName=$PRIMARY\n" not in netconf
    assert "\nName=$n\n" not in netconf


def test_catch_all_network_covers_renamed_interfaces(tmp_path):
    """
    The "en* eth*" glob does not cover edge0. On an image without edge-netconf
    (where .network files are written per MAC) a renamed interface would be left
    with no matching .network at all, and therefore with no address.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(network_config={"prefix": "edge", "start_index": 0}), [], ws)

    net_dir = os.path.join(ws, "mkosi.extra", "etc", "systemd", "network")
    blob = "".join(
        open(os.path.join(net_dir, name)).read()
        for name in os.listdir(net_dir)
        if name.endswith(".network")
    )
    assert "edge*" in blob


def test_card_leaves_no_interface_names_for_the_next_board():
    """
    .link привязаны к MAC той платы, на которой карта отработала. На следующей
    они не совпадут ни с чем, и порты остались бы с именами от ядра.
    """
    script = provision_script()
    assert "rm -f /etc/systemd/network/10-edge-*.link" in script
    assert "rm -f /var/lib/edge/netnames.done" in script


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
