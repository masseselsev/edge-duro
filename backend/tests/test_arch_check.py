from conftest import make_recipe
from core import arch_check


INDEX = """Package: nginx-full
Version: 1.22.1-9
Architecture: arm64
Description: web server

Package: exim4-daemon-light
Version: 4.96-17
Provides: mail-transport-agent
Description: MTA

Package: bash
Version: 5.2-15
Description: shell
"""


def test_extract_names_includes_provides():
    names = arch_check.extract_package_names(INDEX)
    assert {"nginx-full", "exim4-daemon-light", "bash"} <= names
    assert "mail-transport-agent" in names


def test_extract_names_handles_multiple_provides():
    names = arch_check.extract_package_names(
        "Package: foo\nProvides: bar, baz (= 1.0)\n"
    )
    assert {"foo", "bar", "baz"} <= names


def test_debian_arch_normalises_aliases():
    assert arch_check.debian_arch("aarch64") == "arm64"
    assert arch_check.debian_arch("x86_64") == "amd64"


def test_official_sources_use_ports_for_ubuntu_arm64():
    sources = arch_check.official_index_sources("ubuntu", "noble", "arm64")
    assert all(url == "http://ports.ubuntu.com/ubuntu-ports" for url, _, _ in sources)
    assert {c for _, _, c in sources} == {"main", "restricted", "universe", "multiverse"}


def test_official_sources_use_archive_for_ubuntu_amd64():
    sources = arch_check.official_index_sources("ubuntu", "noble", "amd64")
    assert all(url == "http://archive.ubuntu.com/ubuntu" for url, _, _ in sources)


def test_official_sources_for_debian():
    sources = arch_check.official_index_sources("debian", "bookworm", "arm64")
    assert all(url == "https://deb.debian.org/debian" for url, _, _ in sources)
    assert {c for _, _, c in sources} == {
        "main", "contrib", "non-free", "non-free-firmware"
    }
    assert {s for _, s, _ in sources} == {"bookworm"}


def _fetch_all(_url, _suite, _component, _arch):
    return INDEX


def _fetch_nothing(_url, _suite, _component, _arch):
    return None


def test_missing_packages_reported_with_source_and_reason():
    recipe = make_recipe(architecture="arm64", packages=["nginx-full", "edge-target-puma"])
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=_fetch_all)

    assert result.checked
    by_name = {m["name"]: m for m in result.missing}
    assert "nginx-full" not in by_name
    assert by_name["edge-target-puma"]["source"] == "edge"
    assert by_name["edge-target-puma"]["reason"] == "not_in_index"
    assert by_name["dracut-core"]["source"] == "apt"


def test_missing_kernel_is_marked_critical():
    recipe = make_recipe(architecture="arm64")
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=_fetch_all)

    kernel = [m for m in result.missing if m["name"] == "linux-image-arm64"]
    assert kernel and kernel[0]["reason"] == "critical"
    assert arch_check.has_critical(result)


def test_edge_base_missing_is_not_critical():
    recipe = make_recipe(architecture="arm64", packages=["bash"])
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=_fetch_all)

    edge_base = [m for m in result.missing if m["name"] == "edge-base"]
    assert edge_base and edge_base[0]["reason"] == "not_in_index"


def test_unreachable_index_disables_the_whole_check():
    recipe = make_recipe(architecture="arm64", packages=["nginx-full"])
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=_fetch_nothing)

    assert not result.checked
    assert result.missing == []
    assert result.unreachable


def test_partial_failure_also_disables_the_check():
    def flaky(_url, _suite, component, _arch):
        return INDEX if component == "main" else None

    recipe = make_recipe(architecture="arm64", packages=["nginx-full"])
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=flaky)

    assert not result.checked
    assert result.missing == []


def test_second_check_is_served_from_the_disk_cache():
    calls = {"n": 0}

    def counting(_url, _suite, _component, _arch):
        calls["n"] += 1
        return INDEX

    recipe = make_recipe(architecture="arm64", packages=["nginx-full"])
    arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=counting)
    first_round = calls["n"]
    assert first_round > 0

    arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=counting)
    assert calls["n"] == first_round


def test_recipe_repositories_are_checked_too():
    seen = []

    def spy(url, suite, component, arch):
        seen.append((url, suite, component, arch))
        return INDEX

    recipe = make_recipe(
        architecture="arm64",
        repositories=[{"url": "https://edge.example/repo/bookworm/stable",
                       "suite": "bookworm", "components": "main"}],
    )
    arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=spy)

    assert ("https://edge.example/repo/bookworm/stable", "bookworm", "main", "arm64") in seen
