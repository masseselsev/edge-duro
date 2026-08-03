from conftest import make_recipe
from core import apt_index, arch_check


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


def test_absent_index_reports_its_packages_instead_of_disabling_the_check():
    """
    Репозиторий Edge отдаёт 404 на binary-arm64, пока arm64-пакетов нет. Это
    достоверный ответ "сборок под эту архитектуру нет", а не сбой сети, и
    проверка обязана продолжиться и назвать эти пакеты.
    """
    def fetch(url, _suite, _component, _arch):
        return arch_check.INDEX_ABSENT if "edge.example" in url else INDEX

    recipe = make_recipe(
        architecture="arm64",
        packages=["nginx-full", "edge-target-puma"],
        repositories=[{"url": "https://edge.example/repo/bookworm/stable",
                       "suite": "bookworm", "components": "main"}],
    )
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=fetch)

    assert result.checked
    assert result.unreachable == []
    names = {m["name"] for m in result.missing}
    assert "edge-target-puma" in names
    assert "edge-base" in names
    assert "nginx-full" not in names


def test_absent_repo_is_reported_so_it_can_be_kept_out_of_the_image():
    """
    Репозиторий без binary-arm64 не должен попасть в sources.list.d образа:
    на устройстве apt update ловил бы 404 вечно.
    """
    def fetch(url, _suite, _component, _arch):
        return arch_check.INDEX_ABSENT if "edge.example" in url else INDEX

    recipe = make_recipe(
        architecture="arm64",
        repositories=[
            {"url": "https://edge.example/repo/bookworm/stable",
             "suite": "bookworm", "components": "main"},
            {"url": "https://other.example/repo",
             "suite": "bookworm", "components": "main"},
        ],
    )
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=fetch)

    assert result.absent_repos == ["https://edge.example/repo/bookworm/stable"]


def test_official_mirror_is_never_listed_as_an_absent_repo():
    """Зеркало дистрибутива в sources.list.d рецепта не пишется вовсе."""
    def fetch(url, _suite, component, _arch):
        return INDEX if component == "main" else arch_check.INDEX_ABSENT

    recipe = make_recipe(architecture="arm64")
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=fetch)

    assert result.absent_repos == []


def test_a_repo_is_kept_when_any_component_has_an_index():
    def fetch(_url, _suite, component, _arch):
        return INDEX if component == "main" else arch_check.INDEX_ABSENT

    recipe = make_recipe(
        architecture="arm64",
        repositories=[{"url": "https://edge.example/repo", "suite": "bookworm",
                       "components": "main contrib"}],
    )
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=fetch)

    assert result.absent_repos == []


def test_skipped_check_reports_no_absent_repos():
    """При отменённой проверке ничего вырезать из образа нельзя."""
    recipe = make_recipe(
        architecture="arm64",
        repositories=[{"url": "https://edge.example/repo", "suite": "bookworm",
                       "components": "main"}],
    )
    result = arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=_fetch_nothing)

    assert not result.checked
    assert result.absent_repos == []


def test_all_official_indices_absent_disables_the_check():
    """
    Официальное зеркало без единого индекса значит, что мы спрашиваем не то
    (опечатка в release), а не что в Debian не осталось пакетов. Объявлять
    отсутствующим весь список нельзя.
    """
    recipe = make_recipe(architecture="arm64", packages=["nginx-full"])
    result = arch_check.check_recipe_packages(
        recipe, log=lambda _m: None,
        fetch=lambda *_a: arch_check.INDEX_ABSENT,
    )

    assert not result.checked
    assert result.missing == []


def test_fetch_maps_404_to_absent(monkeypatch):
    monkeypatch.setattr(apt_index, "http_get", lambda url, timeout=30: (404, None))
    assert arch_check.fetch_index_text("https://x/repo", "bookworm", "main", "arm64") is arch_check.INDEX_ABSENT


def test_fetch_maps_network_failure_to_unknown(monkeypatch):
    monkeypatch.setattr(apt_index, "http_get", lambda url, timeout=30: (None, None))
    assert arch_check.fetch_index_text("https://x/repo", "bookworm", "main", "arm64") is None


def test_fetch_treats_a_mix_of_404_and_network_failure_as_unknown(monkeypatch):
    def flaky(url, timeout=30):
        return (404, None) if url.endswith(".gz") else (None, None)

    monkeypatch.setattr(apt_index, "http_get", flaky)
    assert arch_check.fetch_index_text("https://x/repo", "bookworm", "main", "arm64") is None


def test_absent_index_is_not_cached(monkeypatch):
    """Кеш на сутки заморозил бы 404 и после того, как arm64-пакеты выйдут."""
    calls = {"n": 0}

    def counting(*_a):
        calls["n"] += 1
        return arch_check.INDEX_ABSENT

    recipe = make_recipe(
        architecture="arm64",
        packages=["nginx-full"],
        repositories=[{"url": "https://edge.example/repo/bookworm/stable",
                       "suite": "bookworm", "components": "main"}],
    )

    def fetch(url, suite, component, arch):
        return arch_check.INDEX_ABSENT if "edge.example" in url else INDEX

    arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=fetch)
    seen = []

    def spy(url, suite, component, arch):
        seen.append(url)
        return arch_check.INDEX_ABSENT if "edge.example" in url else INDEX

    arch_check.check_recipe_packages(recipe, log=lambda _m: None, fetch=spy)
    assert any("edge.example" in u for u in seen), "absent index must be re-fetched, not served from cache"


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
