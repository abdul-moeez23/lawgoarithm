from users.models import Notification
from clients.models import Message

def notifications(request):
    if request.user.is_authenticated:
        # Count unread notifications
        # Count unread notifications (excluding messages as they have their own indicator)
        unread_count = Notification.objects.filter(
            recipient=request.user, 
            is_read=False
        ).exclude(title__istartswith="New Message").count()
        
        # Get latest 10 notifications for the dropdown (excluding messages)
        latest_notifications = Notification.objects.filter(
            recipient=request.user
        ).exclude(title__istartswith="New Message").order_by('-created_at')[:10]
        
        # Count unread messages
        unread_msg_count = Message.objects.filter(recipient=request.user, is_read=False).count()
        
        
        # Determine base templates
        if request.user.role == 'lawyer':
            dashboard_base = 'lawyers/base_lawyer.html'
            dashboard_url = '/lawyer/lawyer-dashboard/'
            profile_url = '/lawyer/edit-lawyer-profile/'
        else:
            dashboard_base = 'clients/dashboard_base.html'
            dashboard_url = '/client-portal/'
            profile_url = '/profile/'

        return {
            'unread_notification_count': unread_count,
            'latest_notifications': latest_notifications,
            'unread_messages_count': unread_msg_count,
            'dashboard_base': dashboard_base,
            'dashboard_url': dashboard_url,
            'profile_url': profile_url,
            'account_base': dashboard_base
        }
    return {
        'dashboard_base': 'clients/dashboard_base.html', 
        'dashboard_url': '/', 
        'profile_url': '/profile/',
        'account_base': 'account/auth_base.html'
    }
