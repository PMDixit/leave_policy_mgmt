"""
Custom middleware for the application.
"""

import time
import logging
from django.conf import settings
from django.http import JsonResponse
from django_multitenant.utils import set_current_tenant


logger = logging.getLogger(__name__)


class TenantMiddleware:
    """
    Middleware to handle multi-tenancy by extracting tenant information
    from authenticated requests and setting tenant context.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        Extract tenant information from authenticated request and set tenant context.
        """
        # Check if user is authenticated (set by DRF authentication)
        if not hasattr(request, 'user') or not request.user:
            return JsonResponse(
                {'error': 'Authentication required'},
                status=401
            )

        try:
            # Set tenant context from authenticated user
            if '/api/v1/' in request.path:
                set_current_tenant(request.user.id)
                
        except Exception as e:
            logger.error(f"Error processing tenant context: {str(e)}")
            return JsonResponse(
                {'error': 'Tenant context setup failed'},
                status=500
            )

        # Continue processing the request
        response = self.get_response(request)
        return response


class RequestLoggingMiddleware:
    """
    Middleware to log API requests with timing information.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()

        # Log request
        logger.info(
            f"Request: {request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        response = self.get_response(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log response
        logger.info(
            f"Response: {response.status_code} for {request.method} {request.path} "
            f"in {duration:.2f}s"
        )

        return response

