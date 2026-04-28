from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
# from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import User, City, Court, SubCategory, FeeBand, Language


class LawyerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='lawyer_profile')

    bar_enrollment = models.CharField(max_length=150)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True)
    # fee_band = models.ForeignKey(FeeBand, on_delete=models.SET_NULL, null=True)
    experience_years = models.IntegerField(default=0)


    courts = models.ManyToManyField(Court)
    # languages = models.ManyToManyField(Language)
    practice_areas = models.ManyToManyField(SubCategory)
    
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    verification_status = models.CharField(
        max_length=20,
        choices=(('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')),
        default='pending'
    )



    # embedding = ArrayField(models.FloatField(), blank=True, null=True)  # AI embedding

    def __str__(self):
        return f"{self.user.username}"


# =========================
# LAWYER PAST MATTERS
# =========================

class Matter(models.Model):
    lawyer = models.ForeignKey(LawyerProfile, on_delete=models.CASCADE, related_name='matters')
    subcategory = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True)
    court = models.ForeignKey(Court, on_delete=models.SET_NULL, null=True)

    year = models.IntegerField()
    duration_months = models.IntegerField(default=0)
    fee_band = models.ForeignKey(FeeBand, on_delete=models.SET_NULL, null=True)

    summary = models.TextField()
    # embedding = ArrayField(models.FloatField(), blank=True, null=True)

    def __str__(self):
        return f"Matter ({self.lawyer.user.username})"


# =========================
# VERIFICATION DOCUMENTS
# =========================

class VerificationDocument(models.Model):
    lawyer = models.ForeignKey(LawyerProfile, on_delete=models.CASCADE)
    file = models.FileField(upload_to='verification/')
    uploaded_at = models.DateTimeField(default=timezone.now)

    admin_comment = models.TextField(blank=True, null=True)


