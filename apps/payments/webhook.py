# apps/payments/webhook.py
import stripe
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from apps.users.models import User
from .models import Subscription, Payment, SubscriptionPlan

stripe.api_key = settings.STRIPE_SECRET_KEY
WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_email")

        try:
            line_items = stripe.checkout.Session.list_line_items(session["id"])
            price_id = line_items.data[0].price.id if line_items.data else None
        except Exception:
            return HttpResponse(status=400)

        if not price_id:
            return HttpResponse(status=400)

        try:
            user = User.objects.get(email=customer_email)
            subscription, _ = Subscription.objects.get_or_create(user=user)
            plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)

            now = timezone.now()
            if plan.duration is None:  # Lifetime plan
                subscription.plan_type = "boost"
                subscription.plan_name = plan.name
                subscription.plan_price = plan.price
                subscription.plan_duration = None
                subscription.start_time = now
                subscription.end_time = None
                subscription.is_active = True
                subscription.is_renewed = False
                subscription.last_payment_date = now
                subscription.plan = plan
                subscription.is_paused = False  # Explicitly set to play state
            else:
                delta = plan.duration
                if subscription.plan_type == "boost" and subscription.end_time is None:
                    return HttpResponse(status=200)
                if subscription.end_time and subscription.end_time > now:
                    subscription.end_time += delta
                else:
                    subscription.end_time = now + delta
                    subscription.start_time = now
                subscription.plan_type = "boost"
                subscription.plan_name = plan.name
                subscription.plan_price = plan.price
                subscription.plan_duration = delta
                subscription.is_active = True
                subscription.is_renewed = False
                subscription.last_payment_date = now
                subscription.plan = plan
                subscription.is_paused = False  # Explicitly set to play state

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
                "plan",
                "is_paused"  # Add to update_fields
            ])
            subscription.user.recalc_premium_status()

            # Fetch payment intent without expand, handle card type safely
            payment_intent_id = session.get("payment_intent")
            card_type = None
            if payment_intent_id:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                if hasattr(payment_intent, "payment_method_details") and payment_intent.payment_method_details:
                    if hasattr(payment_intent.payment_method_details, "card"):
                        card_type = payment_intent.payment_method_details.card.brand

            Payment.objects.create(
                user=user,
                amount=plan.price,
                payment_date=now,
                stripe_payment_id=session.get("id"),
                subscription=subscription,
                card_type=card_type
            )

        except (User.DoesNotExist, SubscriptionPlan.DoesNotExist):
            return HttpResponse(status=400)

    return HttpResponse(status=200)