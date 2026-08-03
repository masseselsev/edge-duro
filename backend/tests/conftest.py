import os
import sys
import types

# Модули core/ импортируются напрямую (backend/ -- корень пакета в рантайме),
# поэтому тот же путь добавляется и для тестов.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def make_recipe(**overrides):
    """Минимальный duck-typed рецепт: core/ читает только атрибуты."""
    base = dict(
        name="test",
        distribution="debian",
        release="bookworm",
        architecture="amd64",
        packages=[],
        repositories=[],
        ignore_missing_arch_packages=False,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)
