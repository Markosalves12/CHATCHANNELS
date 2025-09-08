from django.db import models
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from django.utils.crypto import get_random_string
from datetime import timedelta, datetime

class PasswordResetToken(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    reset_token = models.CharField(max_length=9, unique=True)
    url_token = models.CharField(max_length=16, unique=True)
    created_at = models.DateTimeField(default=now)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return now() > self.expires_at

    def save(self, *args, **kwargs):
        if not self.reset_token:
            self.reset_token = get_random_string(9)
        if not self.url_token:
            self.url_token = get_random_string(16)
        if not self.expires_at:
            self.expires_at = now() + timedelta(hours=1)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['reset_token']),
            models.Index(fields=['url_token']),
        ]