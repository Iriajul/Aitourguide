# apps/admin_panel/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.users.models import User
from apps.scans.models import Scan
from .serializers import AdminUserSerializer, AdminScanSerializer
from apps.users.permissions import IsAdminRole

class AdminDashboardView(APIView):
    """
    Single endpoint for admin dashboard:
    - Users list
    - Recent scans
    - App analytics
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        # Users
        users = User.objects.all()
        users_data = AdminUserSerializer(users, many=True).data

        # Recent scans
        recent_scans = Scan.objects.order_by("-created_at")[:20]  # last 20 scans
        recent_scans_data = AdminScanSerializer(recent_scans, many=True).data

        # Analytics
        total_users = users.count()
        total_scans = Scan.objects.count()

        return Response({
            "analytics": {
                "total_users": total_users,
                "total_scans": total_scans,
            },
            "users": users_data,
            "recent_scans": recent_scans_data
        })
