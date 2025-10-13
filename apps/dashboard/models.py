from django.db import models
from django.conf import settings


class Player(models.Model):
    """Player model - unmanaged, references existing table"""
    full_name = models.TextField()
    age = models.IntegerField(null=True, blank=True)
    nationality = models.CharField(max_length=64, null=True, blank=True)
    position = models.CharField(max_length=32, null=True, blank=True)
    club = models.CharField(max_length=128, null=True, blank=True)
    team_logo = models.TextField(null=True, blank=True)
    league = models.CharField(max_length=64, null=True, blank=True)
    season = models.CharField(max_length=10, null=True, blank=True)
    minutes = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "players"
        managed = False

    def __str__(self):
        return self.full_name


class PlayerRating(models.Model):
    """FIFA-style player ratings - unmanaged, references existing table"""
    player = models.ForeignKey(Player, on_delete=models.CASCADE, db_column='player_id')
    
    # Overall rating
    overall_rating = models.IntegerField()
    league_base_rating = models.FloatField(null=True, blank=True)
    performance_rating = models.FloatField(null=True, blank=True)
    
    # Attributes by category (0-100)
    att = models.IntegerField(null=True, blank=True, help_text="Attacking")
    ply = models.IntegerField(null=True, blank=True, help_text="Playmaking")
    def_rating = models.IntegerField(null=True, blank=True, help_text="Defending")
    ctr = models.IntegerField(null=True, blank=True, help_text="Ball Control")
    phy = models.IntegerField(null=True, blank=True, help_text="Physical")
    gkp = models.IntegerField(null=True, blank=True, help_text="Goalkeeping")
    
    # Metadata
    season = models.CharField(max_length=10, null=True, blank=True)
    position = models.CharField(max_length=32, null=True, blank=True)
    minutes_played = models.IntegerField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "player_ratings"
        managed = False
        ordering = ['-overall_rating']
        unique_together = [['player', 'season']]

    def __str__(self):
        return f"{self.player.full_name} - {self.overall_rating} OVR ({self.season})"


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


