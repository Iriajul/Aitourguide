from django.urls import path
from .views import (
    CreateCheckoutSessionView,
    UpgradeConfirmView,
    CancelSubscriptionView,
    UserProfileView,
    ConfirmSuccessView,
    SubscriptionPlansListView,
)
from .webhook import stripe_webhook

urlpatterns = [
    path("create-checkout-session/", CreateCheckoutSessionView.as_view(), name="create-checkout-session"),
    path("upgrade/confirm/", UpgradeConfirmView.as_view(), name="upgrade-confirm"),
    path("cancel/", CancelSubscriptionView.as_view(), name="cancel-subscription"),
    path("profile/", UserProfileView.as_view(), name="user-profile"),
    path("webhook/", stripe_webhook, name="stripe-webhook"),
    path('confirm-success/', ConfirmSuccessView.as_view(), name='confirm-success'),
    path('subscription-plans/', SubscriptionPlansListView.as_view(), name='subscription-plans-list'),
]
