import os
import sys
import types

import pytest

# Модули core/ импортируются напрямую (backend/ -- корень пакета в рантайме),
# поэтому тот же путь добавляется и для тестов.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """
    arch_check кеширует индексы в ${DURO_WORKSPACE_PATH}/cache/apt_index. Без
    подмены пути тесты писали бы в рабочий каталог сборщика и подхватывали
    кеш друг друга -- проверка на недоступный индекс проходила бы по кешу.
    """
    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """
    populate_extra_tree() fetches two files from the internet (the NIC
    firmware and the Armbian repo key). Both fall back gracefully, and the
    fallback is what the suite should exercise by default -- otherwise every
    armbian test would hit the network and behave differently depending on
    whether it succeeded. Tests that care about the fetched path patch
    urlopen themselves.
    """
    import urllib.error

    def refuse(*_a, **_kw):
        raise urllib.error.URLError("network disabled in tests")

    monkeypatch.setattr("core.workspace.urllib.request.urlopen", refuse)


def make_recipe(**overrides):
    """Минимальный duck-typed рецепт: core/ читает только атрибуты."""
    base = dict(
        name="test",
        distribution="debian",
        release="bookworm",
        architecture="amd64",
        board="generic",
        packages=[],
        repositories=[],
        ignore_missing_arch_packages=False,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)
