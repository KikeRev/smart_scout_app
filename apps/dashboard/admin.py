from django.contrib import admin
from .models import Player, PlayerRating, FootballNews, SavedSearch


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    """Admin interface for Player model"""
    list_display = ['full_name', 'position', 'club', 'league', 'season', 'minutes']
    list_filter = ['league', 'position', 'season', 'club']
    search_fields = ['full_name', 'club', 'nationality']
    readonly_fields = ['full_name', 'age', 'nationality', 'position', 'club', 'league', 'season', 'minutes']


@admin.register(PlayerRating)
class PlayerRatingAdmin(admin.ModelAdmin):
    """Admin interface for PlayerRating model"""
    list_display = ['player', 'overall_rating', 'position', 'season', 'att', 'ply', 'def_rating', 'ctr', 'phy', 'gkp']
    list_filter = ['season', 'position']
    search_fields = ['player__full_name']
    readonly_fields = [
        'player', 'overall_rating', 'league_base_rating', 'performance_rating',
        'att', 'ply', 'def_rating', 'ctr', 'phy', 'gkp',
        'season', 'position', 'minutes_played', 'created_at', 'updated_at'
    ]
    ordering = ['-overall_rating']
    
    fieldsets = (
        ('Player Information', {
            'fields': ('player', 'season', 'position', 'minutes_played')
        }),
        ('Overall Rating', {
            'fields': ('overall_rating', 'league_base_rating', 'performance_rating')
        }),
        ('Attributes', {
            'fields': ('att', 'ply', 'def_rating', 'ctr', 'phy', 'gkp')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(FootballNews)
class FootballNewsAdmin(admin.ModelAdmin):
    """Admin interface for FootballNews model"""
    list_display = ['title', 'source_id', 'published_at']
    list_filter = ['source_id', 'published_at']
    search_fields = ['title', 'summary']
    readonly_fields = ['title', 'published_at', 'summary', 'source_id']


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    """Admin interface for SavedSearch model"""
    list_display = ['user', 'name', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__username', 'name']
    readonly_fields = ['created_at', 'updated_at']
