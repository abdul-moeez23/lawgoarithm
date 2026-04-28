from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect
import uuid

def send_verification_email(request, user):
    token = str(uuid.uuid4())
    user.email_verification_token = token
    user.is_email_verified = False # ensure false
    user.save()

    subject = 'Verify your email'
    # Build absolute URL
    relative_link = reverse('verify_email', kwargs={'token': token})
    verification_url = request.build_absolute_uri(relative_link)
    
    message = f'Click the link to verify your email: {verification_url}'
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
