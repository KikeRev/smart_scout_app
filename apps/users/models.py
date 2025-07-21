from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    first_name = None  # opcional: si prefieres name/surname
    last_name  = None

    name           = models.CharField("first name", max_length=80)
    surname        = models.CharField("surname",    max_length=80, blank=True)
    birth_date     = models.DateField(blank=True, null=True)
    city           = models.CharField(max_length=80, blank=True)
    country        = models.CharField(max_length=80, blank=True)
    email          = models.EmailField(unique=True)   # obligatorio
    job_title      = models.CharField(max_length=80, blank=True)
    favourite_club = models.CharField(max_length=80, blank=True)
    avatar         = models.ImageField(upload_to="avatars/", blank=True, null=True)

    USERNAME_FIELD  = "email"      # login por email
    REQUIRED_FIELDS = ["username"] # aún se pedirá en createsuperuser

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.email or self.username
