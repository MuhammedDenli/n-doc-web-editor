"""CSV data in ``common/db``: schema, byte-exact row edits and key validation.

* Schema: the ``CREATE TABLE`` statements of the Lua modules listed in
  ``common/db/config`` (what the build loads) merged with ``create_tables.sql``,
  introspected with an in-memory SQLite. Column order always comes from the CSV
  header. ``bundles.csv`` names its column ``NAME`` (schema: ``bundle``), and a
  foreign key onto one column of a composite primary key (``interfaces.module ->
  modules.label``) is upgraded to the full key (``(subsystem, module) ->
  modules(subsystem, label)``) when the child has the other key columns.
* Files are edited line by line: unchanged lines keep their exact bytes
  (trailing spaces, LaTeX escapes), as does the trailing-newline state.
* Edits may not add key violations (duplicate/empty primary key, unresolved
  foreign key); violations already in the data do not block unrelated edits.
  A referenced key is never changed or deleted implicitly: ``rename_key``
  updates the referencing rows in the same atomic write.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath

from . import files
from .errors import (
    AmbiguousMatchError,
    CoreError,
    DuplicateKeyError,
    ForeignKeyError,
    GitError,
    InvalidContentError,
    InvalidValueError,
    ReferencedRowError,
    RowNotFoundError,
    StaleWriteError,
    UnknownTableError,
)
from .repo import Repo

SQL_SCHEMA = "create_tables.sql"
LUA_CONFIG = "config"
LUA_DIR = "lua"
# table -> {schema column: CSV header column}
COLUMN_ALIASES: dict[str, dict[str, str]] = {"bundles": {"bundle": "NAME"}}

_LUA_CREATE_RE = re.compile(r"\[\[\s*(CREATE\s+TABLE\b.*?)\]\]", re.DOTALL | re.IGNORECASE)
_SQL_CREATE_RE = re.compile(r"CREATE\s+TABLE\b.*?\)\s*;", re.DOTALL | re.IGNORECASE)
_MODULE_RE = re.compile(r"^[A-Za-z0-9_]+$")
_FORBIDDEN_CHARS = ("\n", "\r", "\x00")
_KEY_FORBIDDEN_CHARS = (";", '"')
MAX_REFERENCED_BY = 20


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ForeignKey:
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


@dataclass(frozen=True)
class Table:
    name: str
    path: str
    columns: tuple[str, ...]  # CSV header
    primary_key: tuple[str, ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()

    @property
    def key_columns(self) -> set[str]:
        return set(self.primary_key).union(*(fk.columns for fk in self.foreign_keys))


Schema = dict[str, Table]


@dataclass
class _Def:
    columns: list[str] = field(default_factory=list)
    primary_key: tuple[str, ...] = ()
    foreign_keys: list[ForeignKey] = field(default_factory=list)


def _introspect(statements: Iterable[str]) -> dict[str, _Def]:
    """Run CREATE TABLE statements in a scratch SQLite DB and read them back."""
    con = sqlite3.connect(":memory:")
    try:
        for stmt in statements:
            try:
                con.execute(stmt)
            except sqlite3.Error:
                continue  # one malformed definition must not hide the others
        defs: dict[str, _Def] = {}
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for name in names:
            info = con.execute(f"PRAGMA table_info('{name}')").fetchall()
            pk = tuple(r[1] for r in sorted((r for r in info if r[5]), key=lambda r: r[5]))
            fks: dict[int, list[tuple[str, str, str | None]]] = {}
            for r in con.execute(f"PRAGMA foreign_key_list('{name}')").fetchall():
                fks.setdefault(r[0], []).append((r[2], r[3], r[4]))
            d = _Def(columns=[r[1] for r in info], primary_key=pk)
            for parts in fks.values():
                d.foreign_keys.append(
                    ForeignKey(
                        columns=tuple(p[1] for p in parts),
                        ref_table=parts[0][0],
                        ref_columns=tuple(p[2] or "" for p in parts),
                    )
                )
            defs[name] = d
        return defs
    finally:
        con.close()


def _schema_sources(repo: Repo) -> list[dict[str, _Def]]:
    sources = []
    db = PurePosixPath(repo.db_dir)
    config = repo.root / db / LUA_CONFIG  # fixed path, no extension (not via the path guard)
    if config.is_file():
        for mod in (line.strip() for line in config.read_text(encoding="utf-8").splitlines()):
            if not _MODULE_RE.match(mod) or not _exists(repo, PurePosixPath(LUA_DIR, f"{mod}.lua")):
                continue
            text = files.read_file(repo, f"{LUA_DIR}/{mod}.lua").text
            sources.append(_introspect(_LUA_CREATE_RE.findall(text)))
    if _exists(repo, db / SQL_SCHEMA):
        text = files.read_file(repo, str(db / SQL_SCHEMA)).text
        sources.append(_introspect(_SQL_CREATE_RE.findall(text)))
    return sources


def _exists(repo: Repo, rel: PurePosixPath) -> bool:
    return (repo.root / rel).is_file()


def _merge(sources: list[dict[str, _Def]]) -> dict[str, _Def]:
    """First source wins for the primary key; foreign keys are united."""
    merged: dict[str, _Def] = {}
    for source in sources:
        for name, d in source.items():
            m = merged.setdefault(name, _Def())
            m.columns += [c for c in d.columns if c not in m.columns]
            m.primary_key = m.primary_key or d.primary_key
            m.foreign_keys += [fk for fk in d.foreign_keys if fk not in m.foreign_keys]
    return merged


def _alias(table: str, column: str) -> str:
    return COLUMN_ALIASES.get(table, {}).get(column, column)


def build_schema(
    defs: dict[str, _Def], headers: Mapping[str, tuple[str, ...]], db_dir: str
) -> Schema:
    """Schema of the tables that have a CSV file (``headers``: table -> header)."""
    for name, d in defs.items():
        d.primary_key = tuple(_alias(name, c) for c in d.primary_key)
        for i, fk in enumerate(d.foreign_keys):
            ref = defs.get(fk.ref_table)
            ref_cols = fk.ref_columns
            if any(not c for c in ref_cols) and ref:
                ref_cols = ref.primary_key  # REFERENCES t without column list
            d.foreign_keys[i] = ForeignKey(
                columns=tuple(_alias(name, c) for c in fk.columns),
                ref_table=fk.ref_table,
                ref_columns=tuple(_alias(fk.ref_table, c) for c in ref_cols),
            )
    schema: Schema = {}
    for name, header in headers.items():
        d = defs.get(name, _Def())
        fks: list[ForeignKey] = []
        for fk in d.foreign_keys:
            fk = _upgrade_composite(fk, header, defs)
            ref_header = headers.get(fk.ref_table)
            if (
                ref_header is not None
                and all(c in header for c in fk.columns)
                and all(c in ref_header for c in fk.ref_columns)
                and fk not in fks
            ):
                fks.append(fk)
        pk = d.primary_key if all(c in header for c in d.primary_key) else ()
        schema[name] = Table(
            name=name,
            path=f"{db_dir}/{name}.csv",
            columns=header,
            primary_key=pk,
            foreign_keys=tuple(fks),
        )
    return schema


def _upgrade_composite(
    fk: ForeignKey, header: tuple[str, ...], defs: dict[str, _Def]
) -> ForeignKey:
    ref = defs.get(fk.ref_table)
    if len(fk.columns) != 1 or not ref or len(ref.primary_key) < 2:
        return fk
    (col,), (ref_col,) = fk.columns, fk.ref_columns
    if ref_col not in ref.primary_key:
        return fk
    others = [c for c in ref.primary_key if c != ref_col]
    if not all(c in header for c in others):
        return fk
    return ForeignKey(
        columns=tuple(col if c == ref_col else c for c in ref.primary_key),
        ref_table=fk.ref_table,
        ref_columns=ref.primary_key,
    )


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RawRow:
    line: str  # exact text, without the line break
    values: tuple[str, ...] | None  # None: blank line (kept, not a record)


@dataclass(frozen=True)
class CsvFile:
    path: str
    header_line: str
    columns: tuple[str, ...]
    rows: tuple[RawRow, ...]
    trailing_newline: bool
    sha256: str = ""

    def serialize(self) -> str:
        lines = [self.header_line, *(r.line for r in self.rows)]
        return "\n".join(lines) + ("\n" if self.trailing_newline else "")

    def records(self) -> Iterable[tuple[int, tuple[str, ...]]]:
        """(file line number, values) of the data rows."""
        for i, row in enumerate(self.rows):
            if row.values is not None:
                yield i + 2, row.values


def _parse_line(line: str, path: str, lineno: int) -> tuple[str, ...]:
    try:
        rows = list(csv.reader([line], delimiter=";", strict=True))
    except csv.Error as exc:
        raise InvalidContentError(f"line {lineno}: {exc}", path=path, line=lineno) from None
    return tuple(rows[0]) if rows else ()


def parse_csv(text: str, path: str, sha256: str = "") -> CsvFile:
    if "\r" in text:
        raise InvalidContentError("CR line endings are not supported in CSV data", path=path)
    if not text:
        raise InvalidContentError("CSV file has no header", path=path)
    trailing = text.endswith("\n")
    lines = (text[:-1] if trailing else text).split("\n")
    columns = _parse_line(lines[0], path, 1)
    if not columns or any(not c for c in columns):
        raise InvalidContentError("CSV header is empty or has an empty column name", path=path)
    rows = tuple(
        RawRow(line=line, values=_parse_line(line, path, i + 2) if line else None)
        for i, line in enumerate(lines[1:])
    )
    return CsvFile(
        path=path,
        header_line=lines[0],
        columns=columns,
        rows=rows,
        trailing_newline=trailing,
        sha256=sha256,
    )


def format_row(values: Iterable[str]) -> str:
    out = []
    for v in values:
        if ";" in v or '"' in v:
            v = '"' + v.replace('"', '""') + '"'
        out.append(v)
    return ";".join(out)


def read_csv_rows(repo: Repo, rel: str) -> list[dict[str, str]]:
    """Records of a CSV file as dicts (missing file: empty list)."""
    if not (repo.root / rel).is_file():
        return []
    f = _read(repo, rel)
    return [dict(zip(f.columns, v, strict=False)) for _, v in f.records()]


def _read(repo: Repo, rel: str) -> CsvFile:
    content = files.read_file(repo, rel)
    return parse_csv(content.text, content.path, content.sha256)


def _csv_paths(repo: Repo) -> dict[str, str]:
    db = repo.root / repo.db_dir
    if not db.is_dir():
        return {}
    return {p.stem: f"{repo.db_dir}/{p.name}" for p in sorted(db.glob("*.csv")) if p.is_file()}


def _load(repo: Repo) -> tuple[Schema, dict[str, CsvFile]]:
    data = {name: _read(repo, rel) for name, rel in _csv_paths(repo).items()}
    schema = build_schema(
        _merge(_schema_sources(repo)), {n: f.columns for n, f in data.items()}, repo.db_dir
    )
    return schema, data


def load_schema(repo: Repo) -> Schema:
    return _load(repo)[0]


# --------------------------------------------------------------------------
# Violations
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    kind: str  # duplicate_key | empty_key | foreign_key | column_count
    table: str
    columns: tuple[str, ...]
    values: tuple[str, ...]
    ref_table: str | None = None
    line: int | None = field(default=None, compare=False)

    def message(self) -> str:
        vals = ", ".join(f"{c}={v!r}" for c, v in zip(self.columns, self.values, strict=False))
        if self.kind == "duplicate_key":
            return f"duplicate primary key ({vals}) in {self.table}"
        if self.kind == "empty_key":
            return f"empty primary key column in {self.table} ({vals})"
        if self.kind == "foreign_key":
            return f"{self.table}: ({vals}) not found in {self.ref_table}"
        return f"{self.table}: row has {self.values[0]} fields, header has {len(self.columns)}"


def _project(table: Table, values: tuple[str, ...], cols: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(values[table.columns.index(c)] for c in cols)


def _key_set(schema: Schema, data: Mapping[str, CsvFile], table: str, cols: tuple[str, ...]):
    t = schema[table]
    return {_project(t, v, cols) for _, v in data[table].records() if len(v) == len(t.columns)}


def violations(schema: Schema, data: Mapping[str, CsvFile]) -> list[Violation]:
    out: list[Violation] = []
    key_cache: dict[tuple[str, tuple[str, ...]], set[tuple[str, ...]]] = {}
    for name, t in schema.items():
        f = data.get(name)
        if f is None:
            continue
        seen: dict[tuple[str, ...], int] = {}
        for lineno, values in f.records():
            if len(values) != len(t.columns):
                out.append(
                    Violation(
                        "column_count", name, t.columns, (str(len(values)), *values), line=lineno
                    )
                )
                continue
            if t.primary_key:
                key = _project(t, values, t.primary_key)
                if any(v == "" for v in key):
                    out.append(Violation("empty_key", name, t.primary_key, key, line=lineno))
                elif key in seen:
                    out.append(Violation("duplicate_key", name, t.primary_key, key, line=lineno))
                else:
                    seen[key] = lineno
            for fk in t.foreign_keys:
                vals = _project(t, values, fk.columns)
                if any(v == "" for v in vals):
                    continue  # empty acts as NULL, like the SQLite tables of the build
                cache_key = (fk.ref_table, fk.ref_columns)
                if cache_key not in key_cache:
                    key_cache[cache_key] = _key_set(schema, data, fk.ref_table, fk.ref_columns)
                if vals not in key_cache[cache_key]:
                    out.append(
                        Violation("foreign_key", name, fk.columns, vals, fk.ref_table, line=lineno)
                    )
    return out


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TableInfo:
    name: str
    path: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...]
    row_count: int
    trailing_newline: bool


@dataclass(frozen=True)
class Row:
    line: int
    values: dict[str, str]


@dataclass(frozen=True)
class TableData:
    table: str
    path: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    sha256: str
    rows: list[Row]
    total: int
    truncated: bool


@dataclass(frozen=True)
class LookupOption:
    value: str
    name: str
    key: dict[str, str]  # the full referenced key (composite foreign keys)


def list_tables(repo: Repo) -> list[TableInfo]:
    schema, data = _load(repo)
    return [
        TableInfo(
            name=t.name,
            path=t.path,
            columns=t.columns,
            primary_key=t.primary_key,
            foreign_keys=t.foreign_keys,
            row_count=sum(1 for _ in data[t.name].records()),
            trailing_newline=data[t.name].trailing_newline,
        )
        for t in schema.values()
    ]


def _table(schema: Schema, name: str) -> Table:
    if not isinstance(name, str) or name not in schema:
        raise UnknownTableError(f"unknown table '{name}'", table=name, tables=sorted(schema))
    return schema[name]


def _as_dict(t: Table, values: tuple[str, ...]) -> dict[str, str]:
    return dict(zip(t.columns, values, strict=False))


def _check_columns(t: Table, cols: Iterable[str]) -> None:
    unknown = [c for c in cols if c not in t.columns]
    if unknown:
        raise InvalidValueError(
            f"unknown column(s) {', '.join(map(repr, unknown))} in {t.name}",
            table=t.name,
            columns=list(t.columns),
        )


def read_table(
    repo: Repo, table: str, where: Mapping[str, str] | None = None, limit: int | None = None
) -> TableData:
    schema, data = _load(repo)
    t = _table(schema, table)
    where = dict(where or {})
    _check_columns(t, where)
    rows = [
        Row(line=lineno, values=_as_dict(t, v))
        for lineno, v in data[table].records()
        if all(_as_dict(t, v).get(c) == str(val) for c, val in where.items())
    ]
    total = len(rows)
    if limit is not None:
        rows = rows[: max(0, int(limit))]
    return TableData(
        table=t.name,
        path=t.path,
        columns=t.columns,
        primary_key=t.primary_key,
        sha256=data[table].sha256,
        rows=rows,
        total=total,
        truncated=len(rows) < total,
    )


def lookup(
    repo: Repo, table: str, column: str, prefix: str = "", limit: int = 50
) -> list[LookupOption]:
    """Allowed values for ``table.column`` (FK select, autocompletion).

    A foreign key column offers the referenced rows (with their ``name`` and full
    key); any other column offers its distinct existing values.
    """
    schema, data = _load(repo)
    t = _table(schema, table)
    _check_columns(t, [column])
    fks = [fk for fk in t.foreign_keys if column in fk.columns]
    prefix_l = (prefix or "").lower()
    out: dict[tuple, LookupOption] = {}
    if fks:
        fk = max(fks, key=lambda f: len(f.columns))
        ref = schema[fk.ref_table]
        ref_col = fk.ref_columns[fk.columns.index(column)]
        for _, v in data[ref.name].records():
            if len(v) != len(ref.columns):
                continue
            row = _as_dict(ref, v)
            key = {c: row[rc] for c, rc in zip(fk.columns, fk.ref_columns, strict=True)}
            opt = LookupOption(value=row[ref_col], name=row.get("name", ""), key=key)
            out.setdefault(tuple(key.values()), opt)
    else:
        for _, v in data[table].records():
            value = _as_dict(t, v).get(column, "")
            out.setdefault((value,), LookupOption(value=value, name="", key={column: value}))
    opts = [o for o in out.values() if o.value.lower().startswith(prefix_l)]
    return opts[: max(1, min(int(limit), 1000))]


# --------------------------------------------------------------------------
# Edits
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RowChange:
    table: str
    path: str
    sha256: str
    line: int | None  # line of the new/changed row (None after delete)
    row: dict[str, str]  # new row (old row after delete)


def _check_value_types(t: Table, values: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(values, Mapping):
        raise InvalidValueError("values must be an object of column -> text", table=t.name)
    _check_columns(t, values)
    keys = t.key_columns
    out = {}
    for col, v in values.items():
        if not isinstance(v, str):
            raise InvalidValueError(f"value of '{col}' must be text", table=t.name, column=col)
        if any(ch in v for ch in _FORBIDDEN_CHARS):
            raise InvalidValueError(
                f"value of '{col}' must not contain line breaks or NUL", table=t.name, column=col
            )
        if col in keys and any(ch in v for ch in _KEY_FORBIDDEN_CHARS):
            raise InvalidValueError(
                f"key column '{col}' must not contain ';' or '\"'", table=t.name, column=col
            )
        out[col] = v
    return out


def _find(t: Table, f: CsvFile, match: Mapping[str, object]) -> int:
    """Index into ``f.rows`` of the single record matching ``match``."""
    if not isinstance(match, Mapping) or not match:
        raise InvalidValueError("match must name at least one column", table=t.name)
    _check_columns(t, match)
    hits = [
        i
        for i, row in enumerate(f.rows)
        if row.values is not None
        and all(_as_dict(t, row.values).get(c) == v for c, v in match.items())
    ]
    if not hits:
        raise RowNotFoundError(f"no row in {t.name} matches", table=t.name, match=dict(match))
    if len(hits) > 1:
        raise AmbiguousMatchError(
            f"{len(hits)} rows in {t.name} match; name more columns (e.g. the primary key)",
            table=t.name,
            match=dict(match),
            occurrences=len(hits),
        )
    return hits[0]


def _with_rows(f: CsvFile, rows: list[RawRow]) -> CsvFile:
    return replace(f, rows=tuple(rows))


def _raw(values: tuple[str, ...]) -> RawRow:
    return RawRow(line=format_row(values), values=values)


def _check_expected(f: CsvFile, expected_hash: str | None) -> None:
    if expected_hash is not None and expected_hash != f.sha256:
        raise StaleWriteError("file changed since it was read", path=f.path, current_hash=f.sha256)


def _referenced_by(
    schema: Schema, data: Mapping[str, CsvFile], found: list[Violation]
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for v in found:
        if len(out) >= MAX_REFERENCED_BY:
            break
        out.append(
            {
                "table": v.table,
                "path": schema[v.table].path,
                "line": v.line,
                "columns": list(v.columns),
                "values": list(v.values),
            }
        )
    return out


def _commit(
    schema: Schema,
    data: dict[str, CsvFile],
    changed: dict[str, CsvFile],
    edited: tuple[str, set[tuple[str, ...]]] | None,
    repo: Repo,
) -> dict[str, files.WriteResult]:
    """Validate ``changed`` against ``data`` and write it.

    ``edited`` is (table, rows written by the caller); a new foreign key
    violation from one of those rows is the caller's mistake, any other new
    violation means a row elsewhere lost its referenced key.
    """
    before = set(violations(schema, data))
    after_data = {**data, **changed}
    new = [v for v in violations(schema, after_data) if v not in before]
    if new:
        _raise_for(schema, after_data, new, edited)
    results = files.write_many(
        repo, {f.path: (f.serialize(), data[name].sha256) for name, f in changed.items()}
    )
    return {r.path: r for r in results}


def _raise_for(
    schema: Schema,
    data: Mapping[str, CsvFile],
    new: list[Violation],
    edited: tuple[str, set[tuple[str, ...]]] | None,
) -> None:
    def own(v: Violation) -> bool:
        if not edited or v.table != edited[0]:
            return False
        t = schema[v.table]
        return any(_project(t, row, v.columns) == v.values for row in edited[1])

    mine = [v for v in new if own(v) or v.kind != "foreign_key"]
    incoming = [v for v in new if v.kind == "foreign_key" and not own(v)]
    if incoming and not mine:
        raise ReferencedRowError(
            "the key is still referenced by other rows; change or delete those rows "
            "first, or use rename_key to rename a key together with its references",
            referenced_by=_referenced_by(schema, data, incoming),
            count=len(incoming),
        )
    v = mine[0]
    details = {"table": v.table, "columns": list(v.columns), "values": list(v.values)}
    if v.kind == "foreign_key":
        raise ForeignKeyError(v.message(), ref_table=v.ref_table, **details)
    if v.kind == "duplicate_key":
        raise DuplicateKeyError(v.message(), **details)
    raise InvalidValueError(v.message(), **details)


def insert_row(
    repo: Repo, table: str, values: Mapping[str, str], *, expected_hash: str | None = None
) -> RowChange:
    """Append a row; columns left out are empty."""
    schema, data = _load(repo)
    t = _table(schema, table)
    vals = _check_value_types(t, values)
    f = data[table]
    _check_expected(f, expected_hash)
    new_values = tuple(vals.get(c, "") for c in t.columns)
    new_file = _with_rows(f, [*f.rows, _raw(new_values)])
    res = _commit(schema, data, {table: new_file}, (table, {new_values}), repo)[t.path]
    return RowChange(t.name, t.path, res.sha256, len(new_file.rows) + 1, _as_dict(t, new_values))


def update_row(
    repo: Repo,
    table: str,
    match: Mapping[str, str],
    values: Mapping[str, str],
    *,
    expected_hash: str | None = None,
) -> RowChange:
    """Change the given columns of the single row matching ``match``."""
    schema, data = _load(repo)
    t = _table(schema, table)
    vals = _check_value_types(t, values)
    if not vals:
        raise InvalidValueError("no values to change", table=t.name)
    f = data[table]
    _check_expected(f, expected_hash)
    i = _find(t, f, match)
    old = f.rows[i].values or ()
    if len(old) != len(t.columns):
        raise InvalidContentError(
            f"line {i + 2} has {len(old)} fields, header has {len(t.columns)}; fix the line "
            "with edit_file",
            path=t.path,
            line=i + 2,
        )
    new_values = tuple(vals.get(c, old[k]) for k, c in enumerate(t.columns))
    if new_values == old:
        raise InvalidValueError("values are identical to the current row", table=t.name)
    rows = list(f.rows)
    rows[i] = _raw(new_values)
    res = _commit(schema, data, {table: _with_rows(f, rows)}, (table, {new_values}), repo)[t.path]
    return RowChange(t.name, t.path, res.sha256, i + 2, _as_dict(t, new_values))


def delete_row(
    repo: Repo, table: str, match: Mapping[str, str], *, expected_hash: str | None = None
) -> RowChange:
    """Delete the single row matching ``match``; refused while it is referenced."""
    schema, data = _load(repo)
    t = _table(schema, table)
    f = data[table]
    _check_expected(f, expected_hash)
    i = _find(t, f, match)
    old = f.rows[i].values or ()
    rows = list(f.rows)
    del rows[i]
    res = _commit(schema, data, {table: _with_rows(f, rows)}, None, repo)[t.path]
    return RowChange(t.name, t.path, res.sha256, None, _as_dict(t, old))


# --------------------------------------------------------------------------
# Rename
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FileChange:
    path: str
    sha256: str
    rows_changed: int


@dataclass(frozen=True)
class TexReference:
    path: str
    line: int
    col: int
    macro: str
    key: str
    replacement: str  # the key to use after the rename


@dataclass(frozen=True)
class RenameResult:
    table: str
    old_key: dict[str, str]
    new_key: dict[str, str]
    files: list[FileChange]
    tex_references: list[TexReference]


def rename_key(
    repo: Repo,
    table: str,
    match: Mapping[str, str],
    new_key: Mapping[str, str],
    *,
    expected_hash: str | None = None,
) -> RenameResult:
    """Change the primary key of one row and every foreign key referencing it.

    All CSV files are written in one atomic step. ``.tex`` files are not
    touched; ``tex_references`` lists the reference macros that use the old key.
    """
    schema, data = _load(repo)
    t = _table(schema, table)
    if not t.primary_key:
        raise InvalidValueError(f"{t.name} has no primary key to rename", table=t.name)
    vals = _check_value_types(t, new_key)
    not_key = [c for c in vals if c not in t.primary_key]
    if not vals or not_key:
        raise InvalidValueError(
            f"new_key must only contain primary key columns {list(t.primary_key)}",
            table=t.name,
            primary_key=list(t.primary_key),
        )
    f = data[table]
    _check_expected(f, expected_hash)
    i = _find(t, f, match)
    old = f.rows[i].values or ()
    old_pk = _project(t, old, t.primary_key)
    new_values = tuple(vals.get(c, old[k]) for k, c in enumerate(t.columns))
    new_pk = _project(t, new_values, t.primary_key)
    if new_pk == old_pk:
        raise InvalidValueError("new key is identical to the current key", table=t.name)

    work = {name: list(cf.rows) for name, cf in data.items()}
    counts: dict[str, int] = {table: 1}
    work[table][i] = _raw(new_values)
    for child in schema.values():
        for fk in child.foreign_keys:
            if fk.ref_table != table or set(fk.ref_columns) != set(t.primary_key):
                continue  # only references to the full key follow the rename
            old_ref = tuple(old_pk[t.primary_key.index(c)] for c in fk.ref_columns)
            new_ref = tuple(new_pk[t.primary_key.index(c)] for c in fk.ref_columns)
            for j, row in enumerate(work[child.name]):
                v = row.values
                if v is None or len(v) != len(child.columns):
                    continue
                if _project(child, v, fk.columns) != old_ref:
                    continue
                updated = list(v)
                for c, nv in zip(fk.columns, new_ref, strict=True):
                    updated[child.columns.index(c)] = nv
                work[child.name][j] = _raw(tuple(updated))
                counts[child.name] = counts.get(child.name, 0) + 1
    changed = {name: _with_rows(data[name], work[name]) for name in counts}
    results = _commit(schema, data, changed, (table, {new_values}), repo)
    return RenameResult(
        table=t.name,
        old_key=dict(zip(t.primary_key, old_pk, strict=True)),
        new_key=dict(zip(t.primary_key, new_pk, strict=True)),
        files=[
            FileChange(schema[n].path, results[schema[n].path].sha256, c) for n, c in counts.items()
        ],
        tex_references=find_tex_references(repo, t.name, old_pk, new_pk),
    )


# table -> reference macro kind (checks.REFERENCE_MACROS)
_TABLE_KINDS = {
    "sfr": "sfr",
    "tsfi": "tsfi",
    "sf": "sf",
    "obj": "obj",
    "spd": "spd",
    "subjobj": "subjobj",
    "errors": "error",
}
_TDS_DEPTH = {"subsystems": 1, "modules": 2, "interfaces": 3}
_TDS_PREFIX = {1: "sub", 2: "mod", 3: "int"}


def find_tex_references(
    repo: Repo, table: str, old_key: tuple[str, ...], new_key: tuple[str, ...]
) -> list[TexReference]:
    """Reference macros in ``.tex`` files that resolve to ``old_key`` of ``table``."""
    from . import checks  # checks imports this module
    from .texutil import line_col

    kind = "tds" if table in _TDS_DEPTH else _TABLE_KINDS.get(table)
    if kind is None:
        return []
    out = []
    for entry in files.list_files(repo):
        if not entry.path.endswith(".tex"):
            continue
        try:
            text = files.read_file(repo, entry.path).text
        except CoreError:
            continue
        for ref in checks.find_references(text):
            if ref.kind != kind:
                continue
            replacement = _renamed(table, ref.key, old_key, new_key)
            if replacement is None:
                continue
            line, col = line_col(text, ref.offset)
            out.append(TexReference(entry.path, line, col, ref.macro, ref.key, replacement))
    return out


def _renamed(table: str, key: str, old: tuple[str, ...], new: tuple[str, ...]) -> str | None:
    if table not in _TDS_DEPTH:
        return new[0] if key.lower() == old[0].lower() else None
    # sub.<s> / mod.<s>.<m> / int.<s>.<m>.<i>: a key covers every deeper level
    depth = _TDS_DEPTH[table]
    parts = key.split(".")
    level = {"sub": 1, "mod": 2, "int": 3}.get(parts[0])
    if level is None or level < depth or len(parts) != level + 1:
        return None
    if tuple(parts[1 : depth + 1]) != old:
        return None
    return ".".join([_TDS_PREFIX[level], *new, *parts[depth + 1 :]])


# --------------------------------------------------------------------------
# Whole-database check
# --------------------------------------------------------------------------


def _baseline(repo: Repo, schema: Schema, rev: str) -> set[Violation] | None:
    from . import git

    data: dict[str, CsvFile] = {}
    try:
        for name, t in schema.items():
            text = git.show_file(repo, rev, t.path)
            if text is None:
                continue
            try:
                data[name] = parse_csv(text, t.path)
            except InvalidContentError:
                continue
    except GitError:
        return None
    # a table whose baseline header differs cannot be compared column-wise
    usable = {n: f for n, f in data.items() if f.columns == schema[n].columns}
    sub_schema = {n: schema[n] for n in usable}
    return set(violations(sub_schema, usable))


def validate_db(repo: Repo, baseline: str | None = "HEAD"):
    """Key violations in all CSV tables as a ``checks.CheckReport``.

    With ``baseline``, violations that already exist at that revision are
    warnings and only new ones are errors.
    """
    from . import checks

    report = checks.CheckReport(checked=[])
    try:
        schema, data = _load(repo)
    except InvalidContentError as exc:
        report.issues.append(
            checks.Issue(code="csv_invalid", message=exc.message, path=exc.details.get("path"))
        )
        return report
    report.checked = [t.path for t in schema.values()]
    known = _baseline(repo, schema, baseline) if baseline else None
    for v in violations(schema, data):
        old = known is not None and v in known
        report.issues.append(
            checks.Issue(
                code=f"csv_{v.kind}",
                message=v.message() + (f" (already in {baseline})" if old else ""),
                severity="warning" if old else "error",
                path=schema[v.table].path,
                line=v.line,
            )
        )
    return report
