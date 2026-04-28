from django.urls import path
from . import views

urlpatterns = [
    path('lawyer-login/', views.lawyer_login, name='lawyer_login'),
    path('signup/', views.lawyer_signup, name='lawyer_signup'),
    path('lawyer-dashboard/',views.lawyer_dashboard,name='lawyer_dashboard'),
    path('lawyer-profile/',views.lawyer_profile,name='lawyer_profile'),
    path('editprofile/' ,views.edit_lawyer_profile,name='edit_lawyer_profile'),
    path ('change-password/',views.lawyer_change_password,name='lawyer_change_password'),
    path('profile-complete/', views.lawyer_profile_complete, name='lawyer_profile_complete'),
    path('waiting-verification/', views.waiting_verification, name='waiting_verification'),
    path('connection-request/<int:interaction_id>/<str:action>/', views.handle_connection_request, name='handle_connection_request'),
    path('my-cases/', views.lawyer_my_cases, name='lawyer_my_cases'),
    path('messages/', views.lawyer_messages, name='lawyer_messages'),
    path('case/<int:case_id>/', views.lawyer_case_detail, name='lawyer_case_detail'),
    path('case/<int:case_id>/send-message/', views.send_message, name='send_message'),
    path('case/<int:case_id>/schedule-appointment/', views.schedule_appointment, name='schedule_appointment'),
    path('case/<int:case_id>/update-progress/', views.update_case_progress, name='update_case_progress'),
    path('appointments/', views.lawyer_appointments, name='lawyer_appointments'),
    path('documents/', views.lawyer_documents, name='lawyer_documents'),
    path('document/<int:document_id>/delete/<str:mode>/', views.delete_document, name='delete_document'),
    path('logout/',views.lawyer_logout,name='lawyer_logout'),

]
