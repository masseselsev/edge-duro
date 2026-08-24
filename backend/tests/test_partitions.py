"""
Разметка разделов, которую получает systemd-repart.

Размер root задавался полом (SizeMinBytes=8G), поэтому распакованный .raw весил
~10 ГБ независимо от того, что реально попало в образ, и ровно столько же потом
ехало по dd на NVMe при провижининге.
"""
import os
import sys
import types

from conftest import make_recipe

# prepare_workspace импортирует models ради аннотации типа; в тестах БД не нужна.
if "models" not in sys.modules:
    stub = types.ModuleType("models")
    stub.Recipe = object
    stub.RecipeAsset = object
    stub.Build = object
    sys.modules["models"] = stub

from core.workspace import prepare_workspace  # noqa: E402


def _repart_confs(recipe_id, recipe):
    ws = prepare_workspace(recipe_id, recipe)
    repart_dir = os.path.join(ws, "mkosi.repart")
    out = {}
    for name in os.listdir(repart_dir):
        out[name] = open(os.path.join(repart_dir, name)).read()
    return out


def _conf_for(confs, label):
    for body in confs.values():
        if f"Label={label}" in body:
            return body
    raise AssertionError(f"нет конфига с Label={label}: {sorted(confs)}")


def test_root_is_minimized_under_a_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path))
    confs = _repart_confs(1, make_recipe(partitions=[]))

    root = _conf_for(confs, "edgeroot")
    assert "Minimize=guess" in root, "repart не ужмёт root под фактическое содержимое"
    assert "SizeMaxBytes=2G" in root
    assert "SizeMinBytes" not in root, "пол размера возвращает балласт в образ"


def test_other_partitions_keep_a_guaranteed_floor(tmp_path, monkeypatch):
    """
    Потолок вместо пола осмыслен только для root: /boot не может стать меньше
    файлов загрузчика, а размерами edgelog/edgestor управляет сам рецепт.
    """
    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path))
    confs = _repart_confs(2, make_recipe(partitions=[]))

    boot = _conf_for(confs, "edgeboot")
    assert "SizeMinBytes=512M" in boot
    assert "SizeMaxBytes" not in boot
    assert "Minimize" not in boot

    log = _conf_for(confs, "edgelog")
    assert "SizeMinBytes=1G" in log
    assert "Minimize" not in log


def test_recipe_size_for_root_is_honoured_as_a_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path))
    confs = _repart_confs(3, make_recipe(partitions=[
        {"mountpoint": "/", "size": "6G", "filesystem": "ext4", "type": "root", "label": "edgeroot"},
    ]))

    root = _conf_for(confs, "edgeroot")
    assert "SizeMaxBytes=6G" in root
    assert "SizeMinBytes" not in root


def test_unbounded_root_is_still_minimized(tmp_path, monkeypatch):
    """size=max снимает потолок, но ужимать раздел всё равно нужно."""
    monkeypatch.setenv("DURO_WORKSPACE_PATH", str(tmp_path))
    confs = _repart_confs(4, make_recipe(partitions=[
        {"mountpoint": "/", "size": "max", "filesystem": "ext4", "type": "root", "label": "edgeroot"},
    ]))

    root = _conf_for(confs, "edgeroot")
    assert "Minimize=guess" in root
    assert "SizeMaxBytes" not in root


def test_extra_partition_mountpoints_exist_in_the_rootfs():
    """
    A generic partition is filled with CopyFiles=<mountpoint>, and the same
    path is where fstab mounts it on the running board. Nothing else in the
    build creates those directories: for a recipe whose packages never touch
    /var/opt/edge, repart logged "Failed to open source file
    '/buildroot/var/opt/edge', skipping" and the image shipped without the
    mount point at all.
    """
    recipe = make_recipe(distribution="debian", release="bookworm", partitions=[])
    ws = prepare_workspace(9101, recipe)

    for mountpoint in ("var/log/edge", "var/opt/edge"):
        assert os.path.isdir(os.path.join(ws, "mkosi.extra", mountpoint)), mountpoint

    # The root partition copies "/" wholesale -- it must not get a directory
    # of its own carved out under mkosi.extra.
    assert not os.path.exists(os.path.join(ws, "mkosi.extra", "mkosi.extra"))
