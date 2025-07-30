# dashboard/models.py
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import JSONField

User = get_user_model()

class ChatSession(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")
    created_at = models.DateTimeField(auto_now_add=True)
    title      = models.CharField(max_length=120, blank=True)  # autogenerado "Informe sobre Rodri"
    thumbs_up  = models.BooleanField(null=True)  # evaluación global opcional
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

class Message(models.Model):
    session    = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="messages"
    )
    role       = models.CharField(max_length=10)          # 'user' | 'assistant'
    content    = models.TextField()
    meta       = JSONField(default=list, blank=True)      # ← NUEVO
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


# Create your models here.
