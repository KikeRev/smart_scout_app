from django.db import models
from django.conf import settings

class FootballNews(models.Model):
    """Model for football news"""
    title         = models.CharField(max_length=500)
    published_at  = models.DateTimeField()
    summary       = models.TextField(blank=True)
    source_id     = models.CharField(max_length=50)

    class Meta:
        db_table = "football_news" 
        managed  = False       # matches the real table
        ordering = ["-published_at"]

    def __str__(self):
        return self.title


class SavedSearch(models.Model):
    """Model for user saved searches"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_searches')
    name = models.CharField(max_length=100, help_text="Descriptive name for the search")
    search_params = models.JSONField(help_text="Applied search parameters")
    selected_players = models.JSONField(help_text="Selected player IDs")
    selected_metrics = models.JSONField(help_text="Selected metrics for the dashboard")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['user', 'name']  # A user cannot have two searches with the same name

    def __str__(self):
        return f"{self.user.username} - {self.name}"


