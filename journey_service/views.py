import logging
import geocoder
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Journey

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def getJourney(request, journey_id=None):

    if not journey_id:
        journey_id = request.query_params.get('journey_id')

    if not journey_id:
        return Response(
            {"error": "journey_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user
    journey = get_object_or_404(Journey, id=journey_id, user=user)

    journey_data = {
        "journey_id": journey.id,
        "user": journey.user.username,
        "departure": journey.onboarding_location,
        "departure_time": journey.onboarding_time,
        "destination": journey.destination_location,
        "destination_time": journey.destination_time,
        "cumulative_distance": journey.cumulative_distance,
        "cumulative_time": journey.cumulative_journey_duration,
        "duration_hours": journey.journey_duration_hours,
        "status": journey.status,
        "route_used": journey.route_used,
        "last_login_method": journey.last_login_method,
        "created_at": journey.created_at
    }

    return Response(
        {
            "message": "Journey retrieved successfully",
            "journey_data": journey_data
        },
        status=status.HTTP_200_OK
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def getAllJourneys(request):
    user = request.user
    journeys = Journey.objects.filter(user=user).order_by('-created_at')

    if not journeys.exists():
        return Response(
            {"error": "No journeys found for this user"},
            status=status.HTTP_404_NOT_FOUND
        )

    data = []
    for j in journeys:
        data.append({
            "user": j.user.username,
            "departure": j.onboarding_location,
            "departure_time": j.onboarding_time,
            "destination": j.destination_location,
            "destination_time": j.destination_time,
            "cumulative_distance": j.cumulative_distance,
            "cumulative_time": j.cumulative_journey_duration,
            "duration_hours": j.journey_duration_hours,
            "status": j.status,
            "route_used": j.route_used,
            "last_login_method": j.last_login_method,
            "created_at": j.created_at
        })

    return Response(
        {
            "message": "User journeys retrieved successfully",
            "total_journeys": len(data),
            "journeys": data
        },
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def startJourney(request):
    user = request.user

    destination = request.data.get('destination')
    onboarding_location = request.data.get('onboarding_location')
    route_used = request.data.get('route_used', [])
    last_login_method = request.data.get('last_login_method', 'email_password')

    if not destination:
        return Response({"error": "destination field is required"},
                        status=status.HTTP_400_BAD_REQUEST)

    if not onboarding_location:
        ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
        try:
            addr = geocoder.ip(ip)
            if addr.ok:
                onboarding_location = f"{addr.city}, {addr.country}" if addr.city else ip
            else:
                onboarding_location = ip
        except Exception as e:
            logger.error(f"IP lookup failed: {e}")
            onboarding_location = ip or "Unknown location"

    active_journey = Journey.objects.filter(user=user, status="active").first()
    if active_journey:
        return Response(
            {
                "error": "User already has an active journey",
                "active_journey_id": active_journey.id
            },
            status=status.HTTP_409_CONFLICT
        )

    valid_login_methods = dict(Journey.LOGIN_METHOD_CHOICES)
    if last_login_method not in valid_login_methods:
        last_login_method = 'email_password'

    try:
        journey = Journey.objects.create(
            user=user,
            onboarding_location=onboarding_location,
            destination_location=destination,
            status="active",
            cumulative_distance=0,
            cumulative_journey_duration=0,
            route_used=route_used,
            last_login_method=last_login_method,
        )

        return Response(
            {
                "message": "Journey started successfully",
                "journey_id": journey.id,
                "onboarding_location": journey.onboarding_location,
                "destination": journey.destination_location,
                "start_time": journey.onboarding_time,
                "status": journey.status
            },
            status=status.HTTP_201_CREATED
        )

    except Exception as e:
        logger.error(f"Error starting journey: {e}")
        return Response(
            {"error": "Failed to start journey"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def completeJourney(request):
    journey_id = request.data.get("journey_id")
    user = request.user

    if not journey_id:
        return Response({"error": "journey_id is required"},
                        status=status.HTTP_400_BAD_REQUEST)

    journey = get_object_or_404(Journey, id=journey_id, user=user)

    if journey.status != "active":
        return Response({"error": "Journey is not active"},
                        status=status.HTTP_400_BAD_REQUEST)

    journey.complete_journey()

    return Response(
        {
            "message": "Journey completed successfully",
            "journey_id": journey.id,
            "completion_time": journey.destination_time,
            "total_duration_minutes": journey.cumulative_journey_duration,
            "total_duration_hours": journey.journey_duration_hours,
            "total_distance": journey.cumulative_distance,
        },
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def updateJourneyProgress(request):
    journey_id = request.data.get("journey_id")
    user = request.user

    if not journey_id:
        return Response({"error": "journey_id is required"},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        additional_duration = int(request.data.get("additional_duration", 0))
        additional_distance = float(request.data.get("additional_distance", 0))
    except ValueError:
        return Response(
            {"error": "Duration must be int, distance must be numeric"},
            status=status.HTTP_400_BAD_REQUEST
        )

    journey = get_object_or_404(Journey, id=journey_id, user=user)

    if journey.status != "active":
        return Response({"error": "Can only update active journeys"},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        journey.update_duration_and_distance(additional_duration, additional_distance)

        return Response(
            {
                "message": "Progress updated successfully",
                "journey_id": journey.id,
                "cumulative_duration": journey.cumulative_journey_duration,
                "cumulative_distance": journey.cumulative_distance,
                "duration_hours": journey.journey_duration_hours
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Error updating progress: {e}")
        return Response({"error": "Update failed"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def addBreakPoint(request):
    journey_id = request.data.get("journey_id")
    break_location = request.data.get("break_location")
    user = request.user

    if not journey_id or not break_location:
        return Response(
            {"error": "journey_id and break_location are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    journey = get_object_or_404(Journey, id=journey_id, user=user)

    if journey.status != "active":
        return Response({"error": "Can only add break points to active journeys"},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        route = journey.route_used or []
        route.append(break_location)
        journey.route_used = route
        journey.save()

        return Response(
            {
                "message": "Break point added successfully",
                "journey_id": journey.id,
                "break_location": break_location,
                "route_used": journey.route_used
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Error adding break point: {e}")
        return Response({"error": "Failed to add break point"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancelJourney(request):
    journey_id = request.data.get("journey_id")
    user = request.user

    if not journey_id:
        return Response({"error": "journey_id is required"},
                        status=status.HTTP_400_BAD_REQUEST)

    journey = get_object_or_404(Journey, id=journey_id, user=user)

    if journey.status != "active":
        return Response({"error": "Can only cancel active journeys"},
                        status=status.HTTP_400_BAD_REQUEST)

    journey.status = "cancelled"
    journey.save()

    return Response(
        {
            "message": "Journey cancelled successfully",
            "journey_id": journey.id,
        },
        status=status.HTTP_200_OK
    )
