"""
URL configuration for leave API endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api

# Create router for API endpoints
router = DefaultRouter()

# Register viewsets
router.register(r'category', api.LeaveCategoryViewSet, basename='leave-category')
router.register(r'application', api.LeaveApplicationViewSet, basename='leave-application')
router.register(r'approval', api.LeaveApprovalViewSet, basename='leave-approval')
router.register(r'balance', api.LeaveBalanceViewSet, basename='leave-balance')
router.register(r'workflow', api.ApprovalWorkflowViewSet, basename='approval-workflow')
router.register(r'application-comment', api.LeaveApplicationCommentViewSet, basename='leave-application-comment')
router.register(r'comment', api.LeaveCommentViewSet, basename='leave-comment')

urlpatterns = [
    # API endpoints
    path('', include(router.urls)),
]
