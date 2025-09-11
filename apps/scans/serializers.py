# apps/scans/serializers.py
from rest_framework import serializers
from .models import Scan
from apps.users.models import User

class ScanSerializer(serializers.ModelSerializer):
    # User info nested (optional) for better overview
    user_email = serializers.SerializerMethodField(read_only=True)
    activity_type = serializers.SerializerMethodField(read_only=True)  # New field for admin dashboard

    class Meta:
        model = Scan
        fields = [
            "id",
            "user",
            "user_email",
            "image_url",          # Cloudinary URL
            "result_text",        # AI analysis text
            "created_at",         # timestamp
            "latitude",
            "longitude",
            "location_name",
            "is_boosted",
            "scan_duration_minutes",
            "processed",
            "engagement_score",
            "source",             # New field for source (camera/gallery)
            "activity_type",      # New field for mapped activity type
        ]
        read_only_fields = [
            "user",
            "user_email",
            "result_text",
            "created_at",
            "image_url",
            "processed",
            "engagement_score",
            "is_boosted",
            "scan_duration_minutes",
            "activity_type",      # Read-only as it's derived
        ]

    def get_user_email(self, obj):
        return obj.user.email if obj.user else None

    def get_activity_type(self, obj):
        """Map source to activity type for the admin dashboard."""
        return "Clicked" if obj.source == "camera" else "Upload"

    # Optional: auto-update user's total scans dynamically
    def create(self, validated_data):
        scan = super().create(validated_data)
        user = scan.user
        if user:
            user.increment_scans()  # Increment total_scans field in User
            user.update_last_activity()
        return scan

    def update(self, instance, validated_data):
        scan = super().update(instance, validated_data)
        user = scan.user
        if user:
            user.update_last_activity()
        return scan