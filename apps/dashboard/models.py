from django.db import models
from django.conf import settings

class FootballNews(models.Model):
    """Modelo para noticias de fútbol"""
    title         = models.CharField(max_length=500)
    published_at  = models.DateTimeField()
    summary       = models.TextField(blank=True)
    source_id     = models.CharField(max_length=50)

    class Meta:
        db_table = "football_news" 
        managed  = False       # coincide con la tabla real
        ordering = ["-published_at"]

    def __str__(self):
        return self.title


class SavedSearch(models.Model):
    """Modelo para búsquedas guardadas del usuario"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_searches')
    name = models.CharField(max_length=100, help_text="Nombre descriptivo de la búsqueda")
    search_params = models.JSONField(help_text="Parámetros de búsqueda aplicados")
    selected_players = models.JSONField(help_text="IDs de jugadores seleccionados")
    selected_metrics = models.JSONField(help_text="Métricas seleccionadas para el dashboard")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['user', 'name']  # Un usuario no puede tener dos búsquedas con el mismo nombre

    def __str__(self):
        return f"{self.user.username} - {self.name}"


