import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Import lazily to avoid heavy imports at collection time
    from apps.agent_service.main import app
    return TestClient(app)


def test_similar_team_fit_not_found(client):
    r = client.get("/players/999999/similar_team_fit", params={"team": "FC Test"})
    assert r.status_code == 404


def test_similar_team_fit_ok_empty_cohort(client, monkeypatch):
    """If no cohort exists for the target team+position, endpoint should still return candidates
    with team_position_similarity as None and success_index equal to overall_similarity.
    This test stubs DB responses indirectly by calling an ID likely to exist in seed data is not guaranteed,
    so we only assert schema keys when 200.
    """
    # Try a small ID range; the endpoint returns 200 for existing ids. If not, skip.
    for test_id in (1, 2, 3, 10, 50):
        r = client.get(f"/players/{test_id}/similar_team_fit", params={"team": "__unlikely_team__", "k": 3})
        if r.status_code == 200:
            data = r.json()
            assert "context" in data and "candidates" in data
            assert "cohort_size" in data["context"]
            # candidates can be empty; if present, assert keys
            for c in data.get("candidates", []):
                assert set(["id", "full_name", "club", "position", "overall_similarity", "team_position_similarity", "success_index"]).issubset(c.keys())
            break
    else:
        pytest.skip("No sample player id available in test environment")


