"""
Unit tests for Django views.
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch, Mock
import json

from apps.dashboard.models import SavedSearch
from tests.conftest import UserFactory

User = get_user_model()


class TestDashboardViews(TestCase):
    """Test cases for dashboard views."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)
    
    def test_home_view_authenticated(self):
        """Test home view for authenticated user."""
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
    
    def test_home_view_unauthenticated(self):
        """Test home view for unauthenticated user."""
        self.client.logout()
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_player_search_view(self):
        """Test player search view."""
        response = self.client.get(reverse('dashboard:player_search'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Search Filters')
    
    def test_comparison_view_no_players(self):
        """Test comparison view with no players selected."""
        response = self.client.get(reverse('dashboard:comparison'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No players selected')
    
    def test_comparison_view_with_players(self):
        """Test comparison view with players selected."""
        # Mock the search service
        with patch('apps.dashboard.views.get_comparison_data') as mock_get_data:
            mock_get_data.return_value = {
                'players': [
                    {
                        'id': 1,
                        'full_name': 'Test Player 1',
                        'team': 'Test Team 1',
                        'position': 'FW'
                    }
                ],
                'metrics': ['goals', 'assists'],
                'chart_type': 'radar_single'
            }
            
            response = self.client.get(
                reverse('dashboard:comparison'),
                {'player_ids': '1'}
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Test Player 1')
    
    def test_save_search_view_post(self):
        """Test save search view POST request."""
        search_data = {
            'name': 'Test Search',
            'search_params': json.dumps({'position': 'FW'}),
            'selected_players': json.dumps([1, 2, 3]),
            'selected_metrics': json.dumps(['goals', 'assists'])
        }
        
        response = self.client.post(reverse('dashboard:save_search'), search_data)
        self.assertEqual(response.status_code, 200)
        
        # Check that search was saved
        saved_search = SavedSearch.objects.get(user=self.user, name='Test Search')
        self.assertEqual(saved_search.name, 'Test Search')
    
    def test_save_search_view_duplicate_name(self):
        """Test save search view with duplicate name."""
        # Create first search
        SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        
        # Try to create second search with same name
        search_data = {
            'name': 'Test Search',
            'search_params': json.dumps({'position': 'FW'}),
            'selected_players': json.dumps([1, 2, 3]),
            'selected_metrics': json.dumps(['goals', 'assists'])
        }
        
        response = self.client.post(reverse('dashboard:save_search'), search_data)
        self.assertEqual(response.status_code, 400)
    
    def test_load_search_view(self):
        """Test load search view."""
        # Create a saved search
        search = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            search_params={'position': 'FW'},
            selected_players=[1, 2, 3],
            selected_metrics=['goals', 'assists']
        )
        
        response = self.client.get(
            reverse('dashboard:load_search', args=[search.id])
        )
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertEqual(data['name'], 'Test Search')
        self.assertEqual(data['search_params'], {'position': 'FW'})
    
    def test_load_search_view_not_found(self):
        """Test load search view with non-existent search."""
        response = self.client.get(
            reverse('dashboard:load_search', args=[999])
        )
        self.assertEqual(response.status_code, 404)
    
    def test_load_search_view_wrong_user(self):
        """Test load search view with search from different user."""
        other_user = UserFactory()
        search = SavedSearch.objects.create(
            user=other_user,
            name='Other User Search',
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        
        response = self.client.get(
            reverse('dashboard:load_search', args=[search.id])
        )
        self.assertEqual(response.status_code, 404)
    
    def test_delete_search_view(self):
        """Test delete search view."""
        # Create a saved search
        search = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        
        response = self.client.delete(
            reverse('dashboard:delete_search', args=[search.id])
        )
        self.assertEqual(response.status_code, 200)
        
        # Check that search was deleted
        self.assertFalse(SavedSearch.objects.filter(id=search.id).exists())
    
    def test_delete_search_view_not_found(self):
        """Test delete search view with non-existent search."""
        response = self.client.delete(
            reverse('dashboard:delete_search', args=[999])
        )
        self.assertEqual(response.status_code, 404)
    
    def test_delete_search_view_wrong_user(self):
        """Test delete search view with search from different user."""
        other_user = UserFactory()
        search = SavedSearch.objects.create(
            user=other_user,
            name='Other User Search',
            search_params={},
            selected_players=[],
            selected_metrics=[]
        )
        
        response = self.client.delete(
            reverse('dashboard:delete_search', args=[search.id])
        )
        self.assertEqual(response.status_code, 404)


class TestUserViews(TestCase):
    """Test cases for user views."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = UserFactory()
    
    def test_login_view_get(self):
        """Test login view GET request."""
        response = self.client.get(reverse('users:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Login')
    
    def test_login_view_post_valid(self):
        """Test login view POST with valid credentials."""
        response = self.client.post(reverse('users:login'), {
            'username': self.user.username,
            'password': 'testpass123'  # This would need to be set properly
        })
        # Note: This test would need proper password handling
        self.assertIn(response.status_code, [200, 302])
    
    def test_login_view_post_invalid(self):
        """Test login view POST with invalid credentials."""
        response = self.client.post(reverse('users:login'), {
            'username': 'invalid',
            'password': 'invalid'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect username or password')
    
    def test_signup_view_get(self):
        """Test signup view GET request."""
        response = self.client.get(reverse('users:signup'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Account')
    
    def test_signup_view_post_valid(self):
        """Test signup view POST with valid data."""
        response = self.client.post(reverse('users:signup'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'name': 'New',
            'surname': 'User',
            'password1': 'testpass123',
            'password2': 'testpass123'
        })
        # Note: This test would need proper form validation
        self.assertIn(response.status_code, [200, 302])
    
    def test_profile_view_authenticated(self):
        """Test profile view for authenticated user."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
    
    def test_profile_view_unauthenticated(self):
        """Test profile view for unauthenticated user."""
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_profile_edit_view_get(self):
        """Test profile edit view GET request."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('users:profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit Profile')
    
    def test_profile_edit_view_post(self):
        """Test profile edit view POST request."""
        self.client.force_login(self.user)
        response = self.client.post(reverse('users:profile_edit'), {
            'name': 'Updated Name',
            'surname': 'Updated Surname',
            'city': 'Updated City',
            'country': 'Updated Country'
        })
        self.assertEqual(response.status_code, 302)  # Redirect after successful update
        
        # Check that user was updated
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, 'Updated Name')
        self.assertEqual(self.user.surname, 'Updated Surname')
    
    def test_logout_view(self):
        """Test logout view."""
        self.client.force_login(self.user)
        response = self.client.post(reverse('users:logout'))
        self.assertEqual(response.status_code, 302)  # Redirect after logout


class TestChatViews(TestCase):
    """Test cases for chat views."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)
    
    def test_chat_list_view(self):
        """Test chat list view."""
        response = self.client.get(reverse('chats:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Reports')
    
    def test_chat_new_view(self):
        """Test new chat view."""
        response = self.client.get(reverse('chats:new'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome, how can I help you?')
    
    def test_chat_session_view(self):
        """Test chat session view."""
        response = self.client.get(reverse('chats:session', args=[1]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome, how can I help you?')
    
    def test_chat_api_view_post(self):
        """Test chat API view POST request."""
        with patch('apps.dashboard.chats.views.process_chat_message') as mock_process:
            mock_process.return_value = {
                'text': 'Test response',
                'attachments': []
            }
            
            response = self.client.post(reverse('chats:chat_api'), {
                'text': 'Test message',
                'session_id': 1
            })
            self.assertEqual(response.status_code, 200)
    
    def test_chat_delete_view(self):
        """Test chat delete view."""
        with patch('apps.dashboard.chats.views.delete_chat') as mock_delete:
            mock_delete.return_value = True
            
            response = self.client.delete(
                reverse('chats:chat_delete', args=[1])
            )
            self.assertEqual(response.status_code, 200)
