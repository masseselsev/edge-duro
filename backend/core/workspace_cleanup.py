"""
Отбор каталогов, которые уборка вправе удалить.

Вынесено из задачи celery, чтобы правило можно было проверить тестом без
файловой системы и без базы: цена ошибки здесь -- rmtree по чужому каталогу.
"""
from typing import Iterable, List, Set

# Служебные каталоги рядом с воркспейсами сборок. Перечислены явно для
# читаемости; проверка на числовое имя ниже и так их защищает.
INFRASTRUCTURE_DIRS = frozenset({
    "outputs",     # готовые артефакты
    "cache",       # кеш образов mkosi, кеш индексов APT, кеш .deb-пакетов Edge
    "pkgcache",    # постоянный кеш пакетов дистрибутива
    "mkosi_work",  # WorkspaceDirectory самого mkosi
})


def orphaned_workspaces(entries: Iterable[str], active_ids: Set[str]) -> List[str]:
    """
    Возвращает имена каталогов сборок, чьего рецепта больше нет.

    Каталог сборки называется идентификатором рецепта, поэтому удаляются только
    целиком числовые имена. Раньше уборка сносила всё, кроме outputs, и каждую
    ночь уносила pkgcache -- то есть отменяла оптимизацию, ради которой этот
    кеш и заводили.
    """
    return [
        name for name in entries
        if name.isdigit() and name not in active_ids and name not in INFRASTRUCTURE_DIRS
    ]
