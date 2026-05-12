from django.urls import path
from . import views

urlpatterns = [
    # path("lawyer/signup/", views.lawyer_signup, name="lawyer_signup"),
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('verification-sent/', views.verification_sent, name='verification_sent'),
    path('role-dispatch/', views.role_dispatch, name='role_dispatch'),
    path('notifications/mark-read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('notifications/', views.all_notifications, name='all_notifications'),
]


