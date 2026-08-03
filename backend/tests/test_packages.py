from conftest import make_recipe
from core.packages import (
    CRITICAL_PACKAGES,
    is_critical,
    kernel_package,
    resolve_package_list,
)


def test_kernel_follows_architecture():
    assert kernel_package("debian", "amd64") == "linux-image-amd64"
    assert kernel_package("debian", "arm64") == "linux-image-arm64"
    assert kernel_package("ubuntu", "arm64") == "linux-image-generic"


def test_arm64_recipe_gets_arm64_kernel():
    std, _ = resolve_package_list(make_recipe(architecture="arm64"))
    assert "linux-image-arm64" in std
    assert "linux-image-amd64" not in std


def test_required_and_dracut_always_present():
    std, _ = resolve_package_list(make_recipe())
    for required in ("apt", "bash", "coreutils", "login", "sudo",
                     "systemd-boot", "systemd-sysv", "initramfs-tools", "dracut-core"):
        assert required in std


def test_edge_packages_split_out_and_core_added():
    std, edge = resolve_package_list(
        make_recipe(packages=["nginx-full", "edge-target-puma"])
    )
    assert "nginx-full" in std
    assert not [p for p in std if p.startswith("edge-")]
    assert set(edge) >= {"edge-base", "edge-python3-core", "edge-target-puma"}


def test_ubuntu_mapping_applied():
    std, _ = resolve_package_list(
        make_recipe(distribution="ubuntu", release="noble", packages=["linux-image-amd64"])
    )
    assert "linux-image-generic" in std
    assert "linux-image-amd64" not in std


def test_debian_firmware_maps_to_several_packages():
    std, _ = resolve_package_list(make_recipe(packages=["linux-firmware"]))
    assert "firmware-misc-nonfree" in std
    assert "intel-microcode" in std
    assert "linux-firmware" not in std


def test_exclude_removes_from_both_lists():
    std, edge = resolve_package_list(
        make_recipe(packages=["nginx-full", "edge-target-puma"]),
        exclude=frozenset({"nginx-full", "edge-target-puma"}),
    )
    assert "nginx-full" not in std
    assert "edge-target-puma" not in edge
    assert "edge-base" in edge


def test_exclude_applies_to_mapped_names():
    # Пользователь пишет linux-firmware, apt видит развёрнутые имена -- отсеивать
    # надо по тому, что видит apt.
    std, _ = resolve_package_list(
        make_recipe(packages=["linux-firmware"]),
        exclude=frozenset({"intel-microcode"}),
    )
    assert "intel-microcode" not in std
    assert "firmware-misc-nonfree" in std


def test_edge_base_is_not_critical():
    assert not is_critical("edge-base")
    assert is_critical("apt")
    assert is_critical("linux-image-arm64")
    assert "edge-base" not in CRITICAL_PACKAGES
