from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
import logging
import geocoder

from .models import User, OtpToken
from .serializers import UserSerializer
from .signals import create_token, send_user_password, send_account_deletion_confirmation

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def getUsers(request):
    users = User.objects.all()
    serializer = UserSerializer(users, many=True)
    return Response(
        {"message": "Fetch successful!", "users": serializer.data},
        status=status.HTTP_200_OK
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def getUser(request):
    user = request.user
    serializer = UserSerializer(user) 
    return Response(
        {"message": "Fetch successful!", "user": serializer.data},
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def registerUser(request):
    email = request.data.get('email', '').strip()
    if not email:
        return Response({"error": "Email is required!"}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email=email).exists():
        return Response({"error": "Email exists!"}, status=status.HTTP_409_CONFLICT)

    temp_password = User.generate_password()

    user_data = request.data.copy()
    user_data['password'] = temp_password
    user_data['temp_password'] = temp_password
    user_data['temp_password_expires'] = timezone.now() + timedelta(hours=24)

    serializer = UserSerializer(data=user_data)
    if serializer.is_valid():
        user = serializer.save()
        user.is_active = False
        user.save()

        try:
            create_token(user)
            logger.info(f"OTP sent to new user {user.email}")
        except Exception as e:
            logger.error(f"Failed to send OTP to {user.email}: {e}")
            return Response(
                {"error": f"Failed to send OTP to {user.email}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {"message": "User registered successfully. Check your email for OTP.", "user": serializer.data},
            status=status.HTTP_201_CREATED
        )

    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def verifyUserEmail(request):
    email = request.data.get('email', '').strip()
    otp_code = request.data.get('otp_code', '').strip()

    if not email or not otp_code:
        return Response({"message": "Email and OTP code are required."}, status=status.HTTP_400_BAD_REQUEST)

    user = get_object_or_404(User, email=email)
    user_otp = OtpToken.objects.filter(user=user).last()

    if not user_otp:
        return Response({"message": "No OTP found for this user."}, status=status.HTTP_404_NOT_FOUND)

    if timezone.now() > user_otp.otp_expires_at:
        return Response({"message": "OTP expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

    if user_otp.otp_code.lower() != otp_code.lower():
        return Response({"message": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)

    user.is_active = True
    user.temp_password_expires = None
    
    try:
        if user.temp_password:
            send_user_password(user, user.temp_password)
            logger.info(f"Password sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send password to {user.email}: {e}")

    user.temp_password = None
    user.save()
    user_otp.delete()

    return Response({"message": "Account activated successfully! Password sent via email."}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def resendOtp(request):
    email = request.data.get('email', '').strip()
    if not email:
        return Response({"message": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

    user = get_object_or_404(User, email=email)
    
    OtpToken.objects.filter(user=user).delete()

    try:
        create_token(user)
        logger.info(f"OTP resent for user {user.email}")
    except Exception as e:
        logger.error(f"Failed to resend OTP for {user.email}: {e}")
        return Response({"message": "Failed to send OTP."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"message": "A new OTP has been sent to your email."}, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def deleteUser(request):
    user = request.user
    otp_code = request.data.get('otp_code')

    if not otp_code:
        try:
            create_token(user)
            send_account_deletion_confirmation(user)
            return Response({"message": "OTP sent. Confirm with code to delete account."}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Failed to send deletion OTP: {e}")
            return Response({"error": "Failed to send OTP."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    user_otp = OtpToken.objects.filter(user=user).last()
    if not user_otp or user_otp.otp_code.lower() != otp_code.lower() or timezone.now() > user_otp.otp_expires_at:
        return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

    email = user.email
    user_otp.delete() 
    user.delete()
    
    return Response({"message": f"Account {email} successfully deleted."}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def loginUser(request):
    email = request.data.get('email', '').strip()
    password = request.data.get('password', '').strip()

    if not email or not password:
        return Response({"error": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)

    if user.temp_password:
        if password == user.temp_password:
            if user.temp_password_expires is None or timezone.now() > user.temp_password_expires:
                return Response(
                    {"error": "Temporary password expired. Please reset your password."},
                    status=status.HTTP_403_FORBIDDEN
                )

            return Response(
                {
                    "error": "Please set a new password.",
                    "requires_new_password": True
                }, 
                status=status.HTTP_403_FORBIDDEN
            )

    if not user.check_password(password):
        return Response({"error": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)

    if not user.is_active:
        return Response({"error": "Account is inactive."}, status=status.HTTP_400_BAD_REQUEST)

    login_ip = request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR')
    try:
        geo = geocoder.ip(login_ip)
        user.last_login_ipa = [str(geo.ip), str(geo.city), str(geo.country)]
    except Exception as e:
        logger.warning(f"Could not geolocate IP {login_ip}: {e}")
        user.last_login_ipa = [login_ip]
    
    user.login_count = (user.login_count or 0) + 1
    user.save()

    serializer = UserSerializer()
    payload = {
        "user_id": user.moti_id,
        "email": user.email,
        "exp": timezone.now() + timedelta(hours=6),
        "iat": timezone.now()
    }
    jwt_token = serializer.encode_jwt(payload=payload)

    user_data = {
        "email": user.email,
        "moti_id": user.moti_id,
        "role": user.role,
        "last_login_ipa": user.last_login_ipa
    }

    return Response(
        {"message": "Login successful", "user": user_data, "token": jwt_token},
        status=status.HTTP_200_OK
    )