"""
Simple API tests for FastAPI endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

# Import the FastAPI app
from apps.agent_service.main import app

client = TestClient(app)


class TestBasicEndpoints:
    """Test cases for basic API endpoints."""
    
    def test_app_creation(self):
        """Test that the FastAPI app is created correctly."""
        assert app is not None
        assert app.title == "Smart-Scout API"
    
    def test_app_has_routers(self):
        """Test that the app has the expected routers."""
        routes = [route.path for route in app.routes]
        assert "/players" in str(routes)
        assert "/news" in str(routes)
        assert "/chat" in str(routes)
    
    def test_players_router_exists(self):
        """Test that players router is included."""
        response = client.get("/players/1/similar")
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_news_router_exists(self):
        """Test that news router is included."""
        response = client.get("/news/players/1/news")
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_chat_router_exists(self):
        """Test that chat router is included."""
        response = client.post("/chat", json={"message": "test"})
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404


class TestPlayerEndpoints:
    """Test cases for player-related API endpoints."""
    
    def test_similar_players_endpoint_exists(self):
        """Test that similar players endpoint exists."""
        response = client.get("/players/1/similar")
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_similar_players_with_filters(self):
        """Test similar players endpoint with filters."""
        response = client.get("/players/1/similar?position=FW&limit=5")
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_similar_players_invalid_player_id(self):
        """Test similar players with invalid player ID."""
        response = client.get("/players/invalid/similar")
        # Should return 422 (validation error) or 404
        assert response.status_code in [404, 422]


class TestNewsEndpoints:
    """Test cases for news-related API endpoints."""
    
    def test_news_by_player_endpoint_exists(self):
        """Test that news by player endpoint exists."""
        response = client.get("/news/players/1/news")
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_news_by_player_with_limit(self):
        """Test news by player endpoint with limit."""
        response = client.get("/news/players/1/news?k=5")
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_search_news_endpoint_exists(self):
        """Test that search news endpoint exists."""
        response = client.get("/news/search?query=football")
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404


class TestChatEndpoints:
    """Test cases for chat-related API endpoints."""
    
    def test_chat_endpoint_exists(self):
        """Test that chat endpoint exists."""
        response = client.post("/chat", json={"message": "test"})
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_chat_endpoint_invalid_json(self):
        """Test chat endpoint with invalid JSON."""
        response = client.post("/chat", data="invalid json")
        # Should return 422 (validation error)
        assert response.status_code == 422
    
    def test_chat_endpoint_missing_message(self):
        """Test chat endpoint with missing message."""
        response = client.post("/chat", json={})
        # Should return 422 (validation error)
        assert response.status_code == 422


class TestErrorHandling:
    """Test cases for error handling."""
    
    def test_404_error(self):
        """Test 404 error for non-existent endpoint."""
        response = client.get("/non-existent-endpoint")
        assert response.status_code == 404
    
    def test_422_error_invalid_data(self):
        """Test 422 error for invalid request data."""
        response = client.post("/chat", json={"invalid_field": "invalid_value"})
        assert response.status_code == 422


class TestAPIDocumentation:
    """Test cases for API documentation."""
    
    def test_openapi_schema_exists(self):
        """Test that OpenAPI schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert "openapi" in response.json()
    
    def test_docs_endpoint_exists(self):
        """Test that docs endpoint is available."""
        response = client.get("/docs")
        assert response.status_code == 200
    
    def test_redoc_endpoint_exists(self):
        """Test that ReDoc endpoint is available."""
        response = client.get("/redoc")
        assert response.status_code == 200
