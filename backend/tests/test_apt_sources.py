"""
Запись APT-источников в дерево образа.

Воркспейс переиспользуется между сборками одного рецепта, поэтому недостаточно
"не записать" источник -- файл, оставшийся от прошлого прогона, попадёт в образ.
"""
import os
import sys
import types

from conftest import make_recipe

# mkosi_config импортирует models ради аннотации типа; в тестах БД не нужна.
if "models" not in sys.modules:
    stub = types.ModuleType("models")
    stub.Recipe = object
    sys.modules["models"] = stub

from core.mkosi_config import generate_mkosi_conf  # noqa: E402

EDGE = {"url": "https://edge.example/repo/bookworm/stable",
        "suite": "bookworm", "components": "main"}


def _custom_list(ws):
    return os.path.join(ws, "mkosi.extra", "etc", "apt", "sources.list.d", "custom.list")


def test_repository_is_written_into_the_image(tmp_path):
    ws = str(tmp_path)
    generate_mkosi_conf(make_recipe(repositories=[EDGE], kernel_params=None,
                                    raw_mkosi_conf=None), ws)

    assert "edge.example" in open(_custom_list(ws)).read()


def test_skipped_repository_is_not_written(tmp_path):
    ws = str(tmp_path)
    generate_mkosi_conf(make_recipe(repositories=[EDGE], kernel_params=None,
                                    raw_mkosi_conf=None),
                        ws, skip_repo_urls=frozenset({EDGE["url"]}))

    assert not os.path.exists(_custom_list(ws))


def test_stale_source_from_an_earlier_build_is_removed(tmp_path):
    """Регрессия: фильтрация без удаления оставляла файл от прошлой сборки."""
    ws = str(tmp_path)
    recipe = make_recipe(repositories=[EDGE], kernel_params=None, raw_mkosi_conf=None)

    generate_mkosi_conf(recipe, ws)
    assert os.path.exists(_custom_list(ws))

    generate_mkosi_conf(recipe, ws, skip_repo_urls=frozenset({EDGE["url"]}))
    assert not os.path.exists(_custom_list(ws)), "stale custom.list leaked into the image"
