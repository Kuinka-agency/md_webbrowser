from app.main import _demo_manifest_payload


def test_demo_manifest_contains_warnings_and_blocklist():
    payload = _demo_manifest_payload()

    warnings = payload.get("warnings", [])
    hits = payload.get("blocklist_hits", {})

    assert warnings, "demo manifest should include warning entries"
    codes = {entry["code"] for entry in warnings}
    assert "canvas-heavy" in codes

    assert hits.get("#onetrust-consent-sdk") == 2
    assert payload.get("blocklist_version")
