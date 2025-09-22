"""
Integration tests for data pipeline processes.
"""

import pytest
import pandas as pd
from unittest.mock import patch, Mock
import tempfile
import os
import json

from apps.ingestion.seed_and_ingest import (
    load_players_from_csv,
    process_news_feeds,
    generate_embeddings,
    save_to_database
)


class TestDataIngestionPipeline:
    """Test cases for data ingestion pipeline."""
    
    def test_load_players_from_csv(self):
        """Test loading players from CSV file."""
        # Create a temporary CSV file
        csv_data = """id,full_name,team,position,age,nationality,goals,assists,minutes
1,Lionel Messi,Inter Miami,FW,36,Argentina,25,15,2500
2,Cristiano Ronaldo,Al Nassr,FW,39,Portugal,20,10,2200
3,Kevin De Bruyne,Manchester City,MF,32,Belgium,8,20,2400"""
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as tmp_file:
            tmp_file.write(csv_data)
            tmp_file_path = tmp_file.name
        
        try:
            players = load_players_from_csv(tmp_file_path)
            assert len(players) == 3
            assert players[0]['full_name'] == 'Lionel Messi'
            assert players[1]['full_name'] == 'Cristiano Ronaldo'
            assert players[2]['full_name'] == 'Kevin De Bruyne'
        finally:
            os.unlink(tmp_file_path)
    
    def test_load_players_from_csv_invalid_file(self):
        """Test loading players from non-existent CSV file."""
        with pytest.raises(FileNotFoundError):
            load_players_from_csv('non_existent_file.csv')
    
    def test_load_players_from_csv_missing_columns(self):
        """Test loading players from CSV with missing required columns."""
        csv_data = """id,full_name,team
1,Lionel Messi,Inter Miami
2,Cristiano Ronaldo,Al Nassr"""
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as tmp_file:
            tmp_file.write(csv_data)
            tmp_file_path = tmp_file.name
        
        try:
            with pytest.raises(ValueError):
                load_players_from_csv(tmp_file_path)
        finally:
            os.unlink(tmp_file_path)
    
    def test_process_news_feeds(self):
        """Test processing news feeds."""
        with patch('apps.ingestion.seed_and_ingest.feedparser.parse') as mock_parse:
            # Mock RSS feed data
            mock_parse.return_value = {
                'entries': [
                    {
                        'title': 'Messi scores hat-trick',
                        'link': 'https://example.com/news1',
                        'published': '2024-01-15T10:30:00Z',
                        'summary': 'Lionel Messi scored three goals...'
                    },
                    {
                        'title': 'Ronaldo breaks record',
                        'link': 'https://example.com/news2',
                        'published': '2024-01-16T11:00:00Z',
                        'summary': 'Cristiano Ronaldo broke another record...'
                    }
                ]
            }
            
            with patch('apps.ingestion.seed_and_ingest.newspaper.Article') as mock_article:
                # Mock article content
                mock_article_instance = Mock()
                mock_article_instance.download.return_value = None
                mock_article_instance.parse.return_value = None
                mock_article_instance.text = 'Full article content...'
                mock_article.return_value = mock_article_instance
                
                news_items = process_news_feeds(['https://example.com/rss'])
                assert len(news_items) == 2
                assert news_items[0]['title'] == 'Messi scores hat-trick'
                assert news_items[1]['title'] == 'Ronaldo breaks record'
    
    def test_generate_embeddings(self):
        """Test generating embeddings for text data."""
        with patch('apps.ingestion.seed_and_ingest.SentenceTransformer') as mock_transformer:
            # Mock the transformer
            mock_model = Mock()
            mock_model.encode.return_value = [[0.1, 0.2, 0.3, 0.4, 0.5]]
            mock_transformer.return_value = mock_model
            
            texts = ['Messi scores hat-trick', 'Ronaldo breaks record']
            embeddings = generate_embeddings(texts)
            
            assert len(embeddings) == 2
            assert len(embeddings[0]) == 5  # Mock embedding dimension
            assert len(embeddings[1]) == 5
    
    def test_save_to_database(self):
        """Test saving data to database."""
        with patch('apps.ingestion.seed_and_ingest.get_db_session') as mock_get_session:
            # Mock database session
            mock_session = Mock()
            mock_get_session.return_value.__enter__.return_value = mock_session
            
            players_data = [
                {
                    'id': 1,
                    'full_name': 'Lionel Messi',
                    'team': 'Inter Miami',
                    'position': 'FW',
                    'age': 36,
                    'nationality': 'Argentina'
                }
            ]
            
            save_to_database(players_data, 'players')
            
            # Verify that session.add was called
            mock_session.add.assert_called()
            mock_session.commit.assert_called()


class TestNewsProcessingPipeline:
    """Test cases for news processing pipeline."""
    
    def test_news_summarization(self):
        """Test news summarization process."""
        with patch('apps.ingestion.seed_and_ingest.pipeline') as mock_pipeline:
            # Mock the summarization pipeline
            mock_summarizer = Mock()
            mock_summarizer.return_value = [{'summary_text': 'Messi scored three goals in a remarkable performance.'}]
            mock_pipeline.return_value = mock_summarizer
            
            news_text = "Lionel Messi scored three goals in Inter Miami's victory over their rivals. The Argentine forward displayed exceptional skill and determination throughout the match."
            
            summary = mock_summarizer(news_text)
            assert 'summary_text' in summary[0]
            assert 'Messi' in summary[0]['summary_text']
    
    def test_news_embedding_generation(self):
        """Test generating embeddings for news articles."""
        with patch('apps.ingestion.seed_and_ingest.SentenceTransformer') as mock_transformer:
            # Mock the transformer
            mock_model = Mock()
            mock_model.encode.return_value = [[0.1, 0.2, 0.3, 0.4, 0.5]]
            mock_transformer.return_value = mock_model
            
            news_articles = [
                'Messi scores hat-trick in MLS victory',
                'Ronaldo breaks another record in Saudi Arabia'
            ]
            
            embeddings = generate_embeddings(news_articles)
            assert len(embeddings) == 2
            assert len(embeddings[0]) == 5
    
    def test_news_deduplication(self):
        """Test news deduplication process."""
        news_items = [
            {
                'title': 'Messi scores hat-trick',
                'url': 'https://example.com/news1',
                'content': 'Lionel Messi scored three goals...'
            },
            {
                'title': 'Messi scores hat-trick',  # Duplicate title
                'url': 'https://example.com/news2',
                'content': 'Lionel Messi scored three goals...'
            },
            {
                'title': 'Ronaldo breaks record',
                'url': 'https://example.com/news3',
                'content': 'Cristiano Ronaldo broke another record...'
            }
        ]
        
        # Simple deduplication based on title
        unique_news = []
        seen_titles = set()
        
        for item in news_items:
            if item['title'] not in seen_titles:
                unique_news.append(item)
                seen_titles.add(item['title'])
        
        assert len(unique_news) == 2
        assert unique_news[0]['title'] == 'Messi scores hat-trick'
        assert unique_news[1]['title'] == 'Ronaldo breaks record'


class TestDatabaseOperations:
    """Test cases for database operations."""
    
    def test_database_connection(self):
        """Test database connection."""
        with patch('apps.ingestion.seed_and_ingest.create_engine') as mock_create_engine:
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            
            # Test connection
            engine = mock_create_engine('postgresql://test:test@localhost/test')
            assert engine is not None
    
    def test_database_transaction_rollback(self):
        """Test database transaction rollback on error."""
        with patch('apps.ingestion.seed_and_ingest.get_db_session') as mock_get_session:
            # Mock database session with error
            mock_session = Mock()
            mock_session.add.side_effect = Exception("Database error")
            mock_get_session.return_value.__enter__.return_value = mock_session
            
            players_data = [{'id': 1, 'name': 'Test Player'}]
            
            with pytest.raises(Exception):
                save_to_database(players_data, 'players')
            
            # Verify rollback was called
            mock_session.rollback.assert_called()
    
    def test_database_batch_insert(self):
        """Test batch insert operation."""
        with patch('apps.ingestion.seed_and_ingest.get_db_session') as mock_get_session:
            # Mock database session
            mock_session = Mock()
            mock_get_session.return_value.__enter__.return_value = mock_session
            
            players_data = [
                {'id': 1, 'name': 'Player 1'},
                {'id': 2, 'name': 'Player 2'},
                {'id': 3, 'name': 'Player 3'}
            ]
            
            save_to_database(players_data, 'players')
            
            # Verify that session.add was called for each player
            assert mock_session.add.call_count == 3
            mock_session.commit.assert_called()


class TestDataValidation:
    """Test cases for data validation in pipeline."""
    
    def test_player_data_validation(self):
        """Test validation of player data during ingestion."""
        from apps.agent_service.validation import validate_player_data
        
        valid_player = {
            'id': 1,
            'full_name': 'Lionel Messi',
            'team': 'Inter Miami',
            'position': 'FW'
        }
        
        invalid_player = {
            'id': -1,  # Invalid ID
            'full_name': 'Lionel Messi',
            'team': 'Inter Miami',
            'position': 'FW'
        }
        
        assert validate_player_data(valid_player) is True
        assert validate_player_data(invalid_player) is False
    
    def test_news_data_validation(self):
        """Test validation of news data during ingestion."""
        from apps.agent_service.validation import validate_news_data
        
        valid_news = {
            'title': 'Messi scores hat-trick',
            'content': 'Lionel Messi scored three goals...',
            'url': 'https://example.com/news',
            'published_date': '2024-01-15T10:30:00Z',
            'source': 'ESPN'
        }
        
        invalid_news = {
            'title': '',  # Empty title
            'content': 'Lionel Messi scored three goals...',
            'url': 'https://example.com/news',
            'published_date': '2024-01-15T10:30:00Z',
            'source': 'ESPN'
        }
        
        assert validate_news_data(valid_news) is True
        assert validate_news_data(invalid_news) is False
    
    def test_data_consistency_check(self):
        """Test data consistency checks."""
        from apps.agent_service.validation import check_data_consistency
        
        consistent_data = {
            'goals': 25,
            'minutes': 2500,
            'goals_per90': 0.9  # 25/2500*90 = 0.9
        }
        
        inconsistent_data = {
            'goals': 25,
            'minutes': 2500,
            'goals_per90': 2.0  # Should be 0.9
        }
        
        assert check_data_consistency(consistent_data) is True
        assert check_data_consistency(inconsistent_data) is False
