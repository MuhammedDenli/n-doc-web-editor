import pytest

from ndoc_mcp import cli

EXTRA = "mwe_tds/mwe_tds_extra.tex"


@pytest.fixture(autouse=True)
def _repo_env(repo, monkeypatch):
    monkeypatch.setenv("NDOC_REPO", str(repo.root))
    monkeypatch.chdir(repo.root)


def test_clean_file_passes(repo, capsys):
    assert cli.run([str(repo.root / EXTRA)]) == 0
    assert capsys.readouterr().err == ""


def test_errors_exit_2_with_locations(repo, capsys):
    (repo.root / EXTRA).write_text("ok\n\\sfrlink{nope}\n", encoding="utf-8")
    assert cli.run([EXTRA]) == 2
    err = capsys.readouterr().err
    assert f"{EXTRA}:2:1: [undefined_reference]" in err


@pytest.mark.parametrize(
    "arg", ["/etc/hosts", "web/mcp/pyproject.toml", "scripts/check_sfr_consistency.sh", "Makefile"]
)
def test_non_content_files_are_ignored(arg):
    assert cli.run([arg]) == 0


def test_csv_runs_sfr_consistency(repo, capsys):
    sfr_module = repo.root / "common/db/sfr_module.csv"
    sfr_module.write_text(sfr_module.read_text() + "fxx_yyy.1;vpn;core\n", encoding="utf-8")
    assert cli.run(["common/db/sfr_module.csv"]) == 2
    assert "sfr_inconsistent" in capsys.readouterr().err


def test_csv_foreign_key_violation_exits_2(repo, capsys):
    sfr_obj = repo.root / "common/db/sfr_obj.csv"
    sfr_obj.write_text(sfr_obj.read_text() + "fcs_ckm.1;o.nosuch\n", encoding="utf-8")
    assert cli.run(["common/db/sfr_obj.csv"]) == 2
    err = capsys.readouterr().err
    assert "[csv_foreign_key]" in err and "o.nosuch" in err
    assert "found 1 error(s)" in err  # the (nn, nn) row already at HEAD is only a warning


def test_unchanged_csv_passes(repo, capsys):
    assert cli.run(["common/db/interfaces.csv"]) == 0
