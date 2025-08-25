from django.db import models
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


