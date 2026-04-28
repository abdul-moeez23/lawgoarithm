import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.template.loader import render_to_string
from users.models import Notification
import asyncio

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            await self.accept()
            # Send initial data
            await self.send_notifications()
        else:
            # Silently accept to stop client retry loops
            await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        # Can be used for client-to-server messages if needed
        pass

    async def send_notifications(self):
        # We can poll periodically or wait for signals (polling for simplicity first to match previous logic)
        # But a better approach in Channels is using channel layers. 
        # However, to replicate the "Loop" efficiently without complex signals setup immediately:
        while True:
            await self.push_updates()
            await asyncio.sleep(5) # Check every 5 seconds

    async def push_updates(self):
        data = await self.get_notification_data()
        await self.send(text_data=json.dumps(data))

    @database_sync_to_async
    def get_notification_data(self):
        unread_count = Notification.objects.filter(recipient=self.user, is_read=False).count()
        latest_notifications = Notification.objects.filter(recipient=self.user).order_by('-created_at')[:20]
        
        # We need to replicate the context processor or view logic for rendering
        html_content = render_to_string('admin_panel/notification_dropdown_content.html', {
            'unread_notification_count': unread_count,
            'latest_notifications': latest_notifications
        })
        
        return {
            'unread_count': unread_count,
            'html': html_content
        }
