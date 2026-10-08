import json

import pytest

from ndoc_core import files

pytestmark = pytest.mark.anyio

BODY = "mwe_tds/mwe_tds_body.tex"
EXTRA = "mwe_tds/mwe_tds_extra.tex"

EXPECTED_TOOLS = {
    "list_documents",
    "document_tree",
    "list_files",
    "search",
    "read_file",
    "edit_file",
    "write_file",
    "run_checks",
    "run_build",
    "list_build_targets",
    "git_status",
    "git_diff",
    "git_log",
    "git_create_branch",
    "git_switch_branch",
    "git_commit",
}


async def call(client, tool, /, **args):
    res = await client.call_tool(tool, args)
    assert not res.is_error, res.content
    return res.structured_content.get("result", res.structured_content)


async def call_error(client, tool, /, **args) -> dict:
    res = await client.call_tool(tool, args)
    assert res.is_error
    text = res.content[0].text  # "Error executing tool <name>: {json}"
    return json.loads(text[text.index("{") :])


async def test_tools_and_annotations(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == EXPECTED_TOOLS
    assert tools["read_file"].annotations.read_only_hint
    assert not tools["git_commit"].annotations.read_only_hint
    assert tools["edit_file"].input_schema["required"] == ["path", "old_text", "new_text"]


async def test_documents_and_tree(client):
    names = [d["name"] for d in await call(client, "list_documents")]
    assert "adv_tds" in names and "mwe_tds" in names
    tree = await call(client, "document_tree", document="mwe_tds")
    paths = [c["path"] for c in tree["children"]]
    assert BODY in paths


async def test_read_edit_roundtrip_with_checks(client, repo):
    content = await call(client, "read_file", path=EXTRA)
    assert content["text"] == "Extra text.\n"
    res = await call(
        client,
        "edit_file",
        path=EXTRA,
        old_text="Extra text.",
        new_text=r"Extra text, see \sfrlink{fcs_ckm.1}.",
        expected_sha256=content["sha256"],
    )
    assert res["replacements"] == 1
    assert res["checks"]["ok"]
    assert res["sha256"] == files.read_file(repo, EXTRA).sha256


async def test_edit_reports_broken_reference(client):
    res = await call(client, "edit_file", path=EXTRA, old_text="Extra", new_text=r"\sfrlink{nope}")
    assert not res["checks"]["ok"]
    assert res["checks"]["issues"][0]["code"] == "undefined_reference"
    assert res["checks"]["issues"][0]["line"] == 1


async def test_write_requires_matching_hash(client, repo):
    err = await call_error(client, "write_file", path=EXTRA, content="x\n")
    assert err["code"] == "stale_write"
    sha = files.read_file(repo, EXTRA).sha256
    res = await call(client, "write_file", path=EXTRA, content="x\n", expected_sha256=sha)
    assert res["checks"]["ok"]
    res = await call(client, "write_file", path="mwe_tds/new.tex", content="New\n", create=True)
    assert res["created"]


@pytest.mark.parametrize(
    ("tool", "args", "code"),
    [
        ("read_file", {"path": "../etc/passwd"}, "path_not_allowed"),
        ("read_file", {"path": "web/mcp/pyproject.toml"}, "path_not_allowed"),
        (
            "write_file",
            {"path": "scripts/x.tex", "content": "", "create": True},
            "path_not_allowed",
        ),
        ("edit_file", {"path": EXTRA, "old_text": "nope", "new_text": "x"}, "text_not_found"),
        ("run_build", {"target": "foo; rm -rf /"}, "build_target_not_allowed"),
        ("document_tree", {"document": "common"}, "unknown_document"),
        ("git_create_branch", {"name": "main"}, "protected_branch"),
        ("git_commit", {"message": "m", "paths": [".git/config"]}, "path_not_allowed"),
    ],
)
async def test_core_errors_become_tool_errors(client, tool, args, code):
    err = await call_error(client, tool, **args)
    assert err["code"] == code
    assert err["message"]


async def test_search(client):
    res = await call(client, "search", pattern="fcs_ckm.1", directory="mwe_tds")
    assert [(m["path"], m["line"]) for m in res["matches"]] == [(BODY, 2)]


async def test_run_checks_defaults_to_changed_files(client, repo):
    assert (await call(client, "run_checks"))["checked"] == []
    (repo.root / EXTRA).write_text("\\begin{itemize}\n", encoding="utf-8")
    res = await call(client, "run_checks")
    assert res["checked"] == [EXTRA]
    assert not res["ok"]
    assert res["issues"][0]["code"] == "unclosed_env"
    res = await call(client, "run_checks", document="mwe_tds")
    assert EXTRA in res["checked"] and not res["ok"]


async def test_branch_edit_commit_flow(client, repo):
    await call(client, "git_switch_branch", name="main")
    assert (await call(client, "git_status"))["branch"] == "main"
    await call(client, "edit_file", path=EXTRA, old_text="Extra", new_text="Changed")
    err = await call_error(client, "git_commit", message="edit", paths=[EXTRA])
    assert err["code"] == "protected_branch"

    await call(client, "git_create_branch", name="agent/edit-extra")
    diff = await call(client, "git_diff", paths=[EXTRA])
    assert "-Extra text." in diff and "+Changed text." in diff
    res = await call(client, "git_commit", message="Change extra text", paths=[EXTRA])
    assert res["branch"] == "agent/edit-extra" and len(res["sha"]) == 40
    st = await call(client, "git_status")
    assert st["clean"]
    log = await call(client, "git_log", limit=1)
    assert log[0]["subject"] == "Change extra text"
    assert await call(client, "git_diff") == "(no changes)"


async def test_build_targets(client):
    targets = await call(client, "list_build_targets")
    assert {"tds", "st", "mwe_tds", "clean"} <= set(targets)


@pytest.mark.docker
async def test_run_build_real(client):
    res = await call(client, "run_build", target="mwe_tds")
    assert res["ok"], res["log_tail"]
    assert res["pdfs"] == ["mwe_tds/mwe_tds.pdf"]
    assert res["pdf_checks"]["checked"] == ["mwe_tds/mwe_tds.pdf"]
