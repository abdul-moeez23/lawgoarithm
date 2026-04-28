import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout as auth_logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)


from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from allauth.account.models import EmailAddress

from lawyers.models import LawyerProfile
from .models import Case, CaseDocument, Interaction, Message, Rating
from users.models import City, SubCategory,User

# Import MatchingService
from lawyers.services.matching import MatchingService

from .forms import CaseForm

def search_lawyers(request):
    from django.db.models import Avg, Count
    practice_area = request.GET.get('practice_area')
    city = request.GET.get('city')

    # Annotate with rating stats
    lawyers = LawyerProfile.objects.filter(verification_status='approved').annotate(
        avg_rating=Avg('interaction__rating__stars'),
        total_reviews=Count('interaction__rating')
    )

    if practice_area:
        lawyers = lawyers.filter(practice_areas__name__icontains=practice_area)
    if city:
        lawyers = lawyers.filter(city__name__icontains=city)

    # Pre-calculate stars to avoid template logic issues
    lawyers = list(lawyers)
    for lawyer in lawyers:
        rating = lawyer.avg_rating if lawyer.avg_rating else 0
        lawyer.rating_percentage = (rating / 5) * 100

    return render(request, 'clients/search_results.html', {'lawyers': lawyers})


def home(request):
    verified_lawyers = LawyerProfile.objects.filter(verification_status='approved').count()
    # verified_lawyers = 120 # Mock count or fetch real
    return render(request, 'clients/index.html', {'verified_lawyers': verified_lawyers})


def signin(request):
    if request.method == "POST":
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        print(f"DEBUG: Attempting login for {email}")
        user = authenticate(request, username=email, password=password)
        
        if user:
            print(f"DEBUG: Authenticated {user.username}, role: {user.role}")
            login(request, user)
            messages.success(request, f"Successfully signed in as {user.username}.")
            
            if user.role == 'lawyer':
                from lawyers.models import LawyerProfile
                try:
                    lp = user.lawyer_profile
                    # Handle all verification states
                    if lp.verification_status == '':
                        return redirect('lawyer_profile_complete')
                    elif lp.verification_status == 'pending':
                        return redirect('waiting_verification')
                    elif lp.verification_status == 'rejected':
                        messages.error(request, "Your profile was rejected. Please update your details.")
                        return redirect('lawyer_profile_complete')
                    elif lp.verification_status == 'approved':
                        return redirect('lawyer_dashboard')
                    else:
                        return redirect('lawyer_dashboard')
                except LawyerProfile.DoesNotExist:
                     return redirect('lawyer_profile_complete')
            
            elif user.role == 'client':
                print(f"DEBUG: Redirecting client to dashboard")
                return redirect('client_dashboard')
            
            else: # Admin
                 return redirect('admin_dashboard')
            
        else:
            print(f"DEBUG: Authentication failed for {email}")
            messages.error(request, "Invalid email or password", extra_tags="auto")
            return redirect('signin')

    return render(request, 'clients/signin.html')


def client_signup(request):
    if request.method == "POST":
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, "Passwords do not match!")
            return redirect('client_signup')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists!")
            return redirect('client_signup')

        # Custom password validation for uppercase and special symbol
        import re
        if not re.search(r'[A-Z]', password):
            messages.error(request, "Password must contain at least one uppercase letter.")
            return redirect('client_signup')
        if not re.search(r'[\W_]', password):
            messages.error(request, "Password must contain at least one special character.")
            return redirect('client_signup')

        # Django Default Password validation
        try:
            validate_password(password, user=None)
        except ValidationError as e:
            for error in e.messages:
                messages.error(request, error)
            return redirect('client_signup')

        try:
            # Create user
            user = User.objects.create_user(username=email, email=email, password=password)
            user.first_name = first_name
            user.last_name = last_name
            user.role = 'client'
            user.save()

            # Create Allauth EmailAddress and send confirmation
            email_address = EmailAddress.objects.create(
                user=user,
                email=email,
                primary=True,
                verified=False
            )
            email_address.send_confirmation(request)
            
            return render(request, 'clients/verification_sent.html', {'email': email})

        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            return redirect('client_signup')

    return render(request, 'clients/signup.html')


# ==========================================
# CLIENT DASHBOARD VIEWS
# ==========================================

@login_required(login_url='signin')
@never_cache
def client_dashboard(request):
    user = request.user
    if user.role != 'client':
        if user.role == 'lawyer':
            return redirect('lawyer_dashboard')
        return redirect('/myadmin/')

    # Stats
    total_cases = Case.objects.filter(client=user).count()
    active_cases = Case.objects.filter(client=user).exclude(status='closed').count()
    
    # Logic for hired lawyers 
    hired_interactions = Interaction.objects.filter(
        case__client=user, 
        status='hired' 
    ).select_related('lawyer', 'lawyer__user', 'case').order_by('-created_at')
    
    hired_count = hired_interactions.count()
    
    # Upcoming Appointments
    from django.utils import timezone
    from .models import Appointment
    appointments_count = Appointment.objects.filter(
        attendee=user,
        datetime__gte=timezone.now(),
        status='scheduled'
    ).count()

    # Recent Activity (Mix of created cases and interactions) - Simplified for now
    recent_cases = Case.objects.filter(client=user).order_by('-updated_at')[:3]

    # Pending Reviews Logic
    # Cases that are closed but have no rating for the hired/accepted interaction
    pending_reviews = Interaction.objects.filter(
        case__client=user,
        case__status='closed',
        status__in=['hired', 'accepted'], # Usually 'hired' for closed cases
        rating__isnull=True
    ).select_related('case', 'lawyer', 'lawyer__user')

    context = {
        'total_cases': total_cases,
        'active_cases': active_cases,
        'hired_count': hired_count,
        'hired_interactions': hired_interactions,
        'appointments_count': appointments_count,
        'recent_cases': recent_cases,
        'pending_reviews': pending_reviews,
    }
    return render(request, 'clients/dashboard_home.html', context)
    
@login_required(login_url='signin')
@never_cache
def my_cases(request):
    user = request.user
    cases = Case.objects.filter(client=user).order_by('-created_at')
    return render(request, 'clients/my_cases.html', {'cases': cases})


@login_required(login_url='signin')
@never_cache
def case_detail(request, pk):
    case = get_object_or_404(Case, pk=pk, client=request.user)
    
    # Mark incoming messages as read
    Message.objects.filter(case=case, recipient=request.user, is_read=False).update(is_read=True)
    
    # Handle Document Upload
    if request.method == "POST" and request.FILES.get('document'):
        doc_file = request.FILES['document']
        doc_title = request.POST.get('title', doc_file.name)
        new_doc = CaseDocument.objects.create(
            case=case, 
            file=doc_file, 
            title=doc_title,
            uploaded_by=request.user
        )
        
        # Broadcast via WebSocket
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'chat_{pk}',
                {
                    'type': 'document_uploaded',
                    'doc': {
                        'id': new_doc.id,
                        'title': new_doc.title,
                        'file_url': new_doc.file.url,
                        'uploaded_at': new_doc.uploaded_at.strftime("%b %d, Y"),
                        'uploaded_by_id': request.user.id,
                        'uploaded_by_name': request.user.get_full_name() or request.user.username,
                        'uploaded_by_role': 'client'
                    }
                }
            )
        except Exception as e:
            print(f"WebSocket Broadcast Error: {e}")

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'status': 'success', 'message': 'Document uploaded.'})

        messages.success(request, "Document uploaded successfully.")
        return redirect('case_detail', pk=pk)

    interactions = Interaction.objects.filter(case=case).select_related('lawyer', 'lawyer__user', 'lawyer__city').order_by('-created_at')
    documents = CaseDocument.objects.filter(case=case).exclude(hidden_for=request.user).order_by('-uploaded_at')
    
    # Chat Logic (Basic: Get messages for this case)
    chat_messages = Message.objects.filter(case=case).exclude(is_deleted_everyone=True).exclude(hidden_for=request.user).order_by('created_at')
    
    # Fetch Appointments
    from .models import Appointment
    appointments = Appointment.objects.filter(case=case).order_by('datetime')

    active_interaction = interactions.filter(status__in=['hired', 'accepted']).first()

    context = {
        'case': case,
        'interactions': interactions,
        'active_interaction': active_interaction,
        'documents': documents,
        'chat_messages': chat_messages,
        'appointments': appointments,
    }
    return render(request, 'clients/case_detail.html', context)



@login_required(login_url='signin')
@never_cache
def client_profile(request):
    user = request.user
    if request.method == "POST":
        user.first_name = request.POST.get('first_name')
        user.last_name = request.POST.get('last_name')
        user.phone = request.POST.get('phone')
        # Handle password change separately or here if simple
        user.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('client_profile')

    return render(request, 'clients/profile.html', {'user': user})


# def client_edit_profile(request):
#     user=request.user
#     if request.method =='POST':
#         user.first_name=request.POST.get('first_name')
#         user.last_name=request.POST.get('last_name')
#         user.phone=request.POST.get('phone')

#         user.save()
#         messages.success(request,"Profile updated successfully.")
#         return redirect('client_profile')



def client_logout(request):
    auth_logout(request)
    return redirect('signin')

@login_required(login_url='signin')
def post_case(request):
    if request.method == 'POST':
        form = CaseForm(request.POST)
        if form.is_valid():
            case = form.save(commit=False)
            case.client = request.user
            case.status = 'submitted'  # Set status to submitted when posted
            case.save() # Saved to DB

            messages.success(request, "Your case has been posted! Here are some recommended lawyers.")
            return redirect('match_results', case_id=case.id)
            
            # return redirect('my_cases') # Old redirect
    else:
        form = CaseForm()
    
    return render(request, 'clients/post_case.html', {'form': form})


@login_required(login_url='signin')
def match_results(request, case_id):
    """
    Display matched lawyers for a specific case.
    """
    case = get_object_or_404(Case, pk=case_id, client=request.user)
    
    cache_key = f"case_matches:{case.id}"
    cached = cache.get(cache_key)
    if cached is None:
        try:
            matches = MatchingService.get_best_matches(case)
            cache.set(cache_key, MatchingService.matches_to_cache_payload(matches), timeout=300)
        except Exception:
            logger.exception("Matching failed for case %s", case.id)
            matches = []
    elif (
        isinstance(cached, list)
        and cached
        and isinstance(cached[0], dict)
        and "lawyer" in cached[0]
    ):
        # Legacy cache entry (ORM objects); use as-is until it expires
        matches = cached
    else:
        matches = MatchingService.matches_from_cache_payload(case, cached if isinstance(cached, list) else [])
    
    # Check which lawyers already have connection requests
    if matches:
        # Extract lawyer objects from match dictionaries
        lawyer_ids = [match['lawyer'].id for match in matches]
        
        existing_interactions = Interaction.objects.filter(
            case=case,
            lawyer_id__in=lawyer_ids
        ).values_list('lawyer_id', 'status')
        
        interaction_status_map = {lawyer_id: status for lawyer_id, status in existing_interactions}
        
        # Add connection status to each match dictionary
        for match in matches:
            match['connection_status'] = interaction_status_map.get(match['lawyer'].id, None)
    
    return render(request, 'clients/match_results.html', {
        'case': case,
        'matches': matches
    })


# Removed AJAX endpoint - now using WebSockets for real-time updates


@login_required(login_url='signin')
def connect_to_lawyer(request, case_id, lawyer_id):
    """
    Handle connection request from client to lawyer.
    Creates an Interaction with status 'invited' when client clicks Connect.
    """
    case = get_object_or_404(Case, pk=case_id, client=request.user)
    lawyer_profile = get_object_or_404(LawyerProfile, pk=lawyer_id)
    
    # Check if interaction already exists
    interaction, created = Interaction.objects.get_or_create(
        case=case,
        lawyer=lawyer_profile,
        defaults={'status': 'invited'}
    )
    
    if not created:
        # If already exists, update status to 'invited' if it was rejected before
        if interaction.status == 'rejected':
            interaction.status = 'invited'
            interaction.save()
            messages.info(request, f"Connection request resent to {lawyer_profile.user.get_full_name()}.")
            
            # Notify Lawyer via WebSocket (Re-sent)
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"lawyer_{lawyer_profile.user.id}",
                {
                    "type": "new_connection_request",
                    "data": {
                        "id": interaction.id,
                        "client_name": case.client.get_full_name() or case.client.email,
                        "case_title": case.title,
                        "case_category": case.category.name if case.category else "General",
                        "case_description": case.description, # Truncate in template or here if you want
                        "created_at": interaction.created_at.strftime("%b. %d, %Y, %I:%M %p"),
                        "time_since": "Just now" 
                    }
                }
            )

        else:
            messages.info(request, f"You have already sent a connection request to {lawyer_profile.user.get_full_name()}.")
    else:
        messages.success(request, f"Connection request sent to {lawyer_profile.user.get_full_name()}!")
        
        # Notify Lawyer via WebSocket (New)
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"lawyer_{lawyer_profile.user.id}",
            {
                "type": "new_connection_request",
                "data": {
                    "id": interaction.id,
                    "client_name": case.client.get_full_name() or case.client.email,
                    "case_title": case.title,
                    "case_category": case.category.name if case.category else "General",
                    "case_description": case.description,
                    "created_at": interaction.created_at.strftime("%b. %d, %Y, %I:%M %p"),
                    "time_since": "Just now"
                }
            }
        )
    
    return redirect('match_results', case_id=case.id)


@login_required(login_url='signin')
def client_send_message(request, case_id):
    """
    Handle sending a message from Client to Lawyer.
    """
    from django.urls import reverse
    if request.method != 'POST':
        return redirect(reverse('case_detail', kwargs={'pk': case_id}) + '?tab=messages')
        
    case = get_object_or_404(Case, pk=case_id, client=request.user)
    content = request.POST.get('content')
    
    # Verify there is a hired/accepted lawyer to send to
    # Fetch the Hired or Accepted interaction
    try:
        interaction = Interaction.objects.filter(case=case, status__in=['invited', 'accepted', 'hired']).latest('created_at')
        recipient = interaction.lawyer.user
    except Interaction.DoesNotExist:
        messages.error(request, "You can only message lawyers you have hired or accepted.")
        return redirect(reverse('case_detail', kwargs={'pk': case_id}) + '?tab=messages')
    
    if content:
        msg = Message.objects.create(
            case=case,
            sender=request.user,
            recipient=recipient,
            content=content,
            is_read=False
        )
        
        # Real-time Broadcast
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'chat_{case_id}',
                {
                    'type': 'chat_message',
                    'message': msg.content,
                    'message_id': msg.id,
                    'sender_id': request.user.id,
                    'sender_name': request.user.get_full_name() or request.user.email,
                    'timestamp': msg.created_at.strftime("%I:%M %p") # Formatting for JS
                }
            )
            # Also notify lawyer dashboard globally
            async_to_sync(channel_layer.group_send)(
                f'lawyer_{recipient.id}',
                {
                    'type': 'chat_message',
                    'case_id': case.id,
                    'message': msg.content,
                    'sender_id': request.user.id,
                    'sender_name': request.user.get_full_name() or request.user.email,
                    'timestamp': msg.created_at.strftime("%I:%M %p")
                }
            )
    
    return redirect(reverse('case_detail', kwargs={'pk': case_id}) + '?tab=messages')


@login_required(login_url='signin')
def client_messages(request):
    """
    List all cases/chats for the client.
    """
    from .models import Interaction
    # Get all interactions for this client where status is accepted or hired
    interactions = Interaction.objects.filter(
        case__client=request.user,
        status__in=['invited', 'accepted', 'hired']
    ).select_related('case', 'lawyer', 'lawyer__user').order_by('-case__updated_at')
    
    from .models import Message
    for interaction in interactions:
        interaction.unread_count = Message.objects.filter(
            case=interaction.case, recipient=request.user, is_read=False
        ).count()
    
    context = {
        'interactions': interactions,
    }
    return render(request, 'clients/messages_list.html', context)


@login_required(login_url='signin')
def mark_notification_read(request, id):
    from users.models import Notification
    notification = get_object_or_404(Notification, id=id, recipient=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'status': 'success'})

@login_required(login_url='signin')
def mark_all_notifications_read(request):
    from users.models import Notification
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'success'})

@login_required(login_url='signin')
def hire_lawyer(request, case_id, lawyer_id):
    """
    Finalize hiring a lawyer for a specific case.
    """
    case = get_object_or_404(Case, pk=case_id, client=request.user)
    interaction = get_object_or_404(Interaction, case=case, lawyer_id=lawyer_id)
    
    # Mark incoming messages as read
    Message.objects.filter(case=case, recipient=request.user, is_read=False).update(is_read=True)
    
    if interaction.status != 'accepted':
        messages.error(request, "You can only hire a lawyer who has accepted your request.")
        return redirect('case_detail', pk=case_id)
    
    # Update Interaction Status
    interaction.status = 'hired'
    interaction.save()
    
    # Update Case Status
    case.status = 'hired'
    case.save()
    
    # Send WebSocket notification to the lawyer
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()
    if channel_layer:
        # Notify lawyer that they are HIRED
        async_to_sync(channel_layer.group_send)(
            f"lawyer_{interaction.lawyer.user.id}",
            {
                "type": "case_hired_notification",
                "message": f"Congratulations! You have been hired for the case: {case.title}",
                "case_id": case.id
            }
        )
        
        # Notify client dashboard to refresh status on match results if open
        async_to_sync(channel_layer.group_send)(
            f'case_{case.id}',
            {
                'type': 'interaction_status_update',
                'lawyer_id': interaction.lawyer.id,
                'status': 'hired',
                'message': f"You have successfully hired {interaction.lawyer.user.get_full_name()}!"
            }
        )

    messages.success(request, f"You have successfully hired {interaction.lawyer.user.get_full_name()}!")
    return redirect('case_detail', pk=case_id)

@login_required(login_url='signin')
def hired_lawyers(request):
    """
    Dedicated view to list all hired lawyers.
    """
    user = request.user
    hired_interactions = Interaction.objects.filter(
        case__client=user, 
        status='hired'
    ).select_related('lawyer', 'lawyer__user', 'case').order_by('-created_at')
    
    return render(request, 'clients/hired_lawyers.html', {
        'hired_interactions': hired_interactions
    })

@login_required(login_url='signin')
def lawyer_public_profile(request, pk):
    """
    Public profile view for clients to see lawyer details and reviews.
    """
    from django.db.models import Avg, Count
    lawyer_profile = get_object_or_404(LawyerProfile, pk=pk)
    
    # Verify lawyer is approved
    if lawyer_profile.verification_status != 'approved':
        messages.error(request, "This lawyer profile is not available.")
        return redirect('client_dashboard')

    # Get reviews (Ratings)
    reviews = Rating.objects.filter(interaction__lawyer=lawyer_profile).select_related('interaction', 'interaction__case', 'interaction__case__client').order_by('-created_at')
    
    # Aggregates
    stats = reviews.aggregate(avg_rating=Avg('stars'), total_reviews=Count('id'))
    
    context = {
        'lawyer': lawyer_profile,
        'reviews': reviews,
        'avg_rating': stats['avg_rating'],
        'total_reviews': stats['total_reviews']
    }
    return render(request, 'clients/lawyer_public_profile.html', context)


@login_required(login_url='signin')
def client_delete_document(request, document_id, mode):
    from .models import CaseDocument
    document = get_object_or_404(CaseDocument, id=document_id)
    
    # Permission check: user should be the client of the case or the uploader
    if document.case.client != request.user and document.uploaded_by != request.user:
        messages.error(request, "Access denied.")
        return redirect('client_dashboard')

    if mode == 'me':
        document.hidden_for.add(request.user)
        messages.success(request, "Document hidden for you.")
    elif mode == 'everyone':
        # Only uploader can delete for everyone
        if document.uploaded_by == request.user:
            doc_id = document.id
            case_id = document.case.id
            document.delete()
            success = True
            message = "Document deleted for everyone."
            
            # Broadcast deletion via WebSocket
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'chat_{case_id}',
                    {
                        'type': 'document_deleted',
                        'document_id': doc_id
                    }
                )
            messages.success(request, message)
        else:
            message = "You can only delete files for everyone that you uploaded."
            messages.error(request, message)
            
    return redirect(request.META.get('HTTP_REFERER', reverse('client_dashboard')))

@login_required(login_url='signin')
def track_download(request, message_id):
    """Marks a message's attachment as downloaded."""
    if request.method == "POST":
        msg = get_object_or_404(Message, id=message_id)
        # Only the recipient downloading counts for preventing deletion
        if request.user == msg.recipient:
            msg.is_attachment_downloaded = True
            msg.save()
            return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)


@login_required(login_url='signin')
def submit_review(request, interaction_id):
    """
    Handle review submission for a closed case/interaction.
    """
    interaction = get_object_or_404(Interaction, pk=interaction_id, case__client=request.user)
    
    # Validation: Case must be closed (or interaction finished)
    if interaction.case.status != 'closed' and interaction.status != 'hired': # Or whatever logic for 'closed'
        # Note: User requirements say "Show review section only after case/interaction is marked closed."
        # Assuming 'closed' status on Case is the trigger.
        if interaction.case.status != 'closed':
             messages.error(request, "You can only review finished cases.")
             return redirect('case_detail', pk=interaction.case.id)

    if request.method == "POST":
        stars = request.POST.get('stars')
        review_text = request.POST.get('review')
        
        try:
            stars = int(stars)
            if not (1 <= stars <= 5):
                raise ValueError
        except (ValueError, TypeError):
             messages.error(request, "Invalid rating.")
             return redirect('case_detail', pk=interaction.case.id)

        # Create or Update Rating
        Rating.objects.update_or_create(
            interaction=interaction,
            defaults={
                'stars': stars,
                'review': review_text,
                'created_at': timezone.now()
            }
        )
        
        # Determine notification message based on update or new
        is_new = not Rating.objects.filter(interaction=interaction).exists() # Wait, update_or_create handles this.
        # Check if created or updated logic is complex with update_or_create return, let's keep it simple.
        
        messages.success(request, "Thank you for your review!")
        
        # Real-time notification to Lawyer?
        # Maybe not strictly required but good for "Professional System"
        
        return redirect('case_detail', pk=interaction.case.id)
    
    return redirect('case_detail', pk=interaction.case.id)
