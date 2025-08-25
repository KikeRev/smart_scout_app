# apps/charts/models.py
from django.db import models
from django.urls import reverse


class TempChart(models.Model):
    image = models.ImageField(upload_to="charts/")
    created_at = models.DateTimeField(auto_now_add=True)

    def get_absolute_url(self):
        return reverse("charts:file", args=[self.pk])

