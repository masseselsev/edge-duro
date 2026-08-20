"""
SSH access in the built image.

With no explicit directives the image lived on the distribution's defaults, and
on Debian and Ubuntu PermitRootLogin defaults to prohibit-password -- so the
root password set in the recipe silently did not work over SSH. Keys, meanwhile,
went to root only, so with root login closed the board could not be reached by
key either.
"""
import os
import sys
import types

from conftest import make_recipe

if "models" not in sys.modules:
    stub = types.ModuleType("models")
    stub.Recipe = object
    stub.RecipeAsset = object
    stub.Build = object
    sys.modules["models"] = stub

from core.packages import resolve_package_list  # noqa: E402
from core.workspace import populate_extra_tree  # noqa: E402

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIexamplekeybody edge@fleet"


def _recipe(**over):
    base = dict(
        distribution="debian", release="bookworm", architecture="amd64", board="generic",
        hostname="edge", hostname_from_netif=False, timezone="UTC", locale="C.UTF-8",
        network_config=None, ssh_keys=[], ssh_port=2222, users=[], partitions=[],
        root_password=None, raw_postinst=None, raw_firstboot=None, kernel_params=None,
        raw_preseed_cfg=None, raw_mkosi_conf=None, is_dev=False, output_formats=["raw_xz"],
        ssh_password_auth=True, ssh_permit_root_login=False,
    )
    base.update(over)
    return make_recipe(**base)


def _sshd_conf(ws):
    return open(os.path.join(ws, "mkosi.extra", "etc", "ssh", "sshd_config.d", "edge.conf")).read()


def test_defaults_keep_password_login_but_not_for_root(tmp_path):
    ws = str(tmp_path)
    populate_extra_tree(_recipe(), [], ws)
    conf = _sshd_conf(ws)

    assert "Port 2222" in conf
    # Refusing passwords by default would make a keyless image unreachable.
    assert "PasswordAuthentication yes" in conf
    # Root login by key nevertheless stays possible.
    assert "PermitRootLogin prohibit-password" in conf


def test_password_login_can_be_switched_off(tmp_path):
    ws = str(tmp_path)
    populate_extra_tree(_recipe(ssh_password_auth=False), [], ws)
    assert "PasswordAuthentication no" in _sshd_conf(ws)


def test_root_password_login_can_be_allowed(tmp_path):
    ws = str(tmp_path)
    populate_extra_tree(_recipe(ssh_permit_root_login=True), [], ws)
    assert "PermitRootLogin yes" in _sshd_conf(ws)


def test_stale_port_conf_is_removed(tmp_path):
    """
    The workspace is reused: a file from an earlier version would stay in the
    image and override Port -- sshd reads sshd_config.d in alphabetical order.
    """
    ws = str(tmp_path)
    sshd_dir = os.path.join(ws, "mkosi.extra", "etc", "ssh", "sshd_config.d")
    os.makedirs(sshd_dir, exist_ok=True)
    with open(os.path.join(sshd_dir, "port.conf"), "w") as f:
        f.write("Port 22\n")

    populate_extra_tree(_recipe(), [], ws)
    assert not os.path.exists(os.path.join(sshd_dir, "port.conf"))


def test_keys_reach_regular_accounts_not_only_root(tmp_path):
    """
    Root password login is closed by default, so the expected way in is a
    regular user account -- the keys have to reach it too.
    """
    ws = str(tmp_path)
    populate_extra_tree(
        _recipe(ssh_keys=[KEY], users=[{"username": "operator", "password": "x", "groups": ["sudo"]}]),
        [], ws,
    )

    root_keys = os.path.join(ws, "mkosi.extra", "root", ".ssh", "authorized_keys")
    assert KEY in open(root_keys).read()

    # The home directory is created by useradd in postinst, so the key is
    # installed from there rather than from mkosi.extra -- otherwise it would
    # land owned by the wrong user.
    postinst = open(os.path.join(ws, "mkosi.postinst")).read()
    assert "getent passwd operator" in postinst
    assert "authorized_keys" in postinst
    assert "chown -R operator:" in postinst


def test_no_key_block_when_recipe_has_no_keys(tmp_path):
    ws = str(tmp_path)
    populate_extra_tree(_recipe(users=[{"username": "operator", "password": "x"}]), [], ws)
    postinst = open(os.path.join(ws, "mkosi.postinst")).read()
    assert "getent passwd operator" not in postinst


def test_openssh_server_is_always_installed():
    """
    sshd_config.d/edge.conf and authorized_keys ship regardless of the recipe's
    packages -- with an empty packages=[] (as ARM64 recipes have) the build
    produced configuration for a daemon the image did not contain: the board
    brought up the network while the port answered "connection refused".
    """
    std, _ = resolve_package_list(_recipe(packages=[]))
    assert "openssh-server" in std

    std_arm, _ = resolve_package_list(
        _recipe(distribution="armbian", release="noble", architecture="arm64",
                board="opi5-plus", packages=[])
    )
    assert "openssh-server" in std_arm
