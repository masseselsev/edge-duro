"""
Уборка воркспейса.

Каталоги сборок называются идентификатором рецепта. Рядом лежат служебные
каталоги (кеш пакетов, кеш образов, рабочая директория mkosi), и удалять их
нельзя: pkgcache добавляли специально, чтобы сборки перестали перекачивать
пакеты, а ночная уборка сводила это на нет.
"""
from core.workspace_cleanup import orphaned_workspaces


def test_removes_workspaces_of_deleted_recipes():
    entries = ["1", "2", "9", "outputs", "pkgcache"]
    assert orphaned_workspaces(entries, active_ids={"1", "2"}) == ["9"]


def test_keeps_workspaces_of_existing_recipes():
    assert orphaned_workspaces(["1", "2"], active_ids={"1", "2"}) == []


def test_never_touches_infrastructure_directories():
    entries = ["cache", "pkgcache", "mkosi_work", "outputs", "deb_cache"]
    assert orphaned_workspaces(entries, active_ids=set()) == []


def test_ignores_anything_that_is_not_a_recipe_id():
    """Неизвестный каталог оставляем: угадывать чужое содержимое опаснее."""
    entries = ["notes.txt", "tmp-restore", "42abc"]
    assert orphaned_workspaces(entries, active_ids=set()) == []


def test_numeric_directory_with_no_recipe_is_orphaned():
    assert orphaned_workspaces(["7"], active_ids={"1"}) == ["7"]
