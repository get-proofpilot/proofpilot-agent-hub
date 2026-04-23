"""Smoke test stub — replace with real tests.

Every agent folder ships with at least one test so `pytest backend/agents`
has something to discover. Keeps the test pipeline green even before real
coverage lands.
"""


def test_manifest_shape():
    from agents._template import manifest

    assert manifest.id
    assert manifest.route_prefix.startswith("/api/")
