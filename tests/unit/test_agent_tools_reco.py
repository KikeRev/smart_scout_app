import types
import sys
import pytest


def test_similar_players_team_fit_tool_smoke(monkeypatch):
    # Arrange: stub heavy ingestion module BEFORE importing tools to avoid external downloads
    dummy_ingest = types.ModuleType("apps.ingestion.seed_and_ingest")
    class DummyPlayer:
        id: int
        full_name: str
        club: str
        position: str
        feature_vector: list[float]
    dummy_ingest.Player = DummyPlayer
    sys.modules["apps.ingestion.seed_and_ingest"] = dummy_ingest

    # Now import tools (safe)
    import apps.agent_service.agents.tools as tools

    class DummyResp:
        def __init__(self, json_data, status_code=200):
            self._json = json_data
            self.status_code = status_code
        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception("http error")
        def json(self):
            return self._json

    def fake_get(url, params=None, timeout=30):
        assert "/players/" in url and url.endswith("/similar_team_fit")
        assert "team" in params
        # minimal shape
        return DummyResp({
            "context": {"base_player_id": 1, "target_team": params["team"], "cohort_size": 0},
            "candidates": []
        })

    monkeypatch.setattr(tools, "requests", type("R", (), {"get": staticmethod(fake_get)}))

    # Act
    out = tools.similar_players_team_fit_tool.run({
        "player_id": 1,
        "team": "MyTeam",
        "k": 5,
        "overall_weight": 0.7
    })

    # Assert
    assert isinstance(out, dict)
    assert "context" in out and out["context"]["target_team"] == "MyTeam"
    assert "candidates" in out


