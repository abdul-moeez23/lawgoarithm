from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from .models import LawyerProfile

def approved_lawyer_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('lawyer_login')
            
        if request.user.role != 'lawyer':
            messages.error(request, "Access denied. Only lawyers can access this page.")
            return redirect('signin')
            
        try:
            lp = request.user.lawyer_profile
        except LawyerProfile.DoesNotExist:
            return redirect('lawyer_profile_complete')
            
        if lp.verification_status == '':
            return redirect('lawyer_profile_complete')
        elif lp.verification_status == 'pending':
            return redirect('waiting_verification')
        elif lp.verification_status == 'rejected':
            messages.error(request, "Your profile was rejected. Please update your details.")
            return redirect('lawyer_profile_complete')
        elif lp.verification_status == 'approved':
            return view_func(request, *args, **kwargs)
        
        # Fallback for unexpected status
        return redirect('lawyer_profile_complete')
        
    return _wrapped_view
