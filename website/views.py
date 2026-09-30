from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import get_user_model
from .models import Product, HealthCondition, CallbackRequest, Order, Review, FAQ, BlogPost
from .forms import CallbackRequestForm, OrderForm
from django.contrib import messages
from django.core.mail import EmailMessage
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings

User = get_user_model()


def home(request):
    products = Product.objects.all()[:6]
    featured = products[:3]
    return render(request, 'website/home.html', {'products': products, 'featured': featured})


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug)
    return render(request, 'website/product_detail.html', {'product': product})


def condition_detail(request, slug):
    condition = get_object_or_404(HealthCondition, slug=slug)
    recommended = condition.recommended_products.all()
    return render(request, 'website/condition_detail.html', {'condition': condition, 'recommended': recommended})


def callback_request(request):
    if request.method == 'POST':
        form = CallbackRequestForm(request.POST)
        if form.is_valid():
            cb = form.save()
            try:
                from customerleads.models import Lead
                fallback_user = User.objects.filter(is_active=True).first()
                if fallback_user:
                    Lead.objects.create(
                        name=cb.full_name,
                        email='',
                        phone=cb.phone_number,
                        company='',
                        status='pending',
                        priority='medium',
                        source='website',
                        created_by=fallback_user,
                    )
            except Exception:
                pass
            return redirect('website:callback_thanks')
    else:
        form = CallbackRequestForm()
    return render(request, 'website/callback_form.html', {'form': form})


def order_create(request):
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save()
            return redirect('website:order_thanks')
    else:
        form = OrderForm()
    return render(request, 'website/order_form.html', {'form': form})


def contact(request):
    return render(request, 'website/contact.html')


def about(request):
    return render(request, 'website/about.html')


def faqs(request):
    faqs = FAQ.objects.all().order_by('-created_at')
    return render(request, 'website/faqs.html', {'faqs': faqs})


def blog_list(request):
    posts = BlogPost.objects.filter(published=True).order_by('-published_at')
    return render(request, 'website/blog_list.html', {'posts': posts})


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost, slug=slug, published=True)
    return render(request, 'website/blog_detail.html', {'post': post})

def contact(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        subject = request.POST.get("subject") or "Website Contact Form"
        message = request.POST.get("message")

        body = f"""
        Name: {name}
        Email: {email}

        Message:
        {message}
        """

        mail = EmailMessage(
            subject,
            body,
            "chipcodetechnologies@gmail.com",
            ["chipcodetechnologies@gmail.com"],
            reply_to=[email],
        )

        mail.send()

        messages.success(request, "Your message has been sent successfully.")

    return render(request, "website/contact.html")


@require_POST
def website_order_submit(request):
    try:
        from customerleads.models import Lead
        fallback_user = User.objects.filter(is_active=True).first()
        
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        product_id = request.POST.get('product')
        
        if not name or not phone:
            return JsonResponse({'success': False, 'error': 'Name and phone are required.'})
        
        lead = Lead(
            name=name,
            phone=phone,
            email='',
            status='pending',
            priority='medium',
            source='website',
            created_by=fallback_user or User.objects.first(),
        )
        
        if product_id:
            from .models import Product
            try:
                product = Product.objects.get(id=product_id)
                lead.company = product.title
            except Product.DoesNotExist:
                pass
        
        lead.save()
        
        return JsonResponse({'success': True, 'message': 'Order submitted successfully! We will contact you soon.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})