# apps/admin_panel/serializers.py
from rest_framework import serializers
from apps.users.models import User
from apps.scans.models import Scan

class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "is_active", "date_joined"]

class AdminScanSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Scan
        fields = ["id", "user", "image", "result_text", "created_at"]
