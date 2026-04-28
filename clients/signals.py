from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from users.models import User
from lawyers.models import LawyerProfile

@receiver(user_signed_up)
def set_user_role(request, user, **kwargs):
    """
    Ensure users signing up via social accounts have the correct role.
    If 'next' URL points to lawyer pages, assign 'lawyer' role and create profile.
    Default to 'client'.
    """
    if user.role:
        return

    # specific check for lawyer signup
    # We check the 'next' parameter which acts as our context carrier
    sociallogin = kwargs.get('sociallogin')
    next_url = None
    
    if sociallogin:
        next_url = sociallogin.state.get('next')
    
    if not next_url:
        # Fallback to request session or GET parameters if available
        next_url = request.GET.get('next')

    # If the user is signing up with the intention to contain on lawyer pages
   
    if next_url and ('/lawyer/' in next_url or 'source=lawyer' in next_url):
        user.role = 'lawyer'
        
        # Social accounts are considered email-verified
        user.is_email_verified = True
        user.is_active = True 
        user.save()
        
        # Create necessary Lawyer Profile
        if not LawyerProfile.objects.filter(user=user).exists():
            LawyerProfile.objects.create(
                user=user,
                verification_status='' # Matches manual signup initial state
            )
            
    else:
        # Default to client
        user.role = 'client'
        user.is_email_verified = True # Social login benefit
        user.is_active = True
        user.save()
