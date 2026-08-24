from conftest import make_recipe
from core.packages import (
    CRITICAL_PACKAGES,
    is_critical,
    kernel_package,
    resolve_package_list,
    was_deliberately_skipped,
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


def test_gpgv_always_present_for_repo_signature_checks():
    """
    Without gpgv, any chroot apt-get against a signed repo fails with "gpgv,
    gpgv2 or gpgv1 required for verification, but neither seems installed" --
    --allow-insecure-repositories does not help, it governs trusting an
    unsigned repo, not the absence of the verifier binary. Caught live: the
    custom-repo apt-get update (wrapped in "|| true") was silently failing on
    every build that configured one.
    """
    std, _ = resolve_package_list(make_recipe())
    assert "gpgv" in std


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


def test_deliberately_skipped_recognises_a_recorded_package():
    missing = [
        {"name": "edge-base", "source": "edge", "reason": "not_in_index"},
        {"name": "intel-microcode", "source": "apt", "reason": "not_in_index"},
    ]
    assert was_deliberately_skipped("edge-base", missing)
    assert was_deliberately_skipped("intel-microcode", missing)


def test_deliberately_skipped_is_false_for_anything_else():
    missing = [{"name": "edge-base", "source": "edge", "reason": "not_in_index"}]
    assert not was_deliberately_skipped("edge-timekeeper", missing)
    assert not was_deliberately_skipped("edge-base", [])
    assert not was_deliberately_skipped("edge-base", None)


def test_a_dependency_failure_does_not_count_as_deliberate():
    """
    Пакет, который apt не смог разрешить уже во время сборки, попадает в тот же
    список, но это отказ, а не осознанный пропуск.
    """
    missing = [{"name": "edge-base", "source": "edge", "reason": "dependency"}]
    assert not was_deliberately_skipped("edge-base", missing)


def test_edge_base_is_not_critical():
    assert not is_critical("edge-base")
    assert is_critical("apt")
    assert is_critical("linux-image-arm64")
    assert "edge-base" not in CRITICAL_PACKAGES
