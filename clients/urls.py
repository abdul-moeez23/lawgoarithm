from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='index'),
    # path('signin/', views.client_signin, name='client_signin'),
    # path('signin/', views.client_signin, name='client_signin'),
    path('signup/', views.client_signup, name='client_signup'),
    # path('logout/', views.client_logout, name='client_logout'),
    path('signin/',views.signin,name='signin'),
    path('lawyers/search/', views.search_lawyers, name='search_lawyers'),  
    path('lawyer/<int:pk>/', views.lawyer_public_profile, name='lawyer_public_profile'),
    path('profile/', views.client_profile, name='client_profile'),
    # path('profile/edit/', views.edit_profile, name='edit_profile'),
    # Dashboard URLs
    path('client-portal/', views.client_dashboard, name='client_dashboard'),
    path('my-cases/', views.my_cases, name='my_cases'),
    path('post-case/', views.post_case, name='post_case'),
    path('messages/', views.client_messages, name='client_messages'),
    path('case/<int:pk>/', views.case_detail, name='case_detail'),
    path('case/<int:case_id>/send-message/', views.client_send_message, name='client_send_message'),
    path('match-results/<int:case_id>/', views.match_results, name='match_results'),
    path('connect/<int:case_id>/<int:lawyer_id>/', views.connect_to_lawyer, name='connect_to_lawyer'),
    path('logout/', views.client_logout, name='logout'),
    # Notifications Management
    path('dashboard/notifications/read/<int:id>/', views.mark_notification_read, name='mark_notification_read_client'),
    path('dashboard/notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_read_client'),
    
    # Hiring
    path('hired-lawyers/', views.hired_lawyers, name='hired_lawyers'),
    path('hire/<int:case_id>/<int:lawyer_id>/', views.hire_lawyer, name='hire_lawyer'),
    path('document/<int:document_id>/delete/<str:mode>/', views.client_delete_document, name='client_delete_document'),
    path('track-download/<int:message_id>/', views.track_download, name='track_download'),
    path('review/<int:interaction_id>/submit/', views.submit_review, name='submit_review'),
]

