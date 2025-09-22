"""
Unit tests for Django models.
"""

import pytest
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from apps.dashboard.models import SavedSearch, FootballNews
from tests.conftest import UserFactory

User = get_user_model()


class TestUserModel(TestCase):
    """Test cases for User model."""
    
    def test_user_creation(self):
        """Test basic user creation."""
        user = UserFactory()
        self.assertIsInstance(user, User)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
    
    def test_user_str_representation(self):
        """Test user string representation."""
        user = UserFactory(email="test@example.com")
        self.assertEqual(str(user), "test@example.com")
    
    def test_user_email_uniqueness(self):
        """Test that email must be unique."""
        UserFactory(email="test@example.com")
        with self.assertRaises(IntegrityError):
            UserFactory(email="test@example.com")
    
    def test_user_username_required(self):
        """Test that username is required."""
        with self.assertRaises(ValidationError):
            user = User(
                email="test@example.com",
                name="Test",
                surname="User"
            )
            user.full_clean()
    
    def test_user_name_required(self):
        """Test that name is required."""
        with self.assertRaises(ValidationError):
            user = User(
                username="testuser",
                email="test@example.com",
                surname="User"
            )
            user.full_clean()
    
    def test_user_email_required(self):
        """Test that email is required."""
        with self.assertRaises(ValidationError):
            user = User(
                username="testuser",
                name="Test",
                surname="User"
            )
            user.full_clean()
    
    def test_user_optional_fields(self):
        """Test that optional fields can be empty."""
        user = UserFactory(
            surname="",
            birth_date=None,
            city="",
            country="",
            job_title="",
            favourite_club="",
            avatar=None
        )
        self.assertIsNotNone(user)
        self.assertEqual(user.surname, "")
        self.assertIsNone(user.birth_date)
        self.assertEqual(user.city, "")
        self.assertEqual(user.country, "")
        self.assertEqual(user.job_title, "")
        self.assertEqual(user.favourite_club, "")
        self.assertIsNone(user.avatar)


class TestSavedSearchModel(TestCase):
    """Test cases for SavedSearch model."""
    
    def setUp(self):
        """Set up test data."""
        self.user = UserFactory()
    
    def test_saved_search_creation(self):
        """Test basic saved search creation."""
        search = SavedSearch.objects.create(
            user=self.user,
            name="Test Search",
            search_params={"position": "FW", "age_min": 20},
            selected_players=[1, 2, 3],
            selected_metrics=["goals", "assists"]
        )
        self.assertIsInstance(search, SavedSearch)
        self.assertEqual(search.user, self.user)
        self.assertEqual(search.name, "Test Search")
    
    def test_saved_search_str_representation(self):
        """Test saved search string representation."""
        search = SavedSearch.objects.create(
            user=self.user,
            name="Test Search",
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        expected = f"{self.user.username} - Test Search"
        self.assertEqual(str(search), expected)
    
    def test_saved_search_unique_constraint(self):
        """Test that user cannot have two searches with same name."""
        SavedSearch.objects.create(
            user=self.user,
            name="Test Search",
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        
        with self.assertRaises(IntegrityError):
            SavedSearch.objects.create(
                user=self.user,
                name="Test Search",
                search_params={},
                selected_players=[],
                selected_metrics=[]
            )
    
    def test_saved_search_different_users_same_name(self):
        """Test that different users can have searches with same name."""
        user2 = UserFactory()
        
        search1 = SavedSearch.objects.create(
            user=self.user,
            name="Test Search",
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        
        search2 = SavedSearch.objects.create(
            user=user2,
            name="Test Search",
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        
        self.assertNotEqual(search1, search2)
        self.assertEqual(search1.name, search2.name)
    
    def test_saved_search_json_fields(self):
        """Test JSON field handling."""
        search_params = {"position": "FW", "age_min": 20, "age_max": 30}
        selected_players = [1, 2, 3, 4, 5]
        selected_metrics = ["goals", "assists", "minutes"]
        
        search = SavedSearch.objects.create(
            user=self.user,
            name="Test Search",
            search_params=search_params,
            selected_players=selected_players,
            selected_metrics=selected_metrics
        )
        
        self.assertEqual(search.search_params, search_params)
        self.assertEqual(search.selected_players, selected_players)
        self.assertEqual(search.selected_metrics, selected_metrics)
    
    def test_saved_search_ordering(self):
        """Test that searches are ordered by updated_at descending."""
        search1 = SavedSearch.objects.create(
            user=self.user,
            name="First Search",
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        
        search2 = SavedSearch.objects.create(
            user=self.user,
            name="Second Search",
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        
        searches = list(SavedSearch.objects.all())
        self.assertEqual(searches[0], search2)  # Most recent first
        self.assertEqual(searches[1], search1)


class TestFootballNewsModel(TestCase):
    """Test cases for FootballNews model."""
    
    def test_football_news_creation(self):
        """Test basic football news creation."""
        news = FootballNews.objects.create(
            title="Test News Title",
            published_at="2024-01-15T10:30:00Z",
            summary="Test news summary",
            source_id="test_source_123"
        )
        self.assertIsInstance(news, FootballNews)
        self.assertEqual(news.title, "Test News Title")
    
    def test_football_news_str_representation(self):
        """Test football news string representation."""
        news = FootballNews.objects.create(
            title="Test News Title",
            published_at="2024-01-15T10:30:00Z",
            summary="Test news summary",
            source_id="test_source_123"
        )
        self.assertEqual(str(news), "Test News Title")
    
    def test_football_news_ordering(self):
        """Test that news is ordered by published_at descending."""
        news1 = FootballNews.objects.create(
            title="First News",
            published_at="2024-01-15T10:30:00Z",
            summary="First summary",
            source_id="source1"
        )
        
        news2 = FootballNews.objects.create(
            title="Second News",
            published_at="2024-01-16T10:30:00Z",
            summary="Second summary",
            source_id="source2"
        )
        
        news_list = list(FootballNews.objects.all())
        self.assertEqual(news_list[0], news2)  # Most recent first
        self.assertEqual(news_list[1], news1)
    
    def test_football_news_blank_summary(self):
        """Test that summary can be blank."""
        news = FootballNews.objects.create(
            title="Test News Title",
            published_at="2024-01-15T10:30:00Z",
            summary="",
            source_id="test_source_123"
        )
        self.assertEqual(news.summary, "")
    
    def test_football_news_managed_false(self):
        """Test that model is not managed by Django."""
        self.assertFalse(FootballNews._meta.managed)
    
    def test_football_news_db_table(self):
        """Test that model uses correct database table."""
        self.assertEqual(FootballNews._meta.db_table, "football_news")
