# from django.db import models

# # Create your models here.


# class MatchResult(models.Model):
#     case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='matches')
#     lawyer = models.ForeignKey(LawyerProfile, on_delete=models.CASCADE)

#     fit_score = models.FloatField(
#         validators=[MinValueValidator(0), MaxValueValidator(100)]
#     )

#     reasons = models.JSONField()    # example: ["Similar past cases", "Court match"]

#     created_at = models.DateTimeField(default=timezone.now)

#     class Meta:
#         unique_together = ('case', 'lawyer')