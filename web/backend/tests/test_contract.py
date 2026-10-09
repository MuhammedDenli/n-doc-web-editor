import json

from ndoc_api.cli import CONTRACT, openapi_json


def test_contract_is_up_to_date():
    """web/contracts/openapi.json is what the app serves (ndoc-api export-openapi)."""
    assert json.loads(CONTRACT.read_text(encoding="utf-8")) == json.loads(openapi_json())


def test_served_spec_matches_contract(anon):
    assert anon.get("/api/openapi.json").json() == json.loads(CONTRACT.read_text())
