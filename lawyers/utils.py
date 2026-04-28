from users.models import Notification, User
from django.db.models import Q
# from django.core.mail import EmailMultiAlternatives
# from django.template.loader import render_to_string
# from django.utils.html import strip_tags
# from django.conf import settings
# import threading

def create_notification(recipient, title, message, link=None):
    """
    Creates an in-app notification for a user.
    """
    Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        link=link
    )

def notify_admin(title, message, link=None):
    """
    Notifies all superusers/admins.
    """
    print(f"--- Triggering Admin Notification: {title} ---")
    admins = User.objects.filter(Q(is_superuser=True) | Q(role='admin')).distinct()
    print(f"--- Found {admins.count()} Admins ---")
    
    for admin in admins:
        create_notification(admin, title, message, link)
        print(f"--- Notification created for {admin.username} ---")


# def send_html_email(subject, template_name, context, recipient_list):
#     """
#     Sends a professional HTML email using a template.
#     """
#     html_content = render_to_string(template_name, context)
#     text_content = strip_tags(html_content)
#     
#     from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Lawyer Platform <noreply@lawyerplatform.com>')
# 
#     email = EmailMultiAlternatives(
#         subject,
#         text_content,
#         from_email,
#         recipient_list
#     )
#     email.attach_alternative(html_content, "text/html")
#     
#     EmailThread(email).start()

# class EmailThread(threading.Thread):
#     def __init__(self, email):
#         self.email = email
#         threading.Thread.__init__(self)
# 
#     def run(self):
#         try:
#             print(f"--- Sending Email to {self.email.to} ---")
#             self.email.send()
#             print("--- Email Sent Successfully ---")
#         except Exception as e:
#             print(f"Failed to send email: {e}")
