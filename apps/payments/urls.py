from django.urls import path
from .views import (
    CreateCheckoutSessionView,
    UpgradeConfirmView,
    CancelSubscriptionView,
    UserProfileView
)
from .webhook import stripe_webhook

urlpatterns = [
    path("create-checkout-session/", CreateCheckoutSessionView.as_view(), name="create-checkout-session"),
    path("upgrade/confirm/", UpgradeConfirmView.as_view(), name="upgrade-confirm"),
    path("cancel/", CancelSubscriptionView.as_view(), name="cancel-subscription"),
    path("profile/", UserProfileView.as_view(), name="user-profile"),
    path("webhook/", stripe_webhook, name="stripe-webhook"),
]
