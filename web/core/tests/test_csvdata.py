import pytest

from ndoc_core import csvdata, files, git
from ndoc_core.errors import (
    AmbiguousMatchError,
    DuplicateKeyError,
    ForeignKeyError,
    InvalidContentError,
    InvalidValueError,
    ReferencedRowError,
    RowNotFoundError,
    StaleWriteError,
    UnknownTableError,
)

DB = "common/db"


def raw(repo, name):
    return (repo.root / DB / f"{name}.csv").read_bytes()


def snapshot(repo):
    return {p.name: p.read_bytes() for p in (repo.root / DB).glob("*.csv")}


# ------------------------------------------------------------------ schema


def test_schema_keys(repo):
    s = csvdata.load_schema(repo)
    assert s["modules"].primary_key == ("subsystem", "label")
    assert s["interfaces"].primary_key == ("subsystem", "module", "label")
    assert s["sfr_obj"].primary_key == ()
    assert {"subjobj", "sfr_subjobj", "releases"} <= s.keys()
    assert s["releases"].primary_key == ("document",)


def test_schema_composite_foreign_keys(repo):
    s = csvdata.load_schema(repo)
    composite = csvdata.ForeignKey(("subsystem", "module"), "modules", ("subsystem", "label"))
    for name in ("interfaces", "sfr_module", "testcase_module", "bundle_module"):
        assert composite in s[name].foreign_keys, name
        # the bare (non-unique) reference onto modules.label is gone
        assert all(fk.columns != ("module",) for fk in s[name].foreign_keys)


def test_schema_lua_only_parts_and_alias(repo):
    s = csvdata.load_schema(repo)
    # sfr_module -> subsystems exists only in lua/cc_core.lua
    assert (
        csvdata.ForeignKey(("subsystem",), "subsystems", ("label",)) in s["sfr_module"].foreign_keys
    )
    # spd.PP_order is in the Lua schema but not in the CSV header
    assert s["spd"].columns == ("label", "name", "description", "PP")
    assert s["bundles"].primary_key == ("NAME",)
    assert csvdata.ForeignKey(("bundle",), "bundles", ("NAME",)) in s["bundle_module"].foreign_keys


def test_list_tables(repo):
    tables = {t.name: t for t in csvdata.list_tables(repo)}
    assert tables["subjobj"].trailing_newline is False
    assert tables["sfr"].trailing_newline is True
    assert tables["subjobj"].row_count == 2
    assert tables["sfr"].path == f"{DB}/sfr.csv"


# ------------------------------------------------------------ byte-exactness


def test_all_files_round_trip(real_repo):
    for name, rel in csvdata._csv_paths(real_repo).items():
        data = (real_repo.root / rel).read_bytes()
        f = csvdata.parse_csv(data.decode("utf-8"), rel)
        assert f.serialize().encode("utf-8") == data, name


@pytest.mark.parametrize(
    "text",
    ["a;b\n", "a;b", "a;b\n1;2\n\n3;4", "a;b\n1 ;\\_x\\-y \n", 'a;b\n"x;y";"q""z"\n'],
)
def test_parse_serialize_identity(text):
    assert csvdata.parse_csv(text, "t.csv").serialize() == text


def test_parse_rejects_crlf_and_open_quote():
    with pytest.raises(InvalidContentError):
        csvdata.parse_csv("a;b\r\n1;2\r\n", "t.csv")
    with pytest.raises(InvalidContentError):
        csvdata.parse_csv('a;b\n"open;2\n', "t.csv")


def test_update_changes_only_that_line(repo):
    before = snapshot(repo)
    old_lines = before["sf.csv"].decode().split("\n")
    trailing_space = next(line for line in old_lines if line.endswith(" "))
    res = csvdata.update_row(
        repo, "sf", {"label": "sf.cryptographicservices"}, {"name": "SF.Kryp\\-to"}
    )
    after = snapshot(repo)
    assert {k for k in before if before[k] != after[k]} == {"sf.csv"}
    new_lines = after["sf.csv"].decode().split("\n")
    diff = [i for i, (a, b) in enumerate(zip(old_lines, new_lines, strict=True)) if a != b]
    assert len(diff) == 1 and res.line == diff[0] + 1
    assert new_lines[diff[0]].split(";")[1] == "SF.Kryp\\-to"
    assert trailing_space in new_lines
    assert res.sha256 == files.read_file(repo, f"{DB}/sf.csv").sha256


def test_no_trailing_newline_is_kept(repo):
    csvdata.insert_row(repo, "subjobj", {"label": "s_user", "name": "S\\_User"})
    data = raw(repo, "subjobj")
    assert data.endswith(b"s_user;S\\_User;") and not data.endswith(b"\n")
    csvdata.delete_row(repo, "subjobj", {"label": "s_user"})
    assert not raw(repo, "subjobj").endswith(b"\n")
    assert raw(repo, "subjobj") == (repo.root / "common/test_db/subjobj.csv").read_bytes()


def test_insert_then_delete_restores_bytes(repo):
    before = snapshot(repo)
    row = {"sfr": "fcs_cop.1.1/hmac", "obj": "o.vpn_auth"}
    csvdata.insert_row(repo, "sfr_obj", row)
    csvdata.delete_row(repo, "sfr_obj", row)
    assert snapshot(repo) == before


def test_value_with_semicolon_is_quoted(repo):
    csvdata.update_row(repo, "sf", {"label": "sf.cryptographicservices"}, {"description": 'a; "b"'})
    row = csvdata.read_table(repo, "sf", {"label": "sf.cryptographicservices"}).rows[0]
    assert row.values["description"] == 'a; "b"'
    assert b'"a; ""b"""' in raw(repo, "sf")


# ------------------------------------------------------------------ reading


def test_read_table_where_and_limit(repo):
    data = csvdata.read_table(repo, "modules", {"subsystem": "vpn"})
    assert {r.values["label"] for r in data.rows} >= {"core"}
    assert all(r.values["subsystem"] == "vpn" for r in data.rows)
    limited = csvdata.read_table(repo, "sfr", limit=2)
    assert len(limited.rows) == 2 and limited.truncated and limited.total > 2
    assert limited.rows[0].line == 2


def test_read_table_errors(repo):
    with pytest.raises(UnknownTableError):
        csvdata.read_table(repo, "nope")
    with pytest.raises(InvalidValueError):
        csvdata.read_table(repo, "sfr", {"nocolumn": "x"})


def test_lookup_foreign_key_and_plain(repo):
    opts = csvdata.lookup(repo, "interfaces", "module")
    keys = [o.key for o in opts]
    assert {"subsystem": "vpn", "module": "core"} in keys
    assert {"subsystem": "ntpclient", "module": "core"} in keys
    core = next(o for o in opts if o.key == {"subsystem": "vpn", "module": "core"})
    assert core.value == "core" and core.name
    sfr = csvdata.lookup(repo, "sfr_obj", "sfr", prefix="FCS_")
    assert sfr and all(o.value.startswith("fcs_") for o in sfr)
    plain = csvdata.lookup(repo, "sfr_module", "relationtype")
    assert len({o.value for o in plain}) == len(plain)


# ------------------------------------------------------------- validation


def test_delete_referenced_row_is_refused(repo):
    before = snapshot(repo)
    with pytest.raises(ReferencedRowError) as exc:
        csvdata.delete_row(repo, "sfr", {"label": "fcs_ckm.1"})
    refs = exc.value.details["referenced_by"]
    assert {"sfr_module", "sfr_obj"} <= {r["table"] for r in refs}
    assert all(r["line"] for r in refs)
    assert snapshot(repo) == before


def test_update_of_referenced_key_is_refused(repo):
    with pytest.raises(ReferencedRowError, match="rename_key"):
        csvdata.update_row(repo, "modules", {"subsystem": "vpn", "label": "core"}, {"label": "x"})


def test_insert_with_unknown_composite_key_is_refused(repo):
    # 'vpn' and 'keymgmt' exist, but not as the pair (vpn, keymgmt)
    with pytest.raises(ForeignKeyError) as exc:
        csvdata.insert_row(
            repo, "interfaces", {"subsystem": "vpn", "module": "keymgmt", "label": "x", "name": "X"}
        )
    assert exc.value.details["ref_table"] == "modules"
    csvdata.insert_row(
        repo, "interfaces", {"subsystem": "vpn", "module": "core", "label": "x", "name": "X"}
    )


def test_existing_violation_does_not_block_unrelated_edits(repo):
    # interfaces.csv already holds (nn, nn), which is not a module
    assert any(
        v.kind == "foreign_key" and v.values == ("nn", "nn")
        for v in csvdata.violations(*csvdata._load(repo))
    )
    csvdata.insert_row(
        repo, "interfaces", {"subsystem": "vpn", "module": "core", "label": "y", "name": "Y"}
    )


def test_duplicate_and_empty_primary_key(repo):
    with pytest.raises(DuplicateKeyError):
        csvdata.insert_row(repo, "sfr", {"label": "fcs_ckm.1", "name": "x"})
    with pytest.raises(InvalidValueError):
        csvdata.insert_row(repo, "sfr", {"name": "no label"})


@pytest.mark.parametrize(
    ("values", "msg"),
    [
        ({"description": "a\nb"}, "line breaks"),
        ({"description": 3}, "must be text"),
        ({"bogus": "x"}, "unknown column"),
    ],
)
def test_invalid_values(repo, values, msg):
    with pytest.raises(InvalidValueError, match=msg):
        csvdata.update_row(repo, "sf", {"label": "sf.cryptographicservices"}, values)


def test_key_column_rejects_separator(repo):
    with pytest.raises(InvalidValueError, match="key column"):
        csvdata.insert_row(repo, "sf", {"label": "a;b", "name": "x"})


def test_match_errors(repo):
    with pytest.raises(RowNotFoundError):
        csvdata.delete_row(repo, "sfr", {"label": "missing"})
    with pytest.raises(AmbiguousMatchError) as exc:
        csvdata.delete_row(repo, "sfr_obj", {"sfr": "fcs_ckm.1"})
    assert exc.value.details["occurrences"] > 1
    with pytest.raises(InvalidValueError):
        csvdata.delete_row(repo, "sfr", {})


def test_stale_expected_hash(repo):
    sha = csvdata.read_table(repo, "sf").sha256
    csvdata.update_row(
        repo, "sf", {"label": "sf.cryptographicservices"}, {"name": "A"}, expected_hash=sha
    )
    with pytest.raises(StaleWriteError):
        csvdata.update_row(
            repo, "sf", {"label": "sf.cryptographicservices"}, {"name": "B"}, expected_hash=sha
        )


def test_identical_update_is_refused(repo):
    row = csvdata.read_table(repo, "sf", {"label": "sf.cryptographicservices"}).rows[0]
    with pytest.raises(InvalidValueError, match="identical"):
        csvdata.update_row(
            repo, "sf", {"label": "sf.cryptographicservices"}, {"name": row.values["name"]}
        )


# ------------------------------------------------------------------ rename


def test_rename_module_updates_references(repo):
    before = snapshot(repo)
    res = csvdata.rename_key(
        repo, "modules", {"subsystem": "vpn", "label": "core"}, {"label": "engine"}
    )
    assert res.old_key == {"subsystem": "vpn", "label": "core"}
    assert res.new_key == {"subsystem": "vpn", "label": "engine"}
    changed = {f.path.rsplit("/", 1)[1] for f in res.files}
    assert changed == {k for k in before if before[k] != snapshot(repo)[k]}
    assert {"modules.csv", "interfaces.csv", "sfr_module.csv", "testcase_module.csv"} <= changed
    assert "bundle_module.csv" in changed  # openvpn -> (vpn, core)
    for table in ("interfaces", "sfr_module", "testcase_module", "bundle_module"):
        rows = csvdata.read_table(repo, table, {"subsystem": "vpn"}).rows
        assert all(r.values["module"] != "core" for r in rows), table
    # other subsystems' 'core' modules are untouched
    assert csvdata.read_table(repo, "modules", {"subsystem": "tls", "label": "core"}).rows
    assert not [v for v in csvdata.validate_db(repo).issues if v.severity == "error"]

    refs = {(r.key, r.replacement) for r in res.tex_references}
    assert ("mod.vpn.core", "mod.vpn.engine") in refs
    assert all(r.path.endswith(".tex") and r.line > 0 for r in res.tex_references)
    assert all(r.key.startswith(("mod.vpn.core", "int.vpn.core.")) for r in res.tex_references)


def test_rename_simple_key(repo):
    res = csvdata.rename_key(repo, "sfr", {"label": "fcs_ckm.1"}, {"label": "fcs_ckm.9"})
    assert any(f.path.endswith("sfr_obj.csv") for f in res.files)
    assert not csvdata.read_table(repo, "sfr_obj", {"sfr": "fcs_ckm.1"}).rows
    assert any(r.replacement == "fcs_ckm.9" for r in res.tex_references) or not res.tex_references


def test_rename_errors(repo):
    with pytest.raises(InvalidValueError, match="primary key"):
        csvdata.rename_key(repo, "sfr", {"label": "fcs_ckm.1"}, {"name": "x"})
    with pytest.raises(InvalidValueError, match="no primary key"):
        csvdata.rename_key(repo, "sfr_obj", {"sfr": "fcs_ckm.1", "obj": "x"}, {"sfr": "y"})
    with pytest.raises(DuplicateKeyError):
        csvdata.rename_key(repo, "sfr", {"label": "fcs_ckm.1"}, {"label": "fcs_cop.1.1/hash"})
    with pytest.raises(ForeignKeyError):
        csvdata.rename_key(
            repo, "modules", {"subsystem": "vpn", "label": "core"}, {"subsystem": "nosuch"}
        )


def test_rename_rolls_back_on_write_failure(repo, monkeypatch):
    before = snapshot(repo)
    real = files._atomic_write
    calls = []

    def flaky(path, data):
        calls.append(path)
        if len(calls) == 3:
            raise OSError("disk full")
        real(path, data)

    monkeypatch.setattr(files, "_atomic_write", flaky)
    with pytest.raises(OSError):
        csvdata.rename_key(repo, "modules", {"subsystem": "vpn", "label": "core"}, {"label": "e"})
    assert snapshot(repo) == before


def test_tds_key_renaming_rules():
    r = csvdata._renamed
    assert r("subsystems", "sub.vpn", ("vpn",), ("net",)) == "sub.net"
    assert r("subsystems", "int.vpn.core.c", ("vpn",), ("net",)) == "int.net.core.c"
    assert r("modules", "sub.vpn", ("vpn", "core"), ("vpn", "e")) is None
    assert r("modules", "mod.vpn.cores", ("vpn", "core"), ("vpn", "e")) is None
    assert r("interfaces", "int.a.b.c", ("a", "b", "c"), ("a", "b", "d")) == "int.a.b.d"
    assert r("sfr", "FCS_CKM.1", ("fcs_ckm.1",), ("x",)) == "x"


# ------------------------------------------------------------- validate_db


def test_validate_db_real_repository_has_no_errors(real_repo):
    report = csvdata.validate_db(real_repo)
    assert report.ok, [i for i in report.issues if i.severity == "error"]
    assert any(i.code == "csv_foreign_key" for i in report.issues)  # (nn, nn), a warning


def test_validate_db_reports_new_violation_as_error(repo):
    path = repo.root / DB / "sfr_obj.csv"
    path.write_bytes(path.read_bytes() + b"nosuch;o.tlscrypto\n")
    report = csvdata.validate_db(repo)
    errors = [i for i in report.issues if i.severity == "error"]
    assert len(errors) == 1 and errors[0].path == f"{DB}/sfr_obj.csv"
    assert errors[0].code == "csv_foreign_key" and errors[0].line
    # without a baseline the old (nn, nn) violation is an error too
    assert len([i for i in csvdata.validate_db(repo, None).issues if i.severity == "error"]) == 2


def test_validate_db_reports_parse_error(repo):
    path = repo.root / DB / "sf.csv"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    report = csvdata.validate_db(repo)
    assert not report.ok and report.issues[0].code == "csv_invalid"


def test_git_show_file(repo):
    assert git.show_file(repo, "HEAD", f"{DB}/sf.csv") == raw(repo, "sf").decode()
    assert git.show_file(repo, "HEAD", f"{DB}/new.csv") is None
