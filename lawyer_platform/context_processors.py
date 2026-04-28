from users.models import Notification

def notifications(request):
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        latest_notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:20]
        return {
            'unread_notification_count': unread_count,
            'latest_notifications': latest_notifications
        }
    return {}
