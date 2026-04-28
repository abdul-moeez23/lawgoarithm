from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = (
        ('client', 'Client'),
        ('lawyer', 'Lawyer'),
        ('admin', 'Admin'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Verification
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=200, blank=True, null=True)
    
    # Presence
    is_online = models.BooleanField(default=False)



# =========================
# LOOKUP TABLES
# =========================

class City(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self): return self.name


class Court(models.Model):
    name = models.CharField(max_length=150)
    def __str__(self): return self.name


class Category(models.Model):
    name = models.CharField(max_length=150)
    def __str__(self): return self.name


class SubCategory(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    def __str__(self): return self.name


class FeeBand(models.Model):
    name = models.CharField(max_length=100)
    min_fee = models.IntegerField(default=0)
    max_fee = models.IntegerField(default=0)
    def __str__(self): return self.name


class Language(models.Model):
    name = models.CharField(max_length=50)
    def __str__(self): return self.name


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.username}: {self.title}"