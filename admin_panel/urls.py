from django.urls import include,path
from .import views


urlpatterns = [
    path('',views.admin_login,name='admin_login'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('logout/', views.admin_logout, name='admin_logout'),
    path('pending-lawyers/', views.pending_lawyer_requests, name='pending_lawyer_requests'),
    path('approve-lawyer/<int:id>/', views.approve_lawyer, name='approve_lawyer'),
    path('reject-lawyer/<int:id>/', views.reject_lawyer, name='reject_lawyer'),

#     # view approved lawyers
    path('approvedlawyer',views.approved_lawyers,name='approved_lawyers'),
    
    # Data Management URLs
    path('manage-cities/', views.manage_cities, name='manage_cities'),
    path('manage-courts/', views.manage_courts, name='manage_courts'),
    path('manage-practice-areas/', views.manage_practice_areas, name='manage_practice_areas'),
    path('manage-fee-bands/', views.manage_fee_bands, name='manage_fee_bands'),
    
    # Notifications

    path('notifications/read/<int:id>/', views.mark_notification_read, name='mark_notification_read'),
]

