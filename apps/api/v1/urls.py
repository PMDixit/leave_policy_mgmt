"""
Main API URL configuration for version 1.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

# Create a router for API endpoints
router = DefaultRouter()

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),

    # Include app-specific API URLs
    path('policy/', include('apps.api.v1.policy.urls')),
    path('leave/', include('apps.api.v1.leave.urls')),

    # API Documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
