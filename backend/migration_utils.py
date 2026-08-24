"""
Idempotent wrappers around the Alembic operations used by this project.

Alembic never actually ran here. `entrypoint.sh` calls `alembic upgrade head`
on every backend start, and it died at revision 002 with

    UPDATE alembic_version SET version_num='002_add_kernel_params_and_firstboot'
    value too long for type character varying(32)

because Alembic's own version table caps the identifier at 32 characters and
two of ours were longer. Every database has therefore been sitting at
`001_initial_schema` for the whole life of the project, and the schema has
been kept current by `create_all` plus the safety migration in `main.py`
instead.

Shortening the two identifiers fixes the crash but not the consequence: the
first successful `upgrade head` would then replay 002..013 against databases
that already have every one of those columns and fail on "column already
exists". Guarding each operation on the current state is what makes the
replay a no-op there while a genuinely empty database still gets built from
scratch -- and it keeps working without anyone having to remember to stamp a
particular deployment by hand.
"""

import sqlalchemy as sa
from alembic import op


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return column in {c["name"] for c in _inspector().get_columns(table)}


def _has_index(table: str, index: str) -> bool:
    if not _has_table(table):
        return False
    return index in {i["name"] for i in _inspector().get_indexes(table)}


def add_column_if_missing(table: str, column: sa.Column) -> None:
    if not _has_column(table, column.name):
        op.add_column(table, column)


def drop_column_if_exists(table: str, column: str) -> None:
    if _has_column(table, column):
        op.drop_column(table, column)


def create_table_if_missing(name: str, *columns, **kwargs) -> None:
    if not _has_table(name):
        op.create_table(name, *columns, **kwargs)


def drop_table_if_exists(name: str) -> None:
    if _has_table(name):
        op.drop_table(name)


def create_index_if_missing(name: str, table: str, columns, **kwargs) -> None:
    if not _has_index(table, name):
        op.create_index(name, table, columns, **kwargs)


def drop_index_if_exists(name: str, table: str) -> None:
    if _has_index(table, name):
        op.drop_index(name, table_name=table)
