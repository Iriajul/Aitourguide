from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User
from django.core.validators import RegexValidator


# -----------------------------
# Signup serializer
# -----------------------------
class UserSignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True, label="Confirm password")
    agree_terms = serializers.BooleanField(write_only=True, required=True)
    
    username = serializers.CharField(
        max_length=150,
        required=True,
        validators=[
            RegexValidator(
                regex=r'^[\w.@+\-_\s]+$',  # Allows letters, numbers, spaces, and the specified special characters
                message="Enter a valid username. This value may contain only letters, numbers, spaces, and @/./+/-/_ characters."
            )
        ]
    )

    class Meta:
        model = User
        fields = ("username", "email", "password", "password2", "agree_terms")

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password2"):
            raise serializers.ValidationError({"password": "Passwords must match."})
        if not attrs.get("agree_terms"):
            raise serializers.ValidationError({"agree_terms": "You must agree to the Terms and Conditions."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2", None)
        validated_data.pop("agree_terms", None)
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email"),
            password=validated_data["password"],
            role="registered"
        )


# -----------------------------
# Serializer for returning user info
# -----------------------------
class UserSerializer(serializers.ModelSerializer):
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "role",
            "profile_picture",
            "free_scans_used",
            "last_login_time",
            "last_activity_time",
            "total_searches",
            "total_scans",
            "total_premium_days",
            "is_active_premium",
        )
        read_only_fields = ("id", "email", "role")

    def get_profile_picture(self, obj):
        return obj.get_profile_picture


# -----------------------------
# Login serializer
# -----------------------------
class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        if email and password:
            user = authenticate(request=self.context.get("request"), username=email, password=password)
            if not user:
                raise serializers.ValidationError("Invalid email or password.")
        else:
            raise serializers.ValidationError("Email and password are required.")

        attrs["user"] = user  # Store the actual User instance
        return attrs

    def create(self, validated_data):
        """
        Returns the actual User instance along with JWT tokens
        """
        user = validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return {
            "user": user,  # <-- now a real User instance
            "access": str(refresh.access_token),
            "refresh": str(refresh)
        }


# -----------------------------
# Edit Profile serializer
# -----------------------------
class EditProfileSerializer(serializers.ModelSerializer):
    old_password = serializers.CharField(write_only=True, required=False)
    new_password = serializers.CharField(write_only=True, required=False)
    profile_picture_file = serializers.ImageField(write_only=True, required=False)
    email = serializers.EmailField(read_only=True)  # Added email as read-only
    
    username = serializers.CharField(
        max_length=150,
        required=False,
        validators=[
            RegexValidator(
                regex=r'^[\w.@+\-_\s]+$',  # Allows letters, numbers, spaces, and the specified special characters
                message="Enter a valid username. This value may contain only letters, numbers, spaces, and @/./+/-/_ characters."
            )
        ]
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",  # Added to fields list
            "old_password",
            "new_password",
            "profile_picture_file",
            "free_scans_used",
            "total_searches",
            "total_scans",
            "total_premium_days",
            "is_active_premium",
        )
        extra_kwargs = {
            "username": {"required": False, "allow_blank": True},
            "profile_picture_file": {"required": False},
            "email": {"read_only": True},  # Explicitly set as read-only
        }

    def validate(self, attrs):
        user = self.instance
        old_password = attrs.get("old_password")
        new_password = attrs.get("new_password")

        if old_password or new_password:
            if not old_password:
                raise serializers.ValidationError({"old_password": "Old password is required."})
            if not new_password:
                raise serializers.ValidationError({"new_password": "New password is required."})
            if not user.check_password(old_password):
                raise serializers.ValidationError({"old_password": "Old password is incorrect."})

        return attrs

    def update(self, instance, validated_data):
        username = validated_data.get("username")
        if username:
            instance.username = username

        old_password = validated_data.pop("old_password", None)
        new_password = validated_data.pop("new_password", None)
        if old_password and new_password:
            instance.set_password(new_password)

        profile_picture_file = validated_data.get("profile_picture_file")
        if profile_picture_file:
            instance.update_profile_picture(profile_picture_file)

        for field in ["free_scans_used", "total_searches", "total_scans", "total_premium_days", "is_active_premium"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        instance.save()
        return instance

# -----------------------------
# Forgot password / OTP / Reset password serializers
# -----------------------------
class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyOtpSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)
    otp_token = serializers.CharField(required=True)


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    otp_token = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs.get('new_password') != attrs.get('confirm_password'):
            raise serializers.ValidationError({"password": "Passwords must match."})
        return attrs


# -----------------------------
# Logout serializer
# -----------------------------
class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
