"""
URL configuration for policy API endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api

# Create router for API endpoints
router = DefaultRouter()

# Register viewsets
router.register(r'policy', api.PolicyViewSet, basename=None)

urlpatterns = [
    # API endpoints
    path('', include(router.urls)),
]
