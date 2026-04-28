from django.urls import re_path
from admin_panel import consumers
from clients import consumers as client_consumers
from lawyers import consumers as lawyer_consumers

websocket_urlpatterns = [
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'ws/interaction-status/$', client_consumers.InteractionStatusConsumer.as_asgi()),
    re_path(r'ws/lawyer/dashboard/$', lawyer_consumers.LawyerDashboardConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<case_id>\d+)/$', client_consumers.ChatConsumer.as_asgi()),
]
