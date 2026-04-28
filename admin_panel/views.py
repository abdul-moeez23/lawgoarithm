from django.shortcuts import render, redirect,get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.views.decorators.cache import never_cache
from lawyers.models import LawyerProfile
from clients.models import Case




# @login_required
def admin_login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, username=email, password=password)
        if user is not None and user.is_superuser:  # check superuser instead of role
            login(request, user)
            return redirect("admin_dashboard")
        else:
            messages.error(request, "Invalid credentials or not admin", extra_tags="admin_error")
    return render(request, "admin_panel/login.html")

@login_required(login_url='admin_login')
@never_cache
def admin_dashboard(request):
    # Only count lawyers who have at least submitted their profile (pending, approved, or rejected)
    total_lawyers = LawyerProfile.objects.exclude(verification_status='').count()
    verified_lawyers = LawyerProfile.objects.filter(verification_status='approved').count()
    pending_lawyers = LawyerProfile.objects.filter(verification_status='pending').count()
    
    # Optional: Count how many people signed up but didn't finish their profile
    incomplete_lawyers = LawyerProfile.objects.filter(verification_status='').count()

    total_cases = Case.objects.count()

    context = {
        'total_lawyers': total_lawyers,
        'verified_lawyers': verified_lawyers,
        'pending_lawyers': pending_lawyers,
        'incomplete_lawyers': incomplete_lawyers,
        'total_cases': total_cases,
    }

    return render(request, 'admin_panel/dashboard.html', context)








def admin_logout(request):
    logout(request)
    return redirect('/')




@login_required(login_url='admin_login')
@never_cache
def pending_lawyer_requests(request):
    # Fetch only pending verification lawyers
    pending_requests = LawyerProfile.objects.filter(verification_status='pending').order_by('-user__date_joined')
    return render(request, 'admin_panel/pending_lawyers.html', {'requests': pending_requests})


@login_required(login_url='admin_login')
@never_cache
def approve_lawyer(request, id):

    lawyer = get_object_or_404(LawyerProfile, id=id)
    
    lawyer.verification_status = 'approved' 
    

    lawyer.save()
    
    # Clean up notifications related to this lawyer request
    from users.models import Notification
    # Delete notifications where the link contains this lawyer's ID
    Notification.objects.filter(link__contains=f"highlight_id={id}").delete()
    
    messages.success(request, f"Lawyer {lawyer.user_id} ka profile approve ho gaya." ,extra_tags="admin_error")
    
    return redirect('admin_dashboard')


@login_required(login_url='admin_login')
@never_cache
def approved_lawyers(request):
    approved_lawyers=LawyerProfile.objects.filter(verification_status='approved').order_by('-user__date_joined')
    return render(request,'admin_panel/approved_lawyers.html',{'lawyers':approved_lawyers})



@login_required(login_url='admin_login')
@never_cache
def reject_lawyer(request, id):
    lawyer = get_object_or_404(LawyerProfile, id=id)

    lawyer.verification_status = 'rejected'

    lawyer.save()
    
    # Clean up notifications related to this lawyer request
    from users.models import Notification
    Notification.objects.filter(link__contains=f"highlight_id={id}").delete()
    
    # messages.success(request, f"Lawyer {lawyer.user_id} ka profile reject ho gaya.")
    return redirect('admin_dashboard')

# =========================
# DATA MANAGEMENT VIEWS
# =========================

@login_required(login_url='admin_login')
@never_cache
def manage_cities(request):
    from users.models import City
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "add":
            name = request.POST.get("name")
            if name:
                City.objects.create(name=name)
                messages.success(request, f"City '{name}' added successfully!", extra_tags="admin_error")
        
        elif action == "edit":
            city_id = request.POST.get("city_id")
            name = request.POST.get("name")
            if city_id and name:
                city = City.objects.get(id=city_id)
                city.name = name
                city.save()
                messages.success(request, "City updated successfully!" ,extra_tags="admin_error")
        
        elif action == "delete":
            city_id = request.POST.get("city_id")
            if city_id:
                try:
                    City.objects.get(id=city_id).delete()
                    messages.success(request, "City deleted successfully!",extra_tags="admin_error")
                except Exception as e:
                    messages.error(request, f"Cannot delete: {str(e)}")
        
        return redirect('manage_cities')
    
    cities = City.objects.all().order_by('name')
    return render(request, 'admin_panel/manage_cities.html', {'cities': cities})


@login_required(login_url='admin_login')
@never_cache
def manage_courts(request):
    from users.models import Court
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "add":
            name = request.POST.get("name")
            if name:
                Court.objects.create(name=name)
                messages.success(request, f"Court '{name}' added successfully!",extra_tags="admin_error")
        
        elif action == "edit":
            court_id = request.POST.get("court_id")
            name = request.POST.get("name")
            if court_id and name:
                court = Court.objects.get(id=court_id)
                court.name = name
                court.save()
                messages.success(request, "Court updated successfully!",extra_tags="admin_error")
        
        elif action == "delete":
            court_id = request.POST.get("court_id")
            if court_id:
                try:
                    Court.objects.get(id=court_id).delete()
                    messages.success(request, "Court deleted successfully!",extra_tags="admin_error")
                except Exception as e:
                    messages.error(request, f"Cannot delete: {str(e)}")
        
        return redirect('manage_courts')
    
    courts = Court.objects.all().order_by('name')
    return render(request, 'admin_panel/manage_courts.html', {'courts': courts})



@login_required(login_url='admin_login')
@never_cache
def manage_practice_areas(request):
    from users.models import Category, SubCategory
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "add_category":
            name = request.POST.get("category_name")
            if name:
                Category.objects.create(name=name)
                messages.success(request, f"Category '{name}' added successfully!",extra_tags="admin_error")
        
        elif action == "add":
            name = request.POST.get("name")
            category_id = request.POST.get("category_id")
            if name and category_id:
                category = Category.objects.get(id=category_id)
                SubCategory.objects.create(name=name, category=category)
                messages.success(request, f"Practice area '{name}' added successfully!",extra_tags="admin_error")
        
        elif action == "edit":
            area_id = request.POST.get("area_id")
            name = request.POST.get("name")
            category_id = request.POST.get("category_id")
            if area_id and name and category_id:
                area = SubCategory.objects.get(id=area_id)
                area.name = name
                area.category_id = category_id
                area.save()
                messages.success(request, "Practice area updated successfully!",extra_tags="admin_error")
        
        elif action == "delete":
            area_id = request.POST.get("area_id")
            if area_id:
                try:
                    SubCategory.objects.get(id=area_id).delete()
                    messages.success(request, "Practice area deleted successfully!",extra_tags="admin_error")
                except Exception as e:
                    messages.error(request, f"Cannot delete: {str(e)}")
        
        return redirect('manage_practice_areas')
    
    categories = Category.objects.all().order_by('name')
    practice_areas = SubCategory.objects.all().select_related('category').order_by('category__name', 'name')
    
    context = {
        'categories': categories,
        'practice_areas': practice_areas
    }
    return render(request, 'admin_panel/manage_practice_areas.html', context)


@login_required(login_url='admin_login')
@never_cache
def manage_fee_bands(request):
    from users.models import FeeBand
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "add":
            name = request.POST.get("name")
            min_fee = request.POST.get("min_fee")
            max_fee = request.POST.get("max_fee")
            if name and min_fee and max_fee:
                FeeBand.objects.create(
                    name=name,
                    min_fee=int(min_fee),
                    max_fee=int(max_fee)
                )
                messages.success(request, f"Fee band '{name}' added successfully!",extra_tags="admin_error")
        
        elif action == "edit":
            band_id = request.POST.get("band_id")
            name = request.POST.get("name")
            min_fee = request.POST.get("min_fee")
            max_fee = request.POST.get("max_fee")
            if band_id and name and min_fee and max_fee:
                band = FeeBand.objects.get(id=band_id)
                band.name = name
                band.min_fee = int(min_fee)
                band.max_fee = int(max_fee)
                band.save()
                messages.success(request, "Fee band updated successfully!",extra_tags="admin_error")
        
        elif action == "delete":
            band_id = request.POST.get("band_id")
            if band_id:
                try:
                    FeeBand.objects.get(id=band_id).delete()
                    messages.success(request, "Fee band deleted successfully!",extra_tags="admin_error")
                except Exception as e:
                    messages.error(request, f"Cannot delete: {str(e)}")
        
        return redirect('manage_fee_bands')
    
    fee_bands = FeeBand.objects.all().order_by('min_fee')
    return render(request, 'admin_panel/manage_fee_bands.html', {'fee_bands': fee_bands})


@login_required(login_url='admin_login')
@never_cache
def mark_notification_read(request, id):
    from users.models import Notification
    
    notification = get_object_or_404(Notification, id=id)
    
    # Ensure the user can only read their own notifications
    if notification.recipient == request.user:
        notification.is_read = True
        notification.save()
        
        # Redirect to the link if it exists
        if notification.link:
            target_link = notification.link
            
            # PATCH 1: Fix legacy broken links
            if target_link.startswith('/admin_panel/'):
                target_link = target_link.replace('/admin_panel/', '/myadmin/', 1)
            
            # PATCH 2: Retroactive Highlighting for old/legacy notifications
            # If 'highlight_id' is NOT in URL but we are going to pending lawyers, try to find the ID.
            if 'pending-lawyers' in target_link and 'highlight_id' not in target_link:
                import re
                from users.models import User
                # Try to extract email from message: "Request from Name (email@example.com)" or similar
                # Simple regex for email extraction
                email_match = re.search(r'[\w\.-]+@[\w\.-]+', notification.message)
                if email_match:
                    email = email_match.group(0)
                    try:
                        user = User.objects.filter(email=email).first()
                        if user and hasattr(user, 'lawyer_profile'):
                            target_link += f"?highlight_id={user.lawyer_profile.id}"
                    except Exception:
                        pass # Fail silently
                
                # FALLBACK FOR VERY OLD NOTIFICATIONS (Name Only)
                # "Lawyer {name} has registered..."
                else:
                    name_match = re.search(r'Lawyer (.+) has registered', notification.message)
                    if name_match:
                        name_part = name_match.group(1).strip()
                        # Try to find user by first name (best effort)
                        try:
                            # This matches the creation logic: message=f"Lawyer {request.user.first_name}..."
                            user = User.objects.filter(first_name__iexact=name_part).first()
                            if user and hasattr(user, 'lawyer_profile'):
                                target_link += f"?highlight_id={user.lawyer_profile.id}"
                        except Exception:
                            pass

            return redirect(target_link)
            
    # Default fallback
    return redirect('admin_dashboard')
