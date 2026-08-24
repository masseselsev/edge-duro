"""
Guards on the Alembic revision chain.

Alembic never actually ran in this project. entrypoint.sh calls
"alembic upgrade head" on every backend start, and it died at revision 002
with "value too long for type character varying(32)" -- Alembic's own version
table caps the identifier at 32 characters and two of ours were longer. Every
database sat at the initial revision for the life of the project while the
schema was kept current by create_all plus the safety migration in main.py.
Nothing failed loudly, so nothing got fixed.
"""
import os
import re

VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")

# alembic_version.version_num is VARCHAR(32) and Alembic does not widen it.
MAX_REVISION_LENGTH = 32


def _revisions():
    out = {}
    for name in sorted(os.listdir(VERSIONS_DIR)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        src = open(os.path.join(VERSIONS_DIR, name)).read()
        rev = re.search(r"^revision(?:\s*:\s*str)?\s*=\s*['\"]([^'\"]+)['\"]", src, re.M)
        down = re.search(r"^down_revision[^=]*=\s*(?:['\"]([^'\"]+)['\"]|None)", src, re.M)
        assert rev, f"{name} declares no revision"
        out[rev.group(1)] = (name, down.group(1) if down and down.group(1) else None, src)
    return out


def test_revision_identifiers_fit_the_version_table():
    for rev, (name, _down, _src) in _revisions().items():
        assert len(rev) <= MAX_REVISION_LENGTH, (
            f"{name}: revision id '{rev}' is {len(rev)} characters; "
            f"alembic_version.version_num holds {MAX_REVISION_LENGTH}, so "
            f"'alembic upgrade head' fails the moment it tries to record it"
        )


def test_revision_chain_is_linear_and_complete():
    revs = _revisions()
    roots = [r for r, (_n, down, _s) in revs.items() if down is None]
    assert len(roots) == 1, f"expected exactly one root revision, got {roots}"

    for rev, (name, down, _src) in revs.items():
        if down is not None:
            assert down in revs, f"{name}: down_revision '{down}' does not exist"

    # Exactly one head: every revision except the last is somebody's parent.
    parents = {down for _n, down, _s in revs.values() if down}
    heads = [r for r in revs if r not in parents]
    assert len(heads) == 1, f"expected exactly one head, got {heads}"


def test_schema_changes_go_through_the_idempotent_helpers():
    """
    The first successful "upgrade head" replays the whole chain against
    databases that already carry every one of those columns. Raw op.add_column
    there fails on "column already exists" and puts the upgrade right back
    where it was, so the operations have to be state-checked.
    """
    raw = []
    for rev, (name, _down, src) in _revisions().items():
        for op in ("op.add_column(", "op.create_table(", "op.create_index(",
                   "op.drop_column(", "op.drop_table(", "op.drop_index("):
            if op in src:
                raw.append(f"{name}: {op}")
    assert not raw, (
        "these migrations call Alembic operations directly instead of the "
        f"guarded helpers in migration_utils: {raw}"
    )
