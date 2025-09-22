"""
Pytest configuration and shared fixtures for Smart Scout App tests.
"""

import os
import sys
import pytest
import django
from django.conf import settings
from django.test import TestCase
from django.contrib.auth import get_user_model
from factory import Faker, SubFactory
from factory.django import DjangoModelFactory
from unittest.mock import Mock, patch
import tempfile
import shutil

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

User = get_user_model()


# =============================================================================
# FACTORIES
# =============================================================================

class UserFactory(DjangoModelFactory):
    """Factory for creating test users."""
    
    class Meta:
        model = User
    
    username = Faker('user_name')
    email = Faker('email')
    name = Faker('first_name')
    surname = Faker('last_name')
    is_active = True
    is_staff = False
    is_superuser = False


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """Configure test database for the entire test session."""
    with django_db_blocker.unblock():
        # Create any necessary test data here
        pass


@pytest.fixture
def user():
    """Create a test user."""
    return UserFactory()


@pytest.fixture
def admin_user():
    """Create an admin user."""
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def authenticated_client(client, user):
    """Create an authenticated client."""
    client.force_login(user)
    return client


@pytest.fixture
def temp_media_root():
    """Create a temporary media root for file upload tests."""
    temp_dir = tempfile.mkdtemp()
    original_media_root = settings.MEDIA_ROOT
    settings.MEDIA_ROOT = temp_dir
    
    yield temp_dir
    
    # Cleanup
    settings.MEDIA_ROOT = original_media_root
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_openai():
    """Mock OpenAI API calls."""
    with patch('openai.OpenAI') as mock_openai:
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        # Mock chat completions
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_client.chat.completions.create.return_value = mock_response
        
        yield mock_client


@pytest.fixture
def mock_requests():
    """Mock requests library for external API calls."""
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_get.return_value = mock_response
        yield mock_get


@pytest.fixture
def sample_player_data():
    """Sample player data for testing."""
    return {
        'id': 1,
        'full_name': 'Lionel Messi',
        'team': 'Inter Miami',
        'position': 'FW',
        'age': 36,
        'nationality': 'Argentina',
        'goals': 25,
        'assists': 15,
        'minutes': 2500,
        'goals_per90': 0.9,
        'assists_per90': 0.54
    }


@pytest.fixture
def sample_news_data():
    """Sample news data for testing."""
    return {
        'title': 'Messi scores hat-trick in MLS',
        'content': 'Lionel Messi scored three goals in Inter Miami\'s victory...',
        'url': 'https://example.com/news/messi-hat-trick',
        'published_date': '2024-01-15T10:30:00Z',
        'source': 'ESPN'
    }


# =============================================================================
# CUSTOM MARKERS
# =============================================================================

def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests"
    )
    config.addinivalue_line(
        "markers", "api: API tests"
    )
    config.addinivalue_line(
        "markers", "slow: Slow running tests"
    )
    config.addinivalue_line(
        "markers", "validation: Data validation tests"
    )


# =============================================================================
# UTILITIES
# =============================================================================

class TestDataMixin:
    """Mixin class with common test data and utilities."""
    
    @staticmethod
    def create_sample_players(count=5):
        """Create sample player data for testing."""
        players = []
        for i in range(count):
            players.append({
                'id': i + 1,
                'full_name': f'Player {i + 1}',
                'team': f'Team {i + 1}',
                'position': ['GK', 'DF', 'MF', 'FW'][i % 4],
                'age': 20 + i,
                'nationality': 'Test Country',
                'goals': i * 2,
                'assists': i,
                'minutes': 2000 + i * 100,
                'goals_per90': (i * 2) / 90,
                'assists_per90': i / 90
            })
        return players
    
    @staticmethod
    def create_sample_news(count=3):
        """Create sample news data for testing."""
        news = []
        for i in range(count):
            news.append({
                'title': f'News Title {i + 1}',
                'content': f'This is news content {i + 1}...',
                'url': f'https://example.com/news/{i + 1}',
                'published_date': f'2024-01-{15 + i}T10:30:00Z',
                'source': 'Test Source'
            })
        return news
