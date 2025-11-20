from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('moti/api/user_auth/', include('user_service.urls')),
]

