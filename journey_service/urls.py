from django.urls import path
from . import views

urlpatterns = [
    path('journey/<int:journey_id>/', views.getJourney, name='get-journey'),
    path('journey/', views.getJourney, name='get-journey-by-data'),
    path('journeys/', views.getAllJourneys, name='get-all-journeys'),
    path('journey/start/', views.startJourney, name='start-journey'),
    path('journey/complete/', views.completeJourney, name='complete-journey'),
    path('journey/update-progress/', views.updateJourneyProgress, name='update-journey-progress'),
    path('journey/add-break-point/', views.addBreakPoint, name='add-break-point'),
    path('journey/cancel/', views.cancelJourney, name='cancel-journey'),
]