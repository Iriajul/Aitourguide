# apps/payments/webhook.py
import stripe
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta
from django.views.decorators.csrf import csrf_exempt
from apps.users.models import User
from .models import Subscription

stripe.api_key = settings.STRIPE_SECRET_KEY
WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET

# Map price IDs to plan metadata
PRICE_META = {
    settings.BOOST_1H_PRICE_ID: {"name": "1 hour", "price": 8, "duration": timedelta(hours=1)},
    settings.BOOST_6H_PRICE_ID: {"name": "6 hours", "price": 18, "duration": timedelta(hours=6)},
    settings.BOOST_12H_PRICE_ID: {"name": "12 hours", "price": 28, "duration": timedelta(hours=12)},
    settings.BOOST_24H_PRICE_ID: {"name": "24 hours", "price": 38, "duration": timedelta(hours=24)},
    settings.BOOST_2D_PRICE_ID: {"name": "2 days", "price": 428, "duration": timedelta(days=2)},
    settings.BOOST_5D_PRICE_ID: {"name": "5 days", "price": 628, "duration": timedelta(days=5)},
    settings.BOOST_7D_PRICE_ID: {"name": "7 days", "price": 88, "duration": timedelta(days=7)},
    settings.BOOST_10D_PRICE_ID: {"name": "10 days", "price": 108, "duration": timedelta(days=10)},
    settings.BOOST_LIFETIME_PRICE_ID: {"name": "Lifetime", "price": 888, "duration": None},
}


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_email")

        # Get price_id from the session's line items
        try:
            line_items = stripe.checkout.Session.list_line_items(session["id"])
            price_id = line_items.data[0].price.id if line_items.data else None
        except Exception:
            return HttpResponse(status=400)

        if not price_id or price_id not in PRICE_META:
            return HttpResponse(status=400)

        try:
            user = User.objects.get(email=customer_email)
            subscription, _ = Subscription.objects.get_or_create(user=user)
            meta = PRICE_META[price_id]
            now = timezone.now()

            # Lifetime plan
            if price_id == settings.BOOST_LIFETIME_PRICE_ID:
                subscription.plan_type = "boost"
                subscription.plan_name = meta["name"]
                subscription.plan_price = meta["price"]
                subscription.plan_duration = None
                subscription.start_time = now
                subscription.end_time = None
                subscription.is_active = True
                subscription.is_renewed = False
                subscription.last_payment_date = now
            else:
                delta = meta["duration"]

                # If user already has lifetime boost → do nothing
                if subscription.plan_type == "boost" and subscription.end_time is None:
                    return HttpResponse(status=200)

                # If user has active boost → extend
                if subscription.end_time and subscription.end_time > now:
                    subscription.end_time += delta
                else:
                    subscription.end_time = now + delta
                    subscription.start_time = now

                subscription.plan_type = "boost"
                subscription.plan_name = meta["name"]
                subscription.plan_price = meta["price"]
                subscription.plan_duration = delta
                subscription.is_active = True
                subscription.is_renewed = False
                subscription.last_payment_date = now

            subscription.save(update_fields=[
                "plan_type",
                "plan_name",
                "plan_price",
                "plan_duration",
                "start_time",
                "end_time",
                "is_active",
                "is_renewed",
                "last_payment_date",
            ])
            subscription.user.recalc_premium_status()

        except User.DoesNotExist:
            return HttpResponse(status=400)

    return HttpResponse(status=200)
