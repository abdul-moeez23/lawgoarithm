from .models import Notification

def notification_context(request):
    if request.user.is_authenticated:
        # Get latest 10 notifications for the dropdown
        notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:10]
        # Count unread notifications
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return {
            'notifications': notifications,
            'unread_notifications_count': unread_count
        }
    return {}
