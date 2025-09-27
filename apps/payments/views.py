# apps/payments/views.py
from datetime import timedelta
import stripe
from django.conf import settings
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import Subscription, SubscriptionPlan
from .serializers import CheckoutSessionSerializer, UserProfileSerializer

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Map duration keys to timedeltas (for predefined boosts)
DURATION_TO_DELTA = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "2d": timedelta(days=2),
    "5d": timedelta(days=5),
    "7d": timedelta(days=7),
    "10d": timedelta(days=10),
    # lifetime has no end_time
    "lifetime": None,
}

def _get_or_create_subscription(user) -> Subscription:
    """
    Ensure the user has a Subscription row.
    """
    sub, _ = Subscription.objects.get_or_create(user=user)
    # Resolve & persist auto-downgrade if needed
    sub.current_plan()
    return sub


class CreateCheckoutSessionView(generics.GenericAPIView):
    """
    POST /api/payments/create-checkout-session/
    Create a Stripe Checkout Session for Boost upgrades.
    Supports predefined durations or admin-created plans via plan_name.
    Blocks if user already has an active Boost.
    Body: 
    - {"duration": "1h" | "6h" | ... | "lifetime"} for predefined plans
    - {"plan_name": "<plan_name>"} for admin-created plans
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CheckoutSessionSerializer

    def post(self, request, *args, **kwargs):
        duration = request.data.get("duration")
        plan_name = request.data.get("plan_name")

        # Handle admin-created plan
        if plan_name:
            try:
                subscription_plan = SubscriptionPlan.objects.get(name=plan_name, is_paused=False)
                price_id = subscription_plan.stripe_price_id
                if not price_id:
                    return Response({"detail": "Plan has no associated Stripe price ID."}, status=status.HTTP_400_BAD_REQUEST)
            except SubscriptionPlan.DoesNotExist:
                return Response({"detail": "Plan not found or inactive."}, status=status.HTTP_400_BAD_REQUEST)
        # Handle predefined duration
        elif duration:
            if duration not in DURATION_TO_DELTA:
                return Response({"detail": "Invalid booster duration."}, status=status.HTTP_400_BAD_REQUEST)
            from .models import PRICE_ID_MAP  # Assuming this is defined in models.py or settings
            price_id = PRICE_ID_MAP.get(duration)
            if not price_id:
                return Response({"detail": "Invalid booster duration or missing price ID."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"detail": "Either duration or plan_name is required."}, status=status.HTTP_400_BAD_REQUEST)

        sub = _get_or_create_subscription(request.user)
        if sub.current_plan() == "boost" and sub.is_active_subscription():
            return Response(
                {"detail": "Boost is already active. You can cancel but cannot upgrade until it expires."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            # Use a hardcoded URL to ensure placeholder is recognized
            success_url = "http://localhost:8000/api/payments/confirm-success/?session_id={CHECKOUT_SESSION_ID}"
            cancel_url = "http://localhost:8000/payments/cancel/"

            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                mode="payment",
                line_items=[{"price": price_id, "quantity": 1}],
                customer_email=request.user.email,
                client_reference_id=str(request.user.id),
                metadata={
                    "user_id": str(request.user.id),
                    "plan_name": plan_name if plan_name else duration,
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )
            print("Constructed success_url:", success_url)
            print("Created Checkout Session:", checkout_session)
            return Response({"checkout_url": checkout_session.url}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ConfirmSuccessView(generics.GenericAPIView):
    """
    GET /api/payments/confirm-success/
    Handle Stripe success redirect and provide a basic response.
    Flutter app will override this with its own UI.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        session_id = request.GET.get("session_id")
        print("Received session_id:", session_id)
        if not session_id or session_id == "{CHECKOUT_SESSION_ID}":
            return Response({"detail": "Invalid or missing session ID."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = stripe.checkout.Session.retrieve(session_id)
            print("Retrieved Session:", session)
            if session.payment_status == "paid":
                return Response({"detail": "Payment successful. Redirecting to app..."}, status=status.HTTP_200_OK)
            else:
                return Response({"detail": "Payment not completed."}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.StripeError as e:
            return Response({"detail": f"Stripe error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Verification failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class UpgradeConfirmView(generics.GenericAPIView):
    """
    POST /api/payments/upgrade/confirm/
    Optional client-side confirmation after Stripe redirects back.
    Body: {"session_id": "<cs_test_...>"}
    - Verifies the Checkout Session is paid.
    - Activates Boost (idempotent).
    Webhook will also activate; this is just for faster UX.
    """
    permission_classes = [permissions.IsAuthenticated]

    # Mapping for plan display name and price (for predefined plans)
    PLAN_INFO = {
        "1h": {"name": "1 hour", "price": 8},
        "6h": {"name": "6 hours", "price": 18},
        "12h": {"name": "12 hours", "price": 28},
        "24h": {"name": "24 hours", "price": 38},
        "2d": {"name": "2 days", "price": 428},
        "5d": {"name": "5 days", "price": 628},
        "7d": {"name": "7 days", "price": 88},
        "10d": {"name": "10 days", "price": 108},
        "lifetime": {"name": "Lifetime", "price": 888},
    }

    def post(self, request, *args, **kwargs):
        session_id = request.data.get("session_id")
        if not session_id:
            return Response({"detail": "session_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = stripe.checkout.Session.retrieve(session_id, expand=["payment_intent"])
        except Exception as e:
            return Response({"detail": f"Unable to retrieve session: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        if session.mode != "payment":
            return Response({"detail": "Invalid session mode."}, status=status.HTTP_400_BAD_REQUEST)

        if session.payment_status != "paid":
            return Response({"detail": "Payment not completed."}, status=status.HTTP_400_BAD_REQUEST)

        # Metadata from Stripe
        plan_name = (session.metadata or {}).get("plan_name")
        user_id_meta = (session.metadata or {}).get("user_id")
        if not plan_name:
            return Response({"detail": "Missing plan_name in session metadata."}, status=status.HTTP_400_BAD_REQUEST)

        if str(request.user.id) != str(user_id_meta):
            return Response({"detail": "Session does not belong to the authenticated user."}, status=status.HTTP_403_FORBIDDEN)

        # Activate subscription
        sub = _get_or_create_subscription(request.user)
        now = timezone.now()

        if plan_name in self.PLAN_INFO:  # Predefined plan
            plan_info = self.PLAN_INFO[plan_name]
            if plan_name == "lifetime":
                sub.plan_type = "boost"
                sub.plan_name = plan_info["name"]
                sub.plan_price = plan_info["price"]
                sub.start_time = now
                sub.end_time = None
                sub.is_active = True
                sub.is_renewed = False
                sub.is_paused = False  # Explicitly set to play state
                sub.last_payment_date = now
                sub.save(update_fields=["plan_type", "plan_name", "plan_price", "start_time", "end_time", "is_active", "is_renewed", "is_paused", "last_payment_date"])
            else:
                delta = DURATION_TO_DELTA[plan_name]
                sub.plan_type = "boost"
                sub.plan_name = plan_info["name"]
                sub.plan_price = plan_info["price"]
                sub.plan_duration = delta
                sub.start_time = now
                sub.end_time = now + delta
                sub.is_active = True
                sub.is_renewed = False
                sub.is_paused = False  # Explicitly set to play state
                sub.last_payment_date = now
                sub.save(update_fields=["plan_type", "plan_name", "plan_price", "plan_duration", "start_time", "end_time", "is_active", "is_renewed", "is_paused", "last_payment_date"])
        else:  # Admin-created plan
            try:
                subscription_plan = SubscriptionPlan.objects.get(name=plan_name)
                sub.plan_type = "boost"
                sub.plan_name = subscription_plan.name
                sub.plan_price = subscription_plan.price
                sub.plan_duration = subscription_plan.duration
                sub.start_time = now
                sub.end_time = now + subscription_plan.duration if subscription_plan.duration else None
                sub.is_active = True
                sub.is_renewed = False
                sub.is_paused = False  # Explicitly set to play state
                sub.last_payment_date = now
                sub.save(update_fields=["plan_type", "plan_name", "plan_price", "plan_duration", "start_time", "end_time", "is_active", "is_renewed", "is_paused", "last_payment_date"])
            except SubscriptionPlan.DoesNotExist:
                return Response({"detail": "Plan not found."}, status=status.HTTP_400_BAD_REQUEST)

        sub.user.recalc_premium_status()

        return Response(
            {
                "detail": "Boost activated.",
                "plan_type": sub.plan_type,
                "plan_name": sub.plan_name,
                "plan_price": f"HK ${sub.plan_price}",
                "end_time": sub.end_time,
            },
            status=status.HTTP_200_OK,
        )


class CancelSubscriptionView(generics.GenericAPIView):
    """
    POST /api/payments/cancel/
    Early-cancel an active Boost (one-off product). This does not refund.
    Sets user back to Free immediately.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        sub = _get_or_create_subscription(request.user)

        if sub.current_plan() != "boost" or not sub.is_active_subscription():
            return Response({"detail": "No active Boost to cancel."}, status=status.HTTP_400_BAD_REQUEST)

        sub.plan_type = "free"
        sub.plan_name = None
        sub.plan_price = None
        sub.plan_duration = None
        sub.end_time = None
        sub.is_active = False
        sub.is_renewed = False
        sub.save(update_fields=["plan_type", "plan_name", "plan_price", "plan_duration", "end_time", "is_active", "is_renewed"])
        sub.user.recalc_premium_status()

        return Response({"detail": "Boost canceled. You are now on the Free plan."}, status=status.HTTP_200_OK)


class UserProfileView(generics.RetrieveAPIView):
    """
    GET /api/payments/profile/
    Returns user profile with plan & time remaining.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user