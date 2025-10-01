import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from apps.agent_service.main import app
    return TestClient(app)


@pytest.mark.parametrize(
    "player_id, team, position",
    [
        (1, "Team_A_GK", "GK"),
        (2, "Team_B_DF", "DF"),
        (3, "Team_C_MF", "MF"),
        (4, "Team_D_FW", "FW"),
    ],
)
def test_similar_team_fit_various_positions(client, player_id, team, position):
    r = client.get(f"/players/{player_id}/similar_team_fit", params={"team": team, "position": position, "k": 5})
    # If the player doesn't exist in this environment, we accept 404 and continue
    if r.status_code == 404:
        pytest.skip(f"Player {player_id} not found in this DB instance")
    assert r.status_code == 200
    data = r.json()
    assert "context" in data and "candidates" in data
    assert data["context"]["position"] == position
    assert data["context"]["target_team"] == team
    for c in data.get("candidates", []):
        assert "success_index" in c
        assert "overall_similarity" in c
        assert "id" in c and "full_name" in c


