from django.urls import path
from . import views

urlpatterns = [
    # path("lawyer/signup/", views.lawyer_signup, name="lawyer_signup"),
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('verification-sent/', views.verification_sent, name='verification_sent'),
    path('role-dispatch/', views.role_dispatch, name='role_dispatch'),
]


