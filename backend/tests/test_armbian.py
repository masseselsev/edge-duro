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


def test_board_specific_firmware_is_gated_on_the_exact_board(tmp_path, monkeypatch):
    """
    r8169 cannot bring the on-board 2.5GbE NICs up at full capability without
    rtl_nic/rtl8125b-2.fw ("Unable to load firmware", seen live on hardware).
    That fix is specific to the Orange Pi 5 Plus's own silicon and has no
    business running on a different RK3588 board that may not even carry the
    same NIC -- gating on is_armbian() alone would have shipped it everywhere.

    Fetched directly from upstream (a 3 KB file) rather than through apt's
    ~655 MB linux-firmware package -- see _fetch_firmware_file in
    core/workspace.py for why the apt route was abandoned. The real network
    call is replaced here so the test doesn't depend on it succeeding.
    """
    import os
    from unittest.mock import MagicMock, patch

    from core.workspace import populate_extra_tree

    # Isolate the shared fwcache dir so this test never reads (or pollutes)
    # a real cached copy from an actual build.
    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path / "wsroot"))
    fake_firmware = b"\x00\x00\x00\x00fake-firmware-blob"

    def fake_urlopen(req, timeout=15):
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.read.return_value = fake_firmware
        return cm

    with patch("core.workspace.urllib.request.urlopen", side_effect=fake_urlopen):
        ws = str(tmp_path / "opi5")
        os.makedirs(ws, exist_ok=True)
        populate_extra_tree(_armbian_recipe(board="opi5-plus"), [], ws)
        fw_path = os.path.join(ws, "mkosi.extra", "lib", "firmware", "rtl_nic", "rtl8125b-2.fw")
        assert os.path.exists(fw_path)
        with open(fw_path, "rb") as f:
            assert f.read() == fake_firmware

        ws2 = str(tmp_path / "other-board")
        os.makedirs(ws2, exist_ok=True)
        populate_extra_tree(_armbian_recipe(board="nanopc-t6-lts"), [], ws2)
        fw_path2 = os.path.join(ws2, "mkosi.extra", "lib", "firmware", "rtl_nic", "rtl8125b-2.fw")
        assert not os.path.exists(fw_path2)


def test_the_boards_displayport_firmware_ships_too(tmp_path, monkeypatch):
    """
    update-initramfs flagged "Possible missing firmware /lib/firmware/rockchip/
    dptx.bin for built-in driver rockchipdrm" on every build. rockchipdrm
    drives the DisplayPort controller behind the board's two USB-C outputs;
    without the blob they stay dark. Same fetch path as the NIC firmware --
    98 KB from upstream instead of the 655 MB linux-firmware package.
    """
    import os
    import urllib.error
    from unittest.mock import MagicMock, patch

    from core.workspace import _FIRMWARE_BASE_URL, populate_extra_tree

    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path / "wsroot"))
    payloads = {
        _FIRMWARE_BASE_URL + "rtl_nic/rtl8125b-2.fw": b"\x00\x00\x00\x00nic",
        _FIRMWARE_BASE_URL + "rockchip/dptx.bin": b"\x10\x80\x01\x00dp",
    }

    def fake_urlopen(req, timeout=30):
        # populate_extra_tree also fetches the Armbian repo key; only the
        # firmware URLs are of interest here, the rest may fail.
        if req.full_url not in payloads:
            raise urllib.error.URLError("not served in this test")
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.read.return_value = payloads[req.full_url]
        return cm

    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)
    with patch("core.workspace.urllib.request.urlopen", side_effect=fake_urlopen):
        populate_extra_tree(_armbian_recipe(board="opi5-plus"), [], ws)

    dp = os.path.join(ws, "mkosi.extra", "lib", "firmware", "rockchip", "dptx.bin")
    assert os.path.exists(dp)
    with open(dp, "rb") as f:
        assert f.read() == payloads[_FIRMWARE_BASE_URL + "rockchip/dptx.bin"]

    # And in the skeleton tree, which is what update-initramfs can actually
    # see: the kernel package builds the initrd during its own configuration,
    # long before mkosi copies the extra trees in.
    skel = os.path.join(ws, "mkosi.skeleton", "usr", "lib", "firmware", "rockchip", "dptx.bin")
    assert os.path.exists(skel)


def test_a_firmware_file_with_the_wrong_magic_is_discarded(tmp_path, monkeypatch):
    """
    A mirror or captive portal answering 200 with an HTML page would otherwise
    be written to /lib/firmware under the driver's own filename, and the board
    would fail to load it with no clue why. Each entry carries the first bytes
    of the genuine file for exactly this check.
    """
    import os
    from unittest.mock import MagicMock, patch

    from core.workspace import _FIRMWARE_BASE_URL, _fetch_board_firmware

    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path / "wsroot"))
    ws = str(tmp_path / "ws")

    def fake_urlopen(req, timeout=30):
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.read.return_value = b"<!DOCTYPE html><title>404</title>"
        return cm

    with patch("core.workspace.urllib.request.urlopen", side_effect=fake_urlopen):
        _fetch_board_firmware(ws, "opi5-plus")

    extra = os.path.join(ws, "mkosi.extra", "lib", "firmware")
    skel = os.path.join(ws, "mkosi.skeleton", "usr", "lib", "firmware")
    assert not os.path.exists(os.path.join(extra, "rtl_nic", "rtl8125b-2.fw"))
    assert not os.path.exists(os.path.join(extra, "rockchip", "dptx.bin"))
    assert not os.path.exists(os.path.join(skel, "rockchip", "dptx.bin"))
    assert _FIRMWARE_BASE_URL.startswith("https://")


def test_etc_hosts_is_written_at_build_time(tmp_path):
    """
    A minimal mkosi image ships no /etc/hosts at all -- that convention comes
    from debian-installer, not from the base packages. Without it, nothing
    resolves the hostname to localhost, and every "sudo" invocation on the
    board prints "unable to resolve host <name>": harmless, but on every
    single command. Caught live on real hardware, not in a test.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(hostname="edge-node"), [], ws)
    hosts = open(os.path.join(ws, "mkosi.extra", "etc", "hosts")).read()
    assert "127.0.0.1\tlocalhost" in hosts
    assert "127.0.1.1\tedge-node" in hosts


def test_live_hostname_rewrite_creates_hosts_if_missing(tmp_path):
    """
    hostname_from_netif overwrites the hostname again at runtime once the
    MAC-derived name is known, and the original code only ever "sed -i"d an
    EXISTING /etc/hosts -- a no-op on an image that ships none, which is the
    normal case (see test_etc_hosts_is_written_at_build_time above).
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(hostname_from_netif=True, network_config=None), [], ws)
    script = open(os.path.join(ws, "mkosi.extra", "opt", "edge", "bin", "firstboot.sh")).read()

    assert "if [ ! -f /etc/hosts ]; then" in script
    assert "printf '127.0.0.1\\tlocalhost\\n127.0.1.1\\t%s\\n' \"$MAC\" > /etc/hosts" in script
    assert "elif grep -q '^127\\.0\\.1\\.1' /etc/hosts" in script
    assert "printf '127.0.1.1\\t%s\\n' \"$MAC\" >> /etc/hosts" in script


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
    # Anchored on the call site rather than on the two calls being adjacent:
    # more steps have since been added between them, and the guarantee under
    # test is the ordering against the completeness check, not the spacing.
    spi_at = script.index("  edge_rk3588_write_spi\n")
    marker_at = script.index('edge_rk3588_individualize "$target"')
    assert check_at < spi_at, "проверка обязана идти до прошивки SPI"
    assert check_at < marker_at, "проверка обязана идти до маркера"


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


def test_last_partition_is_reformatted_not_resized():
    """
    resize2fs cannot grow this far: from a ~32 MiB clone to a ~930 GB disk is
    roughly 29000x, far past what mkfs reserves group-descriptor blocks for.
    On real hardware this produced "Corrupt group descriptor: bad block for
    block bitmap" and a corrupt journal superblock, caught by `e2fsck -fn`
    right after provisioning. The partition is empty at this point (just
    cloned), so mkfs at the final size sidesteps the whole reservation limit.
    """
    script = provision_script()
    assert "mkfs.ext4" in script
    assert '-L "$last_label"' in script

    # The ext4 branch must not also fall through to resize2fs.
    ext4_at = script.index('if [ "$last_fstype" = "ext4" ]; then')
    fallback_at = script.index('else\n      e2fsck -fy "$last_part"')
    assert ext4_at < fallback_at
    assert "resize2fs" not in script[ext4_at:fallback_at]
    assert "resize2fs" in script[fallback_at:]


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


def test_mtd_utils_ships_flashcp_for_spi_writes():
    """
    edge_rk3588_write_spi() (rk3588.py) prefers flashcp over Armbian's own
    dd-based write_uboot_platform_mtd() -- dd through /dev/mtdblock0 was
    timed at 4+ minutes for the 16 MB SPI image on real hardware, flashcp's
    native MTD ioctls at a fraction of that. Without the "mtd-utils" package,
    "command -v flashcp" fails and the code silently falls back to the slow
    path on every build.
    """
    std, _ = resolve_package_list(
        make_recipe(distribution="armbian", release="noble", architecture="arm64",
                    board="opi5-plus", packages=[])
    )
    assert "mtd-utils" in std

    std_other, _ = resolve_package_list(
        make_recipe(distribution="debian", release="bookworm", architecture="amd64",
                    board="generic", packages=[])
    )
    assert "mtd-utils" not in std_other


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


def test_spi_write_prefers_flashcp_but_falls_back_to_armbians_dd():
    """
    flashcp writes through /dev/mtd0's native MTD ioctls instead of Armbian's
    own dd-based write_uboot_platform_mtd() (which goes through the
    block-device compatibility layer at /dev/mtdblock0 and was timed at 4+
    minutes for this 16 MB image on real hardware) -- same bootloader bytes,
    same chip, only the write mechanism differs. write_uboot_platform_mtd()
    must still be reachable as a fallback for whenever flashcp or the image
    file itself is not available, so the board never ends up with no way to
    write SPI at all.
    """
    script = provision_script()
    flashcp_at = script.index("flashcp -v -p")
    fallback_at = script.index('write_uboot_platform_mtd "$DIR" /dev/mtdblock0')
    assert flashcp_at < fallback_at
    assert "command -v flashcp" in script


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


def test_sandbox_trusted_gpg_d_exists_for_the_early_metadata_sync(tmp_path):
    """
    mkosi's "Syncing package manager metadata" step runs apt-get against
    mkosi.sandbox before mkosi.skeleton is even copied in -- a
    mkosi.skeleton copy of this directory (added for mkosi.prepare's own
    later apt-get update) is too late for this specific sync. Without it:
    "W: OpenPGP signature verification failed: ... List of files can't be
    created as '/etc/apt/trusted.gpg.d/' is not a directory", on every build.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)

    assert os.path.isdir(os.path.join(ws, "mkosi.sandbox", "etc", "apt", "trusted.gpg.d"))


def test_prepare_script_mounts_devfs_before_chrooting_for_apt_update(tmp_path):
    """
    Real failure: mkosi.prepare's "chroot $ROOT apt-get update" had no /proc,
    /sys or /dev mounted inside $ROOT first, so /dev/null did not exist in
    the chroot. apt-key (invoked internally by apt-get update against a
    Signed-By: source) then failed with "cannot create /dev/null: Permission
    denied", cascading into "gpgv, gpgv2 or gpgv1 required for verification"
    even with gpgv itself installed. The postinst edge-packages chroot
    already mounts these three before its own chroot calls -- mirror that.

    The /dev bind has to be RECURSIVE. mkosi's sandbox builds the /dev it
    hands to scripts as a tmpfs of empty regular files with the real device
    nodes bind-mounted on top (DevOperation in mkosi/sandbox.py); a plain
    --bind carries only the tmpfs, and a build with it in place still logged
    the exact same "cannot create /dev/null: Permission denied" -- with
    diagnostics confirming $ROOT/dev/null as a 0-byte regular file.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(repositories=[
        {"url": "http://example.invalid/repo", "components": "main"}
    ]), [], ws)
    script = open(os.path.join(ws, "mkosi.prepare")).read()

    chroot_at = script.index('chroot "$ROOT" apt-get update')
    before = script[:chroot_at]
    assert 'mount -t proc proc "$ROOT/proc"' in before
    assert 'mount -t sysfs sys "$ROOT/sys"' in before
    assert 'mount --rbind /dev "$ROOT/dev"' in before
    assert 'mount --bind /dev "$ROOT/dev"' not in script


def test_every_dev_mount_into_a_chroot_is_recursive():
    """
    The postinst chroots mount /dev the same way and for the same reason as
    mkosi.prepare does; a non-recursive bind there leaves them with the same
    dead /dev/null, only without any log line to show for it (their mounts
    are wrapped in "2>/dev/null || true").
    """
    import re

    import core.workspace

    source = open(core.workspace.__file__).read()
    assert 'mount --bind /dev' not in source
    assert len(re.findall(r'mount --rbind /dev "\$ROOT/dev"', source)) == 3


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


_FAKE_ARMBIAN_KEY = b"-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nZmFrZQ==\n-----END PGP PUBLIC KEY BLOCK-----\n"


def _urlopen_serving(payloads):
    """urlopen stub returning payloads[url]; anything else raises."""
    from unittest.mock import MagicMock

    import urllib.error

    def fake(req, timeout=15):
        url = getattr(req, "full_url", req)
        if url not in payloads:
            raise urllib.error.URLError(f"unexpected url {url}")
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.read.return_value = payloads[url]
        return cm

    return fake


def test_armbian_repo_key_is_shipped_so_apt_can_verify_the_index(tmp_path, monkeypatch):
    """
    apt.armbian.com signs its indices, but no keyring was ever shipped, so
    every apt that saw the repo -- mkosi's own sandbox one, the build chroot's
    and the one left on the board -- logged "The signatures couldn't be
    verified because no keyring is specified" and only carried on because the
    source said [trusted=yes]. With the key present the source can name it and
    the index is actually verified.
    """
    import os
    from unittest.mock import patch

    from core.workspace import _ARMBIAN_KEY_URL, populate_extra_tree

    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path / "wsroot"))
    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)

    with patch("core.workspace.urllib.request.urlopen",
               side_effect=_urlopen_serving({_ARMBIAN_KEY_URL: _FAKE_ARMBIAN_KEY})):
        populate_extra_tree(_armbian_recipe(), [], ws)

    # mkosi.sandbox is what mkosi's own apt reads, mkosi.skeleton what the
    # build chroot reads, mkosi.extra what ends up on the board.
    for tree in ("mkosi.sandbox", "mkosi.skeleton", "mkosi.extra"):
        key = os.path.join(ws, tree, "etc", "apt", "trusted.gpg.d", "armbian.asc")
        assert os.path.exists(key), tree
        with open(key, "rb") as f:
            assert f.read() == _FAKE_ARMBIAN_KEY

    sandbox_list = open(os.path.join(
        ws, "mkosi.sandbox", "etc", "apt", "sources.list.d", "armbian.list")).read()
    assert "signed-by=/etc/apt/trusted.gpg.d/armbian.asc" in sandbox_list
    assert "trusted=yes" not in sandbox_list


def test_armbian_source_stays_trusted_when_the_key_cannot_be_fetched(tmp_path):
    """
    The key is fetched over the network at build time. A repo that apt refuses
    to touch at all is worse than one it trusts blindly, so a failed fetch has
    to fall back to [trusted=yes] rather than break the build. The autouse
    no_network fixture makes the fetch fail here.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)

    assert not os.path.exists(os.path.join(
        ws, "mkosi.sandbox", "etc", "apt", "trusted.gpg.d", "armbian.asc"))
    sandbox_list = open(os.path.join(
        ws, "mkosi.sandbox", "etc", "apt", "sources.list.d", "armbian.list")).read()
    assert "trusted=yes" in sandbox_list


def test_a_key_download_that_is_not_a_pgp_key_is_discarded(tmp_path, monkeypatch):
    """
    Same trap as the firmware fetch: a mirror or captive portal answering 200
    with an HTML error page would otherwise be written out as the repo key,
    and apt would reject the repo outright on the finished board.
    """
    import os
    from unittest.mock import patch

    from core.workspace import _ARMBIAN_KEY_URL, install_armbian_key

    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path / "wsroot"))
    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)

    with patch("core.workspace.urllib.request.urlopen",
               side_effect=_urlopen_serving({_ARMBIAN_KEY_URL: b"<html>404</html>"})):
        assert install_armbian_key(ws) is False

    assert not os.path.exists(os.path.join(
        ws, "mkosi.extra", "etc", "apt", "trusted.gpg.d", "armbian.asc"))


def test_moving_a_recipe_off_armbian_drops_the_repo_key(tmp_path, monkeypatch):
    """
    Workspaces are reused between builds. The stale-file cleanup already
    covers the sources list and the dpkg flags; the key has to go with them,
    or a plain Debian image keeps carrying Armbian's signing key.
    """
    import os
    from unittest.mock import patch

    from core.workspace import _ARMBIAN_KEY_URL, populate_extra_tree

    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path / "wsroot"))
    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)

    with patch("core.workspace.urllib.request.urlopen",
               side_effect=_urlopen_serving({_ARMBIAN_KEY_URL: _FAKE_ARMBIAN_KEY})):
        populate_extra_tree(_armbian_recipe(), [], ws)

    populate_extra_tree(_armbian_recipe(distribution="debian", release="bookworm"), [], ws)

    for tree in ("mkosi.sandbox", "mkosi.skeleton", "mkosi.extra"):
        assert not os.path.exists(os.path.join(
            ws, tree, "etc", "apt", "trusted.gpg.d", "armbian.asc")), tree


def test_recipe_repositories_reach_the_package_manager_sandbox(tmp_path):
    """
    Same class of bug the Armbian repo already hit: a repository added in the
    recipe UI was written to mkosi.skeleton and mkosi.extra only, so the build
    chroot and the finished image knew about it but mkosi's own apt -- the one
    that actually installs the recipe's packages, run outside the image --
    never did. A package that exists only in a custom repo could not install.

    The Armbian source itself stays out of this file: it has its own
    armbian.list in the same directory, and apt warns when a target is
    configured twice.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(repositories=[
        {"url": "http://example.invalid/repo", "suite": "noble", "components": "main"}
    ]), [], ws)

    sandbox_custom = os.path.join(
        ws, "mkosi.sandbox", "etc", "apt", "sources.list.d", "custom.list")
    assert os.path.exists(sandbox_custom)
    content = open(sandbox_custom).read()
    assert "http://example.invalid/repo noble main" in content
    assert "apt.armbian.com" not in content


def test_a_recipe_without_repositories_leaves_no_sandbox_sources(tmp_path):
    """The workspace is reused: a list written by an earlier build must go."""
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(repositories=[
        {"url": "http://example.invalid/repo", "components": "main"}
    ]), [], ws)
    populate_extra_tree(_armbian_recipe(repositories=[]), [], ws)

    assert not os.path.exists(os.path.join(
        ws, "mkosi.sandbox", "etc", "apt", "sources.list.d", "custom.list"))


def test_retargeting_a_workspace_drops_the_previous_boards_firmware(tmp_path, monkeypatch):
    """
    Workspaces are reused between builds. Without a sweep, an image retargeted
    at another board -- or moved off armbian entirely -- keeps shipping blobs
    for silicon it does not have, and nothing in the build says so.
    """
    import os
    from unittest.mock import MagicMock, patch

    from core.workspace import _FIRMWARE_BASE_URL, _fetch_board_firmware

    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path / "wsroot"))
    ws = str(tmp_path / "ws")
    payloads = {
        _FIRMWARE_BASE_URL + "rtl_nic/rtl8125b-2.fw": b"\x00\x00\x00\x00nic",
        _FIRMWARE_BASE_URL + "rockchip/dptx.bin": b"\x10\x80\x01\x00dp",
    }

    def fake_urlopen(req, timeout=30):
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.read.return_value = payloads[req.full_url]
        return cm

    with patch("core.workspace.urllib.request.urlopen", side_effect=fake_urlopen):
        _fetch_board_firmware(ws, "opi5-plus")

    nic = os.path.join(ws, "mkosi.extra", "lib", "firmware", "rtl_nic", "rtl8125b-2.fw")
    assert os.path.exists(nic)

    # Same workspace, no longer an armbian recipe.
    _fetch_board_firmware(ws, "")
    assert not os.path.exists(nic)
    assert not os.path.exists(os.path.join(
        ws, "mkosi.skeleton", "usr", "lib", "firmware", "rockchip", "dptx.bin"))


def test_armbian_boots_by_partuuid_not_by_label(tmp_path):
    """
    dd copies the label, the filesystem UUID and the PARTUUID alike, so after
    provisioning the card and the NVMe answer to LABEL=edgeroot identically
    (verified on hardware -- all three matched). The kernel then took whichever
    blkid returned first, and a freshly written test card silently booted the
    installed system. The image therefore names a PARTUUID nothing else on the
    board carries.
    """
    import os

    from core.workspace import IMAGE_ROOT_PARTUUID, populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(_armbian_recipe(), [], ws)
    postinst = open(os.path.join(ws, "mkosi.postinst")).read()

    assert f"root=PARTUUID={IMAGE_ROOT_PARTUUID}" in postinst
    assert "root=LABEL=edgeroot" not in postinst


def test_amd64_images_keep_booting_by_label(tmp_path):
    """
    Only the armbian flow clones its boot medium onto another disk, so only it
    has two filesystems answering to the same label. Leaving the amd64 loader
    entry alone keeps the change off a path this could not be tested on.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    populate_extra_tree(
        _armbian_recipe(distribution="debian", release="bookworm", architecture="amd64"), [], ws)
    postinst = open(os.path.join(ws, "mkosi.postinst")).read()

    assert "root=LABEL=edgeroot" in postinst
    assert "root=PARTUUID=" not in postinst


def test_provisioning_gives_the_clone_its_own_partuuid():
    """
    The image's fixed PARTUUID only distinguishes the media while they differ,
    and the clone starts life as a byte copy of the card. Provisioning has to
    re-stamp it and repoint the clone's own loader entry, or the installed
    system would look for a root that exists only on the card it came from.
    """
    script = provision_script()

    assert "edge_rk3588_reidentify" in script
    assert "sfdisk --part-uuid" in script
    assert "/proc/sys/kernel/random/uuid" in script
    assert "root=PARTUUID=$new_uuid" in script

    # Ordering: re-stamping has to happen before the marker is written, or a
    # crash in between would leave a clone advertised as provisioned while
    # still carrying the card's identity.
    assert script.index("edge_rk3588_reidentify \"$target\"") < script.index("edge_rk3588_individualize \"$target\"")

    # Labels stay: the platform on the installed system addresses its
    # filesystems by them.
    assert "e2label" not in script
    assert "fatlabel" not in script


def test_growfs_never_ships_on_armbian(tmp_path):
    """
    Real corruption, caught on hardware: mkosi.extra is never wiped between
    builds, so an edge-growfs unit written by an earlier non-armbian run of the
    same workspace kept shipping. growfs.sh targets the boot disk -- which on
    this board is the card -- and "sfdisk --relocate gpt-bak-std" rewrote the
    card's GPT header to point at the end of the physical card while leaving
    the partition entry array where it was. Linux discards a table whose
    checksum does not match, so the card came up with no partitions at all.
    """
    import os

    from core.workspace import populate_extra_tree

    ws = str(tmp_path)
    systemd_dir = os.path.join(ws, "mkosi.extra", "etc", "systemd", "system")
    wants_dir = os.path.join(systemd_dir, "multi-user.target.wants")
    os.makedirs(wants_dir, exist_ok=True)

    # Leftovers exactly as a previous build of this workspace would have left.
    stale_unit = os.path.join(systemd_dir, "edge-growfs.service")
    with open(stale_unit, "w") as f:
        f.write("[Unit]\nDescription=stale\n")
    os.symlink("/etc/systemd/system/edge-growfs.service",
               os.path.join(wants_dir, "edge-growfs.service"))

    populate_extra_tree(_armbian_recipe(), [], ws)

    assert not os.path.exists(stale_unit)
    assert not os.path.islink(os.path.join(wants_dir, "edge-growfs.service"))
    assert not os.path.exists(os.path.join(ws, "mkosi.extra", "opt", "edge", "bin", "growfs.sh"))


def test_wait_online_releases_on_the_first_link():
    """
    systemd-networkd-wait-online waits for every managed link by default. With
    only one of the board's two NICs patched it sat in "activating" until its
    120 s timeout, holding network-online.target down -- and edge-firstboot is
    ordered after that target, so hostname, interface naming and the NVMe clone
    all waited two minutes for a network none of them use. Measured on hardware.
    """
    import os

    from core.workspace import populate_extra_tree

    import tempfile
    with tempfile.TemporaryDirectory() as ws:
        populate_extra_tree(_armbian_recipe(), [], ws)
        drop_in = os.path.join(
            ws, "mkosi.extra", "etc", "systemd", "system",
            "systemd-networkd-wait-online.service.d", "10-edge-any-interface.conf")
        assert os.path.exists(drop_in)
        content = open(drop_in).read()
        # The reset line is mandatory: without an empty ExecStart= first,
        # systemd appends and the original all-interfaces wait still runs.
        assert "ExecStart=\n" in content
        assert "--any" in content


def test_gpt_entry_array_is_mirrored_where_card_writers_look_for_it(tmp_path):
    """
    Real corruption, measured on a card written by Raspberry Pi Imager and
    never booted from: the writer relocates the backup GPT onto the physical
    card and in the same pass moves PartitionEntryLBA from 2 to
    FirstUsableLBA - 32, recomputing the header checksum but leaving the 16 KB
    array behind. The stored entry-array CRC then describes bytes nobody wrote
    -- U-Boot reported the checksum of 16384 zeroes -- and Linux discarded the
    table, so the card enumerated no partitions at all.
    """
    import struct

    from core.rk3588 import mirror_gpt_entry_array

    sector = 512
    first_usable = 2048
    count, size = 128, 128
    array_bytes = count * size
    sectors = array_bytes // sector

    img = tmp_path / "disk.raw"
    with open(img, "wb") as f:
        f.write(b"\0" * (sector * 4096))

    header = bytearray(92)
    header[0:8] = b"EFI PART"
    struct.pack_into("<Q", header, 40, first_usable)
    struct.pack_into("<Q", header, 72, 2)
    struct.pack_into("<I", header, 80, count)
    struct.pack_into("<I", header, 84, size)

    array = bytes(range(256)) * (array_bytes // 256)
    with open(img, "r+b") as f:
        f.seek(sector)
        f.write(header)
        f.seek(2 * sector)
        f.write(array)

    assert mirror_gpt_entry_array(str(img), log=lambda *_: None) is True

    mirror_lba = first_usable - sectors
    with open(img, "rb") as f:
        f.seek(mirror_lba * sector)
        assert f.read(array_bytes) == array
        # The header must be left exactly as it was: a writer that does not
        # relocate anything has to see the image it was handed.
        f.seek(sector)
        assert struct.unpack_from("<Q", f.read(92), 72)[0] == 2


def test_mirroring_refuses_to_overwrite_occupied_space(tmp_path):
    """
    The mirror lands in the gap between the bootloader and the first partition.
    On RK3588 that gap also holds idbloader (from sector 64), so anything but
    untouched zeroes there means the layout is not what this assumed -- and
    writing would break the boot chain rather than fix the table.
    """
    import struct

    from core.rk3588 import mirror_gpt_entry_array

    sector = 512
    first_usable = 2048
    count, size = 128, 128
    array_bytes = count * size

    img = tmp_path / "disk.raw"
    with open(img, "wb") as f:
        f.write(b"\0" * (sector * 4096))

    header = bytearray(92)
    header[0:8] = b"EFI PART"
    struct.pack_into("<Q", header, 40, first_usable)
    struct.pack_into("<Q", header, 72, 2)
    struct.pack_into("<I", header, 80, count)
    struct.pack_into("<I", header, 84, size)

    with open(img, "r+b") as f:
        f.seek(sector)
        f.write(header)
        f.seek(2 * sector)
        f.write(b"\xab" * array_bytes)
        # Something already occupies the destination.
        f.seek((first_usable - array_bytes // sector) * sector)
        f.write(b"\x01")

    assert mirror_gpt_entry_array(str(img), log=lambda *_: None) is False


def test_mirroring_is_a_noop_without_a_gpt(tmp_path):
    from core.rk3588 import mirror_gpt_entry_array

    img = tmp_path / "empty.raw"
    with open(img, "wb") as f:
        f.write(b"\0" * (512 * 64))
    assert mirror_gpt_entry_array(str(img), log=lambda *_: None) is False
