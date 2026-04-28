from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import resolve_url
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

class MyAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        user = request.user
        if user.is_authenticated:
            if user.role == 'lawyer':
                return resolve_url('lawyer_dashboard')
            elif user.role == 'client':
                return resolve_url('client_dashboard') # Assuming 'client_dashboard' is the URL name
        return resolve_url(settings.LOGIN_REDIRECT_URL)

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        """
        Deny signup if the intent is explicitly 'login' (passed via auth_mode=login in next param).
        """
        from allauth.exceptions import ImmediateHttpResponse
        
        # Check the 'next' URL for our custom auth_mode flag
        next_url = sociallogin.state.get('next', '')

        # If we see auth_mode=login, we do not allow new account creation.
        if 'auth_mode=login' in next_url:
            # Check where they were trying to go to determine where to send them back
            msg = "Please sign up first, then login."
            
            if 'source=lawyer' in next_url:
                messages.error(request, msg)
                raise ImmediateHttpResponse(redirect('lawyer_login'))
            elif 'source=client' in next_url:
                messages.error(request, msg)
                raise ImmediateHttpResponse(redirect('signin'))
            else:
                 # Fallback if no source specified
                messages.error(request, msg)
                raise ImmediateHttpResponse(redirect('signin'))
            return False
            
        return True
