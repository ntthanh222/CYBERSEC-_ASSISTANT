import json
from pathlib import Path


MANIFEST = Path(__file__).with_name("phase2_contract_manifest.json")


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_contract_manifest_has_required_modes():
    manifest = load_manifest()
    assert set(manifest["mode_notes"]) == {"readiness", "required"}


def test_each_contract_has_identity_and_fields():
    manifest = load_manifest()
    ids = set()
    for contract in manifest["contracts"]:
        assert contract["id"] not in ids
        ids.add(contract["id"])
        assert contract["module"]
        assert contract["endpoint"]
        assert contract["required_response_fields"]


def test_page_and_error_envelopes_are_explicit():
    manifest = load_manifest()
    assert manifest["pagination_envelope"] == ["items", "total", "page", "page_size"]
    assert manifest["error_envelope"] == ["error", "message", "request_id"]


def test_password_contract_is_local_first_by_default():
    manifest = load_manifest()
    password_contract = next(
        item for item in manifest["contracts"] if item["id"] == "password-checker-response"
    )
    assert password_contract["endpoint"] == "LOCAL_FIRST_DEFAULT"
    assert "raw password" in password_contract["privacy"]


if __name__ == "__main__":
    test_contract_manifest_has_required_modes()
    test_each_contract_has_identity_and_fields()
    test_page_and_error_envelopes_are_explicit()
    test_password_contract_is_local_first_by_default()
    print("phase2 contract manifest checks passed")
