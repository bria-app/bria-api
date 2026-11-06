"""SQL helpers that run the same on Postgres (production) and SQLite (local stack, tests).

Postgres keeps the exact SQL it had before (``date(timezone(...))``, ``greatest``); SQLite
gets an equivalent. Lima has had no daylight saving since 1994, so a fixed UTC-5 offset is
the same as ``America/Lima``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Date, DateTime, String, case, cast, func, literal
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import TypeDecorator

LIMA_TZ = "America/Lima"


class UTCDateTime(TypeDecorator[datetime]):
    """``timestamptz`` that always binds UTC and always reads back an aware datetime.

    Postgres already does both. SQLite stores the wall time it is given and returns naive
    values, so a Lima-time bound or an aware ``now`` would be compared against the wrong
    hour, and Python would refuse to compare naive with aware datetimes.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class lima_date(FunctionElement[Any]):  # noqa: N801 - reads like a SQL function
    """Calendar day in Lima of a UTC timestamp column."""

    type = Date()
    inherit_cache = True
    name = "lima_date"


@compiles(lima_date)
def _lima_date_default(element: lima_date, compiler: SQLCompiler, **kw: Any) -> str:
    column = compiler.process(element.clauses, **kw)
    return f"date(timezone('{LIMA_TZ}', {column}))"


@compiles(lima_date, "sqlite")
def _lima_date_sqlite(element: lima_date, compiler: SQLCompiler, **kw: Any) -> str:
    column = compiler.process(element.clauses, **kw)
    return f"date({column}, '-5 hours')"


class greatest(FunctionElement[Any]):  # noqa: N801 - reads like a SQL function
    """``GREATEST(a, b, ...)``; SQLite spells it as the scalar ``max(a, b, ...)``."""

    inherit_cache = True
    name = "greatest"


@compiles(greatest)
def _greatest_default(element: greatest, compiler: SQLCompiler, **kw: Any) -> str:
    return f"greatest({compiler.process(element.clauses, **kw)})"


@compiles(greatest, "sqlite")
def _greatest_sqlite(element: greatest, compiler: SQLCompiler, **kw: Any) -> str:
    return f"max({compiler.process(element.clauses, **kw)})"


def zero_pad(value: Any, width: int) -> ColumnElement[str]:
    """Integer as text, left-padded with zeros to ``width`` (like Python's ``f"{n:0{width}d}"``).

    Built from ``||``, ``substr`` and ``length``, which both backends have (``lpad`` is
    Postgres-only). NULL stays NULL, as with ``lpad``.
    """
    text = cast(value, String)
    padded = func.substr(literal("0" * width).concat(text), func.length(text) + 1)
    return case((func.length(text) >= width, text), else_=padded)
