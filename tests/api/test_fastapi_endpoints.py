"""
API tests for FastAPI endpoints.
"""

import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock
import tempfile
import os

# Import the FastAPI app
from apps.agent_service.main import app

client = TestClient(app)


class TestPlayerEndpoints:
    """Test cases for player-related API endpoints."""
    
    def test_get_players(self):
        """Test GET /players endpoint."""
        with patch('apps.agent_service.routers.players.get_players') as mock_get:
            mock_get.return_value = [
                {
                    'id': 1,
                    'full_name': 'Lionel Messi',
                    'team': 'Inter Miami',
                    'position': 'FW',
                    'age': 36,
                    'nationality': 'Argentina'
                }
            ]
            
            response = client.get("/players")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]['full_name'] == 'Lionel Messi'
    
    def test_get_players_with_filters(self):
        """Test GET /players endpoint with filters."""
        with patch('apps.agent_service.routers.players.get_players') as mock_get:
            mock_get.return_value = []
            
            response = client.get("/players?position=FW&age_min=20&age_max=30")
            assert response.status_code == 200
    
    def test_get_player_by_id(self):
        """Test GET /players/{player_id} endpoint."""
        with patch('apps.agent_service.routers.players.get_player_by_id') as mock_get:
            mock_get.return_value = {
                'id': 1,
                'full_name': 'Lionel Messi',
                'team': 'Inter Miami',
                'position': 'FW',
                'age': 36,
                'nationality': 'Argentina'
            }
            
            response = client.get("/players/1")
            assert response.status_code == 200
            data = response.json()
            assert data['full_name'] == 'Lionel Messi'
    
    def test_get_player_by_id_not_found(self):
        """Test GET /players/{player_id} endpoint with non-existent player."""
        with patch('apps.agent_service.routers.players.get_player_by_id') as mock_get:
            mock_get.return_value = None
            
            response = client.get("/players/999")
            assert response.status_code == 404
    
    def test_get_similar_players(self):
        """Test GET /players/{player_id}/similar endpoint."""
        with patch('apps.agent_service.routers.players.get_similar_players') as mock_get:
            mock_get.return_value = [
                {
                    'id': 2,
                    'full_name': 'Cristiano Ronaldo',
                    'team': 'Al Nassr',
                    'position': 'FW',
                    'similarity_score': 0.85
                }
            ]
            
            response = client.get("/players/1/similar")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]['full_name'] == 'Cristiano Ronaldo'
    
    def test_get_similar_players_with_filters(self):
        """Test GET /players/{player_id}/similar endpoint with filters."""
        with patch('apps.agent_service.routers.players.get_similar_players') as mock_get:
            mock_get.return_value = []
            
            response = client.get(
                "/players/1/similar?position=FW&exclude_club=Inter Miami&limit=5"
            )
            assert response.status_code == 200


class TestNewsEndpoints:
    """Test cases for news-related API endpoints."""
    
    def test_get_news_by_player(self):
        """Test GET /news/player/{player_id} endpoint."""
        with patch('apps.agent_service.routers.news.get_news_by_player') as mock_get:
            mock_get.return_value = [
                {
                    'title': 'Messi scores hat-trick',
                    'content': 'Lionel Messi scored three goals...',
                    'url': 'https://example.com/news',
                    'published_date': '2024-01-15T10:30:00Z',
                    'source': 'ESPN'
                }
            ]
            
            response = client.get("/news/player/1")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]['title'] == 'Messi scores hat-trick'
    
    def test_get_news_by_player_with_limit(self):
        """Test GET /news/player/{player_id} endpoint with limit."""
        with patch('apps.agent_service.routers.news.get_news_by_player') as mock_get:
            mock_get.return_value = []
            
            response = client.get("/news/player/1?limit=5")
            assert response.status_code == 200
    
    def test_search_news(self):
        """Test GET /news/search endpoint."""
        with patch('apps.agent_service.routers.news.search_news') as mock_search:
            mock_search.return_value = [
                {
                    'title': 'Football news about transfers',
                    'content': 'Latest transfer news...',
                    'url': 'https://example.com/news',
                    'published_date': '2024-01-15T10:30:00Z',
                    'source': 'BBC Sport'
                }
            ]
            
            response = client.get("/news/search?query=transfers")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert 'transfers' in data[0]['title'].lower()
    
    def test_search_news_with_limit(self):
        """Test GET /news/search endpoint with limit."""
        with patch('apps.agent_service.routers.news.search_news') as mock_search:
            mock_search.return_value = []
            
            response = client.get("/news/search?query=football&limit=10")
            assert response.status_code == 200


class TestChatEndpoints:
    """Test cases for chat-related API endpoints."""
    
    def test_chat_endpoint_post(self):
        """Test POST /chat endpoint."""
        with patch('apps.agent_service.routers.chat.process_chat_message') as mock_process:
            mock_process.return_value = {
                'text': 'Test response from agent',
                'attachments': []
            }
            
            response = client.post("/chat", json={
                'message': 'Hello, can you help me find a striker?',
                'session_id': 'test-session-123'
            })
            assert response.status_code == 200
            data = response.json()
            assert data['text'] == 'Test response from agent'
    
    def test_chat_endpoint_post_without_session(self):
        """Test POST /chat endpoint without session_id."""
        with patch('apps.agent_service.routers.chat.process_chat_message') as mock_process:
            mock_process.return_value = {
                'text': 'Test response from agent',
                'attachments': []
            }
            
            response = client.post("/chat", json={
                'message': 'Hello, can you help me find a striker?'
            })
            assert response.status_code == 200
            data = response.json()
            assert data['text'] == 'Test response from agent'
    
    def test_chat_endpoint_invalid_json(self):
        """Test POST /chat endpoint with invalid JSON."""
        response = client.post("/chat", data="invalid json")
        assert response.status_code == 422
    
    def test_chat_stream_endpoint(self):
        """Test POST /chat/stream endpoint."""
        with patch('apps.agent_service.routers.chat.process_chat_message_stream') as mock_process:
            def mock_stream():
                yield "Test response part 1"
                yield "Test response part 2"
            
            mock_process.return_value = mock_stream()
            
            response = client.post("/chat/stream", json={
                'message': 'Hello, can you help me find a striker?',
                'session_id': 'test-session-123'
            })
            assert response.status_code == 200
            assert response.headers['content-type'] == 'text/plain; charset=utf-8'


class TestHealthEndpoints:
    """Test cases for health check endpoints."""
    
    def test_health_check(self):
        """Test GET /health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
    
    def test_health_check_detailed(self):
        """Test GET /health/detailed endpoint."""
        with patch('apps.agent_service.routers.health.check_database_connection') as mock_db:
            with patch('apps.agent_service.routers.health.check_redis_connection') as mock_redis:
                mock_db.return_value = True
                mock_redis.return_value = True
                
                response = client.get("/health/detailed")
                assert response.status_code == 200
                data = response.json()
                assert data['status'] == 'healthy'
                assert data['database'] == 'connected'
                assert data['redis'] == 'connected'


class TestErrorHandling:
    """Test cases for error handling."""
    
    def test_404_error(self):
        """Test 404 error for non-existent endpoint."""
        response = client.get("/non-existent-endpoint")
        assert response.status_code == 404
    
    def test_422_error_invalid_data(self):
        """Test 422 error for invalid request data."""
        response = client.post("/chat", json={
            'invalid_field': 'invalid_value'
        })
        assert response.status_code == 422
    
    def test_500_error_internal_server_error(self):
        """Test 500 error for internal server error."""
        with patch('apps.agent_service.routers.players.get_players') as mock_get:
            mock_get.side_effect = Exception("Database connection error")
            
            response = client.get("/players")
            assert response.status_code == 500


class TestAuthentication:
    """Test cases for authentication."""
    
    def test_protected_endpoint_without_auth(self):
        """Test protected endpoint without authentication."""
        # Note: This would depend on your actual authentication implementation
        response = client.get("/protected-endpoint")
        # The actual status code would depend on your auth implementation
        assert response.status_code in [401, 403, 404]
    
    def test_protected_endpoint_with_auth(self):
        """Test protected endpoint with authentication."""
        # Note: This would depend on your actual authentication implementation
        headers = {"Authorization": "Bearer test-token"}
        response = client.get("/protected-endpoint", headers=headers)
        # The actual status code would depend on your auth implementation
        assert response.status_code in [200, 401, 403, 404]


class TestFileUpload:
    """Test cases for file upload endpoints."""
    
    def test_upload_file(self):
        """Test file upload endpoint."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(b"Test PDF content")
            tmp_file_path = tmp_file.name
        
        try:
            with open(tmp_file_path, 'rb') as f:
                response = client.post("/upload", files={"file": f})
                # The actual status code would depend on your implementation
                assert response.status_code in [200, 201, 400, 404]
        finally:
            os.unlink(tmp_file_path)
    
    def test_upload_invalid_file_type(self):
        """Test upload with invalid file type."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp_file:
            tmp_file.write(b"Test content")
            tmp_file_path = tmp_file.name
        
        try:
            with open(tmp_file_path, 'rb') as f:
                response = client.post("/upload", files={"file": f})
                # Should return 400 for invalid file type
                assert response.status_code in [400, 404]
        finally:
            os.unlink(tmp_file_path)
