"""
initramfs generation during a build.

It used to run three times -- the kernel's postinst, a second dpkg trigger and
our own explicit pass -- at 32-37 seconds each, more than 40% of the build in
total. mkinitramfs is almost entirely single-threaded, which is why the host
showed ~4% load across 24 cores at that point: exactly one was busy.
"""
import os
import sys
import types

from conftest import make_recipe

if "models" not in sys.modules:
    stub = types.ModuleType("models")
    stub.Recipe = object
    stub.RecipeAsset = object
    stub.Build = object
    sys.modules["models"] = stub

from core.packages import resolve_package_list  # noqa: E402
from core.workspace import populate_extra_tree  # noqa: E402


def _recipe(**over):
    base = dict(
        distribution="debian", release="bookworm", architecture="amd64", board="generic",
        hostname="edge", hostname_from_netif=False, timezone="UTC", locale="C.UTF-8",
        network_config=None, ssh_keys=[], ssh_port=2222, users=[], partitions=[],
        root_password=None, raw_postinst=None, raw_firstboot=None, kernel_params=None,
        raw_preseed_cfg=None, raw_mkosi_conf=None, is_dev=False, output_formats=["raw_xz"],
        ssh_password_auth=True, ssh_permit_root_login=False,
    )
    base.update(over)
    return make_recipe(**base)


def test_zstd_is_installed_so_compression_is_not_single_threaded():
    """
    initramfs.conf asks for COMPRESS=zstd, but without the binary mkinitramfs
    silently falls back to single-threaded gzip. With zstd present it builds the
    command as "zstd -q -1 -T0", i.e. it compresses on every core.
    """
    std, _ = resolve_package_list(_recipe())
    assert "zstd" in std

    std_arm, _ = resolve_package_list(
        _recipe(distribution="armbian", release="noble", architecture="arm64", board="opi5-plus")
    )
    assert "zstd" in std_arm


def test_package_installs_do_not_regenerate_initramfs(tmp_path):
    """
    The file has to live in mkosi.skeleton: that tree is copied BEFORE packages
    are installed, otherwise the kernel's postinst gets to build an initramfs
    before the ban is even in place.
    """
    ws = str(tmp_path)
    populate_extra_tree(_recipe(), [], ws)

    conf = os.path.join(ws, "mkosi.skeleton", "etc", "initramfs-tools", "update-initramfs.conf")
    assert os.path.exists(conf)
    assert "update_initramfs=no" in open(conf).read()


def test_the_ban_never_reaches_the_finished_image(tmp_path):
    """
    Were the ban to stay in the image, the board would stop rebuilding the
    initramfs on kernel upgrades and would one day boot an outdated one.
    """
    ws = str(tmp_path)
    populate_extra_tree(_recipe(), [], ws)
    postinst = open(os.path.join(ws, "mkosi.postinst")).read()

    assert "rm -f /etc/initramfs-tools/update-initramfs.conf" in postinst
    # Lifting the ban must not depend on whether a kernel was found.
    removal = postinst.index("rm -f /etc/initramfs-tools/update-initramfs.conf")
    guard = postinst.index('if [ -n "$KVER" ] && command -v update-initramfs')
    assert removal < guard, "the ban must be lifted before any checks"


def test_initramfs_is_regenerated_exactly_once(tmp_path):
    ws = str(tmp_path)
    populate_extra_tree(_recipe(), [], ws)
    postinst = open(os.path.join(ws, "mkosi.postinst")).read()
    assert postinst.count("update-initramfs -u -k") == 1


def test_armbian_skips_the_virtio_iso_module_pass(tmp_path):
    """
    virtio_blk/virtio_net/... are modules for a QEMU/VirtualBox guest,
    isofs/sr_mod/cdrom are for booting from an ISO. RK3588 is bare metal with no
    ISO mode (it boots through extlinux, see test_armbian.py), so a second
    update-initramfs pass for those modules buys Armbian nothing but an extra
    ~27s on every build.
    """
    ws = str(tmp_path)
    populate_extra_tree(
        _recipe(distribution="armbian", release="noble", architecture="arm64", board="opi5-plus"),
        [], ws,
    )
    postinst = open(os.path.join(ws, "mkosi.postinst")).read()
    assert "Adding virtio + ISO boot modules" not in postinst
    assert postinst.count("update-initramfs -u -k") == 0


def test_amd64_keeps_the_virtio_iso_module_pass(tmp_path):
    """amd64 can still boot from an ISO installer or live as a QEMU guest."""
    ws = str(tmp_path)
    populate_extra_tree(_recipe(), [], ws)
    postinst = open(os.path.join(ws, "mkosi.postinst")).read()
    assert "Adding virtio + ISO boot modules" in postinst
