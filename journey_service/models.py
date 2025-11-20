from django.db import models
from django.core.validators import MinLengthValidator, MinValueValidator, MaxValueValidator
from django.contrib.postgres.fields import ArrayField 
from user_service.models import User

class Journey(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('paused', 'Paused'),
    ]
    
    LOGIN_METHOD_CHOICES = [
        ('email_password', 'Email/Password'),
        ('google_oauth', 'Google OAuth'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='journeys')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    onboarding_location = models.CharField(max_length=255, blank=True, null=True)
    onboarding_time = models.DateTimeField(auto_now_add=True)
    destination_location = models.CharField(max_length=255, blank=False, null=False)
    destination_time = models.DateTimeField(auto_now=True)
    cumulative_distance = models.FloatField(blank=True, null=True, validators=[MinValueValidator(0)])
    cumulative_journey_duration = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])  # in minutes
    route_used = ArrayField(
        models.CharField(max_length=255),
        blank=True,
        default=list
    )
    last_login_method = models.CharField(
        max_length=20, 
        choices=LOGIN_METHOD_CHOICES, 
        default='email_password'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'journeys'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_id']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Journey {self.id} for {self.username} ({self.status})"

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def journey_duration_hours(self):
        if self.cumulative_journey_duration:
            return round(self.cumulative_journey_duration / 60, 2)
        return 0

    def add_break_point(self, location):
        if not self.journey_break_points:
            self.journey_break_points = []
        self.journey_break_points.append(location)
        self.save()

    def complete_journey(self):
        self.status = 'completed'
        self.save()

    def update_duration_and_distance(self, additional_duration, additional_distance):
        self.cumulative_journey_duration = (self.cumulative_journey_duration or 0) + additional_duration
        self.cumulative_distance = (self.cumulative_distance or 0) + additional_distance
        self.save()

