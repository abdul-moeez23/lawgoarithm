from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login,logout
from django.contrib.auth.decorators import login_required
# from .models import User
from lawyers.models import LawyerProfile
from django.contrib.auth.hashers import make_password,check_password
from users.models import User, City, Court, Language, FeeBand, SubCategory, Notification
from lawyers.models import VerificationDocument
from django.views.decorators.cache import never_cache
from lawyers.utils import notify_admin
from django.urls import reverse
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .decorators import approved_lawyer_required




def lawyer_login(request):
    # storage = messages.get_messages(request)
    # storage.used = True
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, username=email, password=password)

        if user is None:
            messages.error(request, "Invalid email or password",extra_tags="auto")
            return redirect("lawyer_login")

        if user.role != "lawyer":
            messages.error(request, "This account is not registered as a lawyer",extra_tags="auto")
            return redirect("lawyer_login")

        # Authenticate and Login
        login(request, user)

        # Verification and Profile Completion Check
        try:
            lp = user.lawyer_profile
        except LawyerProfile.DoesNotExist:
            return redirect("lawyer_profile_complete")

        # Case 1: Profile is completely fresh (not yet submitted)
        if lp.verification_status == '':
            return redirect("lawyer_profile_complete")

        # Case 2: Profile is pending admin approval
        if lp.verification_status == "pending":
            return redirect("waiting_verification")

        # Case 3: Profile was rejected by admin
        if lp.verification_status == "rejected":
            messages.error(request, "Your profile was rejected. Please update your details.")
            return redirect("lawyer_profile_complete")

        # Case 4: Profile is approved
        if lp.verification_status == "approved":
            return redirect("lawyer_dashboard")

        # Fallback
        return redirect("lawyer_dashboard")

    return render(request, "lawyers/login.html")




def lawyer_signup(request):
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        password = request.POST.get("password")

        # Name validation: Only letters and spaces, and not empty
        import re
        name_regex = r'^[a-zA-Z\s]+$'
        if not first_name or not last_name:
            messages.error(request, "First and Last names cannot be empty or just spaces.")
            return redirect("lawyer_signup")

        if not re.match(name_regex, first_name) or not re.match(name_regex, last_name):
            messages.error(request, "First and Last names should only contain letters and spaces.")
            return redirect("lawyer_signup")

        # Check existing user
        existing_user = User.objects.filter(username=email).first()
        if existing_user and existing_user.is_email_verified:
            messages.error(request, "Email already exists and is verified. Please log in.")
            return redirect("lawyer_signup")

        # Custom password validation
        import re
        if ' ' in password:
            messages.error(request, "Password cannot contain spaces.")
            return redirect("lawyer_signup")
        if not re.search(r'[A-Z]', password):
            messages.error(request, "Password must contain at least one uppercase letter.")
            return redirect("lawyer_signup")
        if not re.search(r'[^A-Za-z0-9\s]', password):
            messages.error(request, "Password must contain at least one special character.")
            return redirect("lawyer_signup")

        # Password validation
        try:
            validate_password(password, user=None)
        except ValidationError as e:
            for error in e.messages:
                messages.error(request, error)
            return redirect("lawyer_signup")

        if existing_user:
            user = existing_user
            user.first_name = first_name
            user.last_name = last_name
            user.phone = phone
            user.password = make_password(password)
            user.save()
            LawyerProfile.objects.get_or_create(user=user, defaults={'verification_status': ''})
        else:
            # Create User
            user = User.objects.create(
                username=email,
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role='lawyer',
                password=make_password(password),
                is_active=False, # Wait for verification
                is_email_verified=False
            )

            # Create empty lawyer profile
            LawyerProfile.objects.create(
                user=user,
                verification_status=''
            )
        
        from users.utils import send_verification_email
        send_verification_email(request, user)

        messages.success(request, "Signup successful. Please check your email to verify your account.", extra_tags='auto')
        # login(request, user) # Don't login yet
        return redirect("verification_sent")


    return render(request, "lawyers/signup.html")



@login_required(login_url='lawyer_login')
@never_cache
def lawyer_profile_complete(request):
    if request.method == "POST":

        lp, created = LawyerProfile.objects.get_or_create(user=request.user)

        lp.bar_enrollment = request.POST.get("bar_enrollment")
        lp.city_id = request.POST.get("city")
        # lp.fee_band_id = request.POST.get("fee_band")
        
        # Handle enrollment_date if provided
        enrollment_date = request.POST.get("enrollment_date")
        if enrollment_date:
            lp.enrollment_date = enrollment_date
            
        if request.FILES.get('profile_picture'):
            lp.profile_picture = request.FILES['profile_picture']
        lp.verification_status = 'pending'
        lp.rejection_reason = ""
        lp.save()

        courts_ids = request.POST.getlist("courts")
        # languages_ids = request.POST.getlist("languages")
        practice_ids = request.POST.getlist("practice_areas")

        lp.courts.set(courts_ids)
        # lp.languages.set(languages_ids)
        lp.practice_areas.set(practice_ids)

        # Handle verification documents upload

        from lawyers.models import VerificationDocument
        files = request.FILES.getlist('verification_documents')
        for file in files:
            VerificationDocument.objects.create(
                lawyer=lp,
                file=file
            )
        
        
        # LawyerProfile.objects.create(
        # #     user=user,
        #     verification_status='pending'
        # )

        # request.user.profile_completed = True
        request.user.save()

        from django.urls import reverse
        # Notify Admin (In-App Only)
        notify_admin(
            title="New Lawyer Request",
            message=f"Request from {request.user.first_name} ({request.user.email})",
            link=reverse('pending_lawyer_requests') + f"?highlight_id={lp.id}"
        )

        messages.success(request, "Profile completed successfully")
        return redirect('lawyer_login')



    from users.models import City, Court, SubCategory, FeeBand, Language
    
    # Try to get existing profile for pre-filling
    try:
        lp = LawyerProfile.objects.get(user=request.user)
    except LawyerProfile.DoesNotExist:
        lp = None

    context = {
        'cities': City.objects.all(),
        # 'fee_bands': FeeBand.objects.all(),
        'courts': Court.objects.all(),
        'languages': Language.objects.all(),
        'practice_areas': SubCategory.objects.all(),
        'lawyer_profile': lp,
    }
    
    return render(request, "lawyers/profile_complete.html", context)



@login_required(login_url='lawyer_login')
@never_cache
def waiting_verification(request):
    return render(request, "lawyers/waiting.html")

@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
@never_cache
def lawyer_dashboard(request):
    from clients.models import Interaction, Case
    
    lawyer = request.user  # session se automatic fetch
    lawyer_profile = get_object_or_404(LawyerProfile, user=lawyer)
    
    # Get connection requests (Interactions with status 'invited' or 'accepted')
    pending_requests = Interaction.objects.filter(
        lawyer=lawyer_profile,
        status__in=['invited', 'accepted']
    ).select_related('case', 'case__client', 'case__category', 'case__city').order_by('-created_at')[:10]
    
    # Get accepted/hired cases count
    total_cases = Interaction.objects.filter(
        lawyer=lawyer_profile,
        status__in=['accepted', 'hired']
    ).count()
    
    # Get active clients (unique clients with accepted/hired cases)
    active_clients = Interaction.objects.filter(
        lawyer=lawyer_profile,
        status__in=['accepted', 'hired']
    ).values_list('case__client', flat=True).distinct().count()
    
    # Get upcoming appointments count (future dates)
    from django.utils import timezone
    from clients.models import Appointment, CaseDocument
    
    from django.db.models import Q
    appointments_count = Appointment.objects.filter(
        Q(organizer=lawyer) | Q(attendee=lawyer),
        datetime__gte=timezone.now(),
        status='scheduled'
    ).count()

    # Get documents uploaded by lawyer
    documents_count = CaseDocument.objects.filter(
        uploaded_by=lawyer
    ).exclude(hidden_for=lawyer).count()
    
    # Get all active cases for the document upload dropdown
    all_cases = Interaction.objects.filter(
        lawyer=lawyer_profile,
        status__in=['accepted', 'hired']
    ).select_related('case', 'case__client').order_by('-created_at')

    context = {
        'lawyer': lawyer,
        'lawyer_profile': lawyer_profile,
        'pending_requests': pending_requests,
        'total_cases': total_cases,
        'active_clients': active_clients,
        'appointments_count': appointments_count,
        'documents_count': documents_count,
        'all_cases': all_cases,
    }
    
    return render(request, 'lawyers/lawyer_dashboard.html', context)


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
@never_cache
def lawyer_profile(request):
    # lawyer = request.user
    lawyer_profile = get_object_or_404(LawyerProfile, user=request.user)
    return render(request, 'lawyers/lawyer_profile.html', {'lawyer': lawyer_profile})






@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
@never_cache
def edit_lawyer_profile(request):

    user = request.user
    lawyer_profile = LawyerProfile.objects.get(user=user)

    if request.method == "POST":

        # ========== BASIC INFO ==========
        user.first_name = request.POST.get("first_name", "").strip()
        user.phone = request.POST.get("phone")

        # Name validation
        import re
        name_regex = r'^[a-zA-Z\s]+$'
        if not user.first_name:
            messages.error(request, "Name cannot be empty or just spaces.")
            return redirect("edit_lawyer_profile")

        if not re.match(name_regex, user.first_name):
            messages.error(request, "Name should only contain letters and spaces.")
            return redirect("edit_lawyer_profile")

        user.save()

        # ========== LAWYER PROFILE FIELDS ==========
        lawyer_profile.city_id = request.POST.get("city")
        
        enrollment_date = request.POST.get("enrollment_date")
        if enrollment_date:
            lawyer_profile.enrollment_date = enrollment_date
            
        # lawyer_profile.fee_band_id = request.POST.get("fee_band")

        # ========== PROFILE PICTURE ==========
        if request.FILES.get('profile_picture'):
            lawyer_profile.profile_picture = request.FILES['profile_picture']

        # ========== CHECKBOX MULTIPLE FIELDS ==========
        selected_courts = request.POST.getlist("courts")
        selected_languages = request.POST.getlist("languages")
        selected_practice_areas = request.POST.getlist("practice_areas")

        # Clear previous selections
        lawyer_profile.courts.clear()
        # lawyer_profile.languages.clear()
        lawyer_profile.practice_areas.clear()

        # Add new checked ones
        if selected_courts:
            lawyer_profile.courts.add(*selected_courts)

        if selected_languages:
            lawyer_profile.languages.add(*selected_languages)

        if selected_practice_areas:
            lawyer_profile.practice_areas.add(*selected_practice_areas)

        # ========== DOCUMENTS ==========
        document_file = request.FILES.get("documents")
        if document_file:
            lawyer_profile.verificationdocument_set.create(file=document_file)

        # Send back for admin approval
        lawyer_profile.verification_status = 'pending'
        lawyer_profile.rejection_reason = ""
        lawyer_profile.save()

        from django.urls import reverse
        from lawyers.utils import notify_admin
        notify_admin(
            title="Lawyer Profile Updated",
            message=f"{request.user.first_name} ({request.user.email}) has updated their profile and requires re-approval.",
            link=reverse('pending_lawyer_requests') + f"?highlight_id={lawyer_profile.id}"
        )

        messages.success(request, "Profile updated successfully! Your changes have been sent to the admin for re-approval.")
        return redirect("lawyer_dashboard")

    # ========== DATA FOR TEMPLATE ==========
    cities = City.objects.all()
    courts = Court.objects.all()
    languages = Language.objects.all()
    practice_areas = SubCategory.objects.all()
    # fee_bands = FeeBand.objects.all()
    fee_bands = [] # Empty list to avoid template errors if iterated

    return render(request, 'lawyers/lawyer_editprofile.html', {
        "user": user,
        "lawyer": lawyer_profile,
        "cities": cities,
        "courts": courts,
        "languages": languages,
        "practice_areas": practice_areas,
        "fee_bands": fee_bands,
    })

# def lawyer_change_password(request):
#     return render(request,'lawyers/change_password.html')

# # @login_required(login_url='/login/')

@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
@never_cache
def lawyer_change_password(request):

    lawyer = request.user   # login user (session se auto ata ha)

    if request.method == "POST":
        old_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        # 1. Check old password correct?
        if not check_password(old_password, lawyer.password):
            messages.error(request, "Old password is incorrect.")
            return redirect('lawyer_change_password')

        # 2. New passwords match?
        if new_password != confirm_password:
            messages.error(request, "New password and Confirm password do not match.")
            return redirect('lawyer_change_password')

        # 3. Update password securely
        lawyer.password = make_password(new_password)
        lawyer.save()

        messages.success(request, "Your password has been updated successfully.")
        return redirect('lawyer_dashboard')

    return render(request, 'lawyers/change_password.html')
# def lawyer_logout(request):
    
#     request.session.flush()
#     return redirect('/')

def lawyer_logout(request):
    logout(request)
    return redirect('/')


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
@never_cache
def handle_connection_request(request, interaction_id, action):
    """
    Handle connection request actions: accept or reject
    """
    from clients.models import Interaction
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    lawyer_profile = get_object_or_404(LawyerProfile, user=request.user)
    interaction = get_object_or_404(
        Interaction,
        pk=interaction_id,
        lawyer=lawyer_profile,
        status__in=['invited', 'accepted']
    )
    
    from django.http import JsonResponse

    if action == 'accept':
        if interaction.status != 'invited':
            return JsonResponse({'status': 'error', 'message': 'Request already accepted or handled'}, status=400)
            
        interaction.status = 'accepted'
        interaction.save()
        
        # Notify client that lawyer is interested (unlocks chat)
        msg = f"{request.user.get_full_name()} has accepted your connection request for case: {interaction.case.title}. Chat is now unlocked."
        from users.models import Notification
        Notification.objects.create(
            recipient=interaction.case.client,
            title="Lawyer Accepted Connection",
            message=msg,
            link=f"/match-results/{interaction.case.id}/" 
        )

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'case_{interaction.case.id}',
                {
                    'type': 'interaction_status_update',
                    'lawyer_id': interaction.lawyer.id,
                    'status': 'accepted',
                    'message': f'Your lawyer has accepted your connection request ✅\nChat is now unlocked.'
                }
            )

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
             return JsonResponse({'status': 'success', 'message': 'Request accepted'})
        
        messages.success(request, f"You have accepted the connection request. Chat is now unlocked.")

    elif action == 'propose_fee':
        if interaction.status != 'accepted':
            return JsonResponse({'status': 'error', 'message': 'You must accept the request before proposing a fee'}, status=400)
            
        quoted_fee = request.POST.get('quoted_fee')
        if not quoted_fee:
            return JsonResponse({'status': 'error', 'message': 'Fee is required'}, status=400)
            
        interaction.quoted_fee = quoted_fee
        interaction.save()
        
        # Notify client of the fee (enables hire button)
        msg = f"{request.user.get_full_name()} has quoted a fee of Rs. {quoted_fee} for your case: {interaction.case.title}."
        from users.models import Notification
        Notification.objects.create(
            recipient=interaction.case.client,
            title="Fee Proposed 💰",
            message=msg,
            link=f"/match-results/{interaction.case.id}/" 
        )

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'case_{interaction.case.id}',
                {
                    'type': 'interaction_status_update',
                    'lawyer_id': interaction.lawyer.id,
                    'status': 'accepted',
                    'quoted_fee': str(quoted_fee),
                    'message': f'Lawyer has proposed a fee of Rs. {quoted_fee} \nYou can now hire them.'
                }
            )

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
             return JsonResponse({'status': 'success', 'message': 'Fee proposed successfully'})
             
        messages.success(request, f"Fee proposed successfully.")

    elif action == 'reject':
        interaction.status = 'rejected'
        interaction.save()
        
        # Send WebSocket notification to client
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'case_{interaction.case.id}',
                {
                    'type': 'interaction_status_update',
                    'lawyer_id': interaction.lawyer.id,
                    'status': 'rejected',
                    'message': f'{lawyer_profile.user.get_full_name()} has rejected your connection request.'
                }
            )

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
             return JsonResponse({'status': 'success', 'message': 'Request rejected'})
             
        messages.info(request, f"You have rejected the connection request for case: {interaction.case.title}")
    else:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
             return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)
        messages.error(request, "Invalid action.")
    
    return redirect('lawyer_dashboard')    


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
@never_cache
def lawyer_my_cases(request):
    """
    List of cases where the lawyer is accepted or hired.
    """
    from clients.models import Interaction
    
    lawyer_profile = get_object_or_404(LawyerProfile, user=request.user)
    
    # interactions = Interaction.objects.filter(
    #     lawyer=lawyer_profile, 
    #     status__in=['accepted', 'hired']
    # ).select_related('case', 'case__client').order_by('-created_at')
    
    # We want to list cases based on updated_at usually, but interaction created_at is fine for now
    interactions = Interaction.objects.filter(
        lawyer=lawyer_profile, 
        status__in=['invited', 'accepted', 'hired']
    ).select_related('case', 'case__client').order_by('-created_at')

    return render(request, 'lawyers/my_cases.html', {'interactions': interactions})


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
@never_cache
def lawyer_case_detail(request, case_id):
    """
    Detailed view of a case for the lawyer, including CHAT, Documents, and Appointments.
    """
    from clients.models import Case, CaseDocument, Interaction, Message, Appointment
    
    lawyer_profile = get_object_or_404(LawyerProfile, user=request.user)
    case = get_object_or_404(Case, pk=case_id)
    
    # Verify the lawyer has access
    interaction = get_object_or_404(Interaction, case=case, lawyer=lawyer_profile)
    
    # Mark incoming messages as read
    Message.objects.filter(case=case, recipient=request.user, is_read=False).update(is_read=True)
    
    # Handle Document Upload
    if request.method == "POST" and request.FILES.get('document'):
        if interaction.status in ['accepted', 'hired']:
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
                    f'chat_{case_id}',
                    {
                        'type': 'document_uploaded',
                        'doc': {
                            'id': new_doc.id,
                            'title': new_doc.title,
                            'file_url': new_doc.file.url,
                            'uploaded_at': new_doc.uploaded_at.strftime("%b %d, Y"),
                            'uploaded_by_id': request.user.id,
                            'uploaded_by_name': request.user.get_full_name() or request.user.username,
                            'uploaded_by_role': 'lawyer'
                        }
                    }
                )
            except Exception as e:
                print(f"WebSocket Broadcast Error: {e}")

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'message': 'Document uploaded.'})

            messages.success(request, "Document uploaded successfully.")
            return redirect('lawyer_case_detail', case_id=case_id)
        else:
            messages.error(request, "You must accept the case before uploading documents.")
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'You must accept the case before uploading documents.'}, status=403)
    
    documents = CaseDocument.objects.filter(case=case).exclude(hidden_for=request.user).exclude(is_deleted_everyone=True).order_by('-uploaded_at')
    chat_messages = Message.objects.filter(case=case).exclude(is_deleted_everyone=True).exclude(hidden_for=request.user).order_by('created_at')
    appointments = Appointment.objects.filter(case=case).order_by('datetime')
    
    context = {
        'case': case,
        'interaction': interaction,  # Added this
        'interaction_status': interaction.status,
        'documents': documents,
        'chat_messages': chat_messages,
        'appointments': appointments,
    }
    return render(request, 'lawyers/lawyer_case_detail.html', context)


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def send_message(request, case_id):
    """
    Handle sending a message from Lawyer to Client.
    """
    from clients.models import Case, Message, Interaction
    
    from django.urls import reverse
    
    if request.method != 'POST':
        return redirect(reverse('lawyer_case_detail', kwargs={'case_id': case_id}) + '?tab=messages')
        
    lawyer_profile = get_object_or_404(LawyerProfile, user=request.user)
    case = get_object_or_404(Case, pk=case_id)
    content = request.POST.get('content')
    
    # Verify access
    interaction = get_object_or_404(Interaction, case=case, lawyer=lawyer_profile, status__in=['invited', 'accepted', 'hired'])
    
    if content:
        msg = Message.objects.create(
            case=case,
            sender=request.user,
            recipient=case.client,
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
                    'timestamp': msg.created_at.strftime("%I:%M %p")
                }
            )
            # Also notify client dashboard globally
            async_to_sync(channel_layer.group_send)(
                f'client_{case.client.id}',
                {
                    'type': 'chat_message',
                    'case_id': case.id,
                    'message': msg.content,
                    'sender_id': request.user.id,
                    'sender_name': request.user.get_full_name() or request.user.email,
                    'timestamp': msg.created_at.strftime("%I:%M %p")
                }
            )

        # Create persistent notification for the recipient
        Notification.objects.create(
            recipient=case.client,
            title=f"New Message from {request.user.get_full_name() or request.user.email}",
            message=content[:100] + ("..." if len(content) > 100 else ""),
            link=reverse('case_detail', kwargs={'pk': case.id}) + "?tab=messages"
        )
    
    return redirect(reverse('lawyer_case_detail', kwargs={'case_id': case_id}) + '?tab=messages')


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def schedule_appointment(request, case_id):
    """
    Schedule a new appointment for a case.
    """
    from clients.models import Case, Appointment, Interaction
    
    lawyer_profile = get_object_or_404(LawyerProfile, user=request.user)
    case = get_object_or_404(Case, pk=case_id)
    
    # Verify access
    get_object_or_404(Interaction, case=case, lawyer=lawyer_profile, status__in=['accepted', 'hired'])

    if request.method == "POST":
        title = request.POST.get('title')
        date_str = request.POST.get('date') # Expected format YYYY-MM-DD
        time_str = request.POST.get('time') # Expected format HH:MM
        duration = request.POST.get('duration', 30)
        location = request.POST.get('location')
        notes = request.POST.get('notes')
        
        # Combine date and time
        from django.utils.dateparse import parse_datetime
        full_datetime_str = f"{date_str} {time_str}"
        # Ideally parsing needs to be robust, but simple for now
        # Or better: construct datetime object
        import datetime
        dt_obj = datetime.datetime.strptime(full_datetime_str, "%Y-%m-%d %H:%M")
        # Make it timezone aware
        from django.utils import timezone
        dt_aware = timezone.make_aware(dt_obj)

        Appointment.objects.create(
            case=case,
            organizer=request.user,
            attendee=case.client,
            title=title,
            datetime=dt_aware,
            duration_minutes=duration,
            location=location,
            notes=notes,
            status='scheduled'
        )

        # Persistence Notification
        Notification.objects.create(
            recipient=case.client,
            title="Appointment Scheduled",
            message=f"Lawyer {request.user.get_full_name()} has scheduled an appointment: {title} for {dt_aware.strftime('%d %b %Y at %I:%M %p')}",
            link=f"/case/{case.id}/"
        )
        
        messages.success(request, "Appointment scheduled successfully.")
        return redirect(reverse('lawyer_case_detail', kwargs={'case_id': case_id}) + '?tab=appointments')
        
    return redirect(reverse('lawyer_case_detail', kwargs={'case_id': case_id}) + '?tab=appointments')


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def lawyer_messages(request):
    """
    List all cases/chats for the lawyer.
    """
    from clients.models import Interaction
    lawyer_profile = get_object_or_404(LawyerProfile, user=request.user)
    
    # Get all interactions where status is accepted or hired
    interactions = Interaction.objects.filter(
        lawyer=lawyer_profile, 
        status__in=['invited', 'accepted', 'hired']
    ).select_related('case', 'case__client').order_by('-case__updated_at')
    
    from clients.models import Message
    for interaction in interactions:
        interaction.unread_count = Message.objects.filter(
            case=interaction.case, recipient=request.user, is_read=False
        ).count()
    
    context = {
        'interactions': interactions,
    }
    return render(request, 'lawyers/messages_list.html', context)


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def update_case_progress(request, case_id):
    """
    Update detailed status, progress %, and next hearing date for a case.
    """
    from clients.models import Case, Interaction
    lawyer_profile = get_object_or_404(LawyerProfile, user=request.user)
    case = get_object_or_404(Case, pk=case_id)
    
    # Verify lawyer is hired for this case
    get_object_or_404(Interaction, case=case, lawyer=lawyer_profile, status='hired')

    if request.method == "POST":
        detailed_status = request.POST.get('detailed_status')
        progress_percentage = request.POST.get('progress_percentage')
        next_hearing_date = request.POST.get('next_hearing_date')
        case_completed = request.POST.get('case_completed')

        if detailed_status:
            case.detailed_status = detailed_status
        
        if progress_percentage is not None:
            case.progress_percentage = int(progress_percentage)
            
        if next_hearing_date:
            from django.utils.dateparse import parse_datetime
            from django.utils import timezone
            import datetime
            try:
                # Expecting YYYY-MM-DDTHH:MM (datetime-local input)
                dt = datetime.datetime.strptime(next_hearing_date, "%Y-%m-%dT%H:%M")
                case.next_hearing_date = timezone.make_aware(dt)
            except ValueError:
                messages.error(request, "Invalid date format.")
        
        if case_completed == 'true':
            case.status = 'closed'
            case.progress_percentage = 100
            case.detailed_status = "Case Successfully Completed"

        case.save()

        # Broadcast update via WebSocket
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'case_{case.id}',
                {
                    'type': 'case_progress_update',
                    'detailed_status': case.detailed_status,
                    'progress_percentage': case.progress_percentage,
                    'next_hearing_date': case.next_hearing_date.strftime('%d %b %Y') if case.next_hearing_date else None,
                    'status': case.status,
                    'updated_at': "just now" # Or format case.updated_at
                }
            )
            
            # Also send a global notification to the client
            async_to_sync(channel_layer.group_send)(
                f'client_{case.client.id}',
                {
                    'type': 'notification_update',
                    'message': f'Progress updated for case: {case.title}',
                    'case_id': case.id,
                    'is_progress_update': True,
                    'progress_percentage': case.progress_percentage,
                    'detailed_status': case.detailed_status
                }
            )

        # Persistence Notification
        Notification.objects.create(
            recipient=case.client,
            title="Case Progress Updated",
            message=f"Progress updated for case: {case.title}. Status: {case.detailed_status}",
            link=f"/case/{case.id}/"
        )

        messages.success(request, "Case progress updated successfully.")
        
    return redirect(f"{reverse('lawyer_case_detail', kwargs={'case_id': case_id})}?tab=details")


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def lawyer_appointments(request):
    """
    Global list of appointments for the lawyer.
    """
    from clients.models import Appointment
    from django.db.models import Q
    appointments = Appointment.objects.filter(
        Q(organizer=request.user) | Q(attendee=request.user)
    ).order_by('datetime')
    return render(request, 'lawyers/appointments.html', {'appointments': appointments})


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def lawyer_documents(request):
    """
    Global list of documents uploaded by the lawyer.
    """
    from clients.models import CaseDocument
   
    documents = CaseDocument.objects.filter(uploaded_by=request.user).exclude(hidden_for=request.user).exclude(is_deleted_everyone=True).order_by('-uploaded_at')
    return render(request, 'lawyers/documents.html', {'documents': documents})


@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def delete_document(request, document_id, mode):
    from clients.models import CaseDocument
    from django.http import JsonResponse
    document = get_object_or_404(CaseDocument, id=document_id)
    
    success = False
    message = ""

    if mode == 'me':
        document.hidden_for.add(request.user)
        success = True
        message = "Document hidden for you."
    elif mode == 'everyone':
        # Verify permissions: only uploader can delete for everyone
        if document.uploaded_by == request.user:
            if not document.can_delete_everyone:
                message = "You can only delete within 10 minutes of uploading."
                success = False
            else:
                doc_id = document.id
                case_id = document.case.id
                # Soft delete for everyone (keep in DB for Admin/Audit)
                document.is_deleted_everyone = True
                document.save()
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
        else:
            message = "You can only delete files for everyone that you uploaded."
            success = False
            
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': success, 'message': message})
            
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect(request.META.get('HTTP_REFERER', reverse('lawyer_dashboard')))

@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def lawyer_upload_document(request):
    """
    Global document upload from dashboard or documents page.
    """
    if request.method == "POST":
        case_id = request.POST.get('case_id')
        doc_file = request.FILES.get('document')
        doc_title = request.POST.get('title')
        
        if not case_id or not doc_file:
            messages.error(request, "Please select a case and a file.")
            return redirect(request.META.get('HTTP_REFERER', 'lawyer_dashboard'))
            
        from clients.models import Case, CaseDocument, Interaction
        case = get_object_or_404(Case, pk=case_id)
        
        # Verify access
        get_object_or_404(Interaction, case=case, lawyer__user=request.user)
        
        CaseDocument.objects.create(
            case=case,
            file=doc_file,
            title=doc_title or doc_file.name,
            uploaded_by=request.user
        )
        messages.success(request, f"Document uploaded successfully to Case #{case.id}.")
        return redirect('lawyer_documents')
        
    return redirect('lawyer_dashboard')

@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def lawyer_upload_document(request):
    """
    Global document upload from dashboard or documents page.
    """
    if request.method == "POST":
        case_id = request.POST.get('case_id')
        doc_file = request.FILES.get('document')
        doc_title = request.POST.get('title')
        
        if not case_id or not doc_file:
            messages.error(request, "Please select a case and a file.")
            return redirect(request.META.get('HTTP_REFERER', 'lawyer_dashboard'))
            
        from clients.models import Case, CaseDocument, Interaction
        case = get_object_or_404(Case, pk=case_id)
        
        # Verify access
        get_object_or_404(Interaction, case=case, lawyer__user=request.user)
        
        CaseDocument.objects.create(
            case=case,
            file=doc_file,
            title=doc_title or doc_file.name,
            uploaded_by=request.user
        )
        messages.success(request, f"Document uploaded successfully to Case #{case.id}.")
        return redirect('lawyer_documents')
        
    return redirect('lawyer_dashboard')

@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def cancel_appointment(request, appointment_id):
    from clients.models import Appointment
    from django.db.models import Q
    from users.models import Notification
    
    appointment = get_object_or_404(
        Appointment, 
        Q(organizer=request.user) | Q(attendee=request.user), 
        pk=appointment_id
    )
    
    if request.method == "POST":
        appointment.status = 'cancelled'
        appointment.save()
        
        # Notify the client
        Notification.objects.create(
            recipient=appointment.case.client,
            title="Appointment Cancelled ❌",
            message=f"Lawyer {request.user.get_full_name() or request.user.email} has cancelled the appointment: '{appointment.title}' scheduled for {appointment.datetime.strftime('%d %b %Y at %I:%M %p')}.",
            link=f"/case/{appointment.case.id}/?tab=appointments"
        )
        
        # Broadcast real-time appointment update
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'chat_{appointment.case.id}',
                    {
                        'type': 'appointment_update',
                        'action': 'cancelled',
                        'message': f"Lawyer {request.user.get_full_name() or request.user.email} has cancelled the appointment."
                    }
                )
        except Exception as e:
            print(f"WebSocket Broadcast Error: {e}")
            
        messages.success(request, "Appointment has been cancelled and client has been notified.")
    
    from django.urls import reverse
    return redirect(reverse('lawyer_case_detail', kwargs={'case_id': appointment.case.id}) + '?tab=appointments')

@login_required(login_url='/lawyer/lawyer-login/')
@approved_lawyer_required
def edit_appointment(request, appointment_id):
    from clients.models import Appointment
    from django.db.models import Q
    from users.models import Notification
    
    appointment = get_object_or_404(
        Appointment, 
        Q(organizer=request.user) | Q(attendee=request.user), 
        pk=appointment_id
    )
    
    if request.method == "POST":
        date_str = request.POST.get('date')
        time_str = request.POST.get('time')
        
        # Combine date and time
        full_datetime_str = f"{date_str} {time_str}"
        import datetime
        dt_obj = datetime.datetime.strptime(full_datetime_str, "%Y-%m-%d %H:%M")
        from django.utils import timezone
        dt_aware = timezone.make_aware(dt_obj)
        
        appointment.title = request.POST.get('title')
        appointment.datetime = dt_aware
        appointment.duration_minutes = request.POST.get('duration')
        appointment.location = request.POST.get('location')
        appointment.notes = request.POST.get('notes')
        appointment.save()
        
        # Notify the client
        Notification.objects.create(
            recipient=appointment.case.client,
            title="Appointment Rescheduled / Location Set 📅",
            message=f"Lawyer {request.user.get_full_name() or request.user.email} has rescheduled/updated '{appointment.title}' for {dt_aware.strftime('%d %b %Y at %I:%M %p')}. Location: {appointment.location or 'Not specified'}.",
            link=f"/case/{appointment.case.id}/?tab=appointments"
        )
        
        # Broadcast real-time appointment update
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'chat_{appointment.case.id}',
                    {
                        'type': 'appointment_update',
                        'action': 'rescheduled',
                        'message': f"Lawyer {request.user.get_full_name() or request.user.email} has updated the appointment."
                    }
                )
        except Exception as e:
            print(f"WebSocket Broadcast Error: {e}")
            
        messages.success(request, "Appointment successfully updated and client notified.")
        
    from django.urls import reverse
    return redirect(reverse('lawyer_case_detail', kwargs={'case_id': appointment.case.id}) + '?tab=appointments')
