import pytest
from conftest import git as raw_git

from ndoc_core import git
from ndoc_core.errors import (
    DirtyWorktreeError,
    GitError,
    InvalidBranchNameError,
    PathNotAllowedError,
    ProtectedBranchError,
)

BODY = "mwe_tds/mwe_tds_body.tex"
EXTRA = "mwe_tds/mwe_tds_extra.tex"


def append(repo, rel, text="more\n"):
    path = repo.root / rel
    path.write_text(path.read_text() + text)


def test_status_clean(repo):
    st = git.status(repo)
    assert st.branch == "work"
    assert st.upstream is None
    assert st.clean


def test_status_lists_changes(repo):
    append(repo, BODY)
    (repo.root / "mwe_tds/new.tex").write_text("x")
    st = git.status(repo)
    by_path = {f.path: f for f in st.files}
    assert by_path[BODY].worktree == "M"
    assert by_path["mwe_tds/new.tex"].untracked


def test_status_rename(repo):
    raw_git(repo.root, "mv", EXTRA, "mwe_tds/renamed.tex")
    [entry] = git.status(repo).files
    assert (entry.index, entry.path, entry.orig_path) == ("R", "mwe_tds/renamed.tex", EXTRA)


def test_diff(repo):
    append(repo, BODY, "Neuer Satz.\n")
    out = git.diff(repo)
    assert "+Neuer Satz." in out
    assert git.diff(repo, [EXTRA]) == ""
    assert "+Neuer Satz." in git.diff(repo, [BODY])


def test_diff_against_base(repo):
    append(repo, BODY, "Neuer Satz.\n")
    git.commit(repo, "change", [BODY])
    assert "+Neuer Satz." in git.diff(repo, base="main")


@pytest.mark.parametrize("bad", ["--output=/tmp/x", "-p", "main;ls", "nope-branch"])
def test_diff_rejects_bad_revisions(repo, bad):
    with pytest.raises(GitError):
        git.diff(repo, base=bad)


def test_diff_path_guard(repo):
    with pytest.raises(PathNotAllowedError):
        git.diff(repo, ["../outside.tex"])


def test_commit_only_given_paths(repo):
    append(repo, BODY)
    append(repo, EXTRA)
    raw_git(repo.root, "add", EXTRA)  # staged, but not part of this commit
    sha = git.commit(repo, "docs: extend body", [BODY])
    assert len(sha) == 40
    changed = raw_git(repo.root, "show", "--name-only", "--format=", sha).split()
    assert changed == [BODY]
    remaining = {f.path for f in git.status(repo).files}
    assert remaining == {EXTRA}
    assert git.log(repo, 1)[0].subject == "docs: extend body"


def test_commit_new_and_deleted_files(repo):
    (repo.root / "mwe_tds/new.tex").write_text("neu\n")
    (repo.root / EXTRA).unlink()
    sha = git.commit(repo, "add and remove", ["mwe_tds/new.tex", EXTRA])
    out = raw_git(repo.root, "show", "--name-status", "--format=", sha)
    assert "A\tmwe_tds/new.tex" in out
    assert f"D\t{EXTRA}" in out
    assert git.status(repo).clean


def test_commit_with_author(repo):
    append(repo, BODY)
    git.commit(repo, "x", [BODY], author="Ada Editor <ada@example.com>")
    assert git.log(repo, 1)[0].author == "Ada Editor"


@pytest.mark.parametrize("author", ["no email", "A <b>", "A <a@b>\nInjected: x"])
def test_commit_rejects_bad_author(repo, author):
    append(repo, BODY)
    with pytest.raises(GitError):
        git.commit(repo, "x", [BODY], author=author)


@pytest.mark.parametrize(
    "paths", [[], [".git/config"], ["../x.tex"], ["web/x.md"], ["scripts/check_sfr_consistency.sh"]]
)
def test_commit_rejects_bad_paths(repo, paths):
    with pytest.raises((GitError, PathNotAllowedError)):
        git.commit(repo, "x", paths)


def test_commit_rejects_empty_message(repo):
    append(repo, BODY)
    with pytest.raises(GitError):
        git.commit(repo, "   ", [BODY])


def test_commit_refused_on_protected_branch(repo):
    raw_git(repo.root, "switch", "-q", "main")
    append(repo, BODY)
    with pytest.raises(ProtectedBranchError):
        git.commit(repo, "x", [BODY])


def test_create_and_switch_branch(repo):
    git.create_branch(repo, "agent/session-1")
    assert git.current_branch(repo) == "agent/session-1"
    assert "agent/session-1" in git.list_branches(repo)
    git.switch_branch(repo, "work")
    assert git.current_branch(repo) == "work"


def test_create_branch_from_start_point(repo):
    git.create_branch(repo, "from-main", start="main", checkout=False)
    assert git.current_branch(repo) == "work"
    assert "from-main" in git.list_branches(repo)


@pytest.mark.parametrize(
    "bad", ["-x", "a..b", "a b", "x.lock", "a//b", "", "a~1", "@{-1}", "trailing/"]
)
def test_invalid_branch_names(repo, bad):
    with pytest.raises(InvalidBranchNameError):
        git.create_branch(repo, bad)


def test_cannot_create_protected_branch_name(repo):
    with pytest.raises(ProtectedBranchError):
        git.create_branch(repo, "master")


def test_switch_requires_clean_tree(repo):
    append(repo, BODY)
    with pytest.raises(DirtyWorktreeError):
        git.switch_branch(repo, "main")


def test_switch_to_unknown_branch(repo):
    with pytest.raises(GitError):
        git.switch_branch(repo, "does-not-exist")


def test_log(repo):
    commits = git.log(repo, 5)
    assert [c.subject for c in commits] == ["fixture"]
    assert git.log(repo, 5, path=BODY)[0].subject == "fixture"
