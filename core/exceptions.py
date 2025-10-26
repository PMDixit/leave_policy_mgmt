"""
Custom exception handlers for consistent error responses.
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from django.db import IntegrityError


def custom_exception_handler(exc, context):
    """
    Custom exception handler that provides consistent error responses.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Customize the response format
        custom_response_data = {
            'success': False,
            'message': 'An error occurred',
            'error_code': 'INTERNAL_ERROR'
        }

        # Handle specific exception types
        if isinstance(exc, ValidationError):
            custom_response_data.update({
                'message': 'Validation failed',
                'errors': exc.messages if hasattr(exc, 'messages') else str(exc),
                'error_code': 'VALIDATION_ERROR'
            })
        elif isinstance(exc, IntegrityError):
            custom_response_data.update({
                'message': 'Database integrity error',
                'error_code': 'INTEGRITY_ERROR'
            })
        else:
            # Use the original error message
            if hasattr(response.data, 'get'):
                error_detail = response.data.get('detail', str(exc))
            else:
                error_detail = str(exc)
            custom_response_data['message'] = error_detail

        response.data = custom_response_data

    return response


class APIException(Exception):
    """Base API exception class."""

    def __init__(self, message="An error occurred", status_code=status.HTTP_400_BAD_REQUEST, error_code=None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or 'API_ERROR'
        super().__init__(self.message)


class ValidationAPIException(APIException):
    """Exception for validation errors."""

    def __init__(self, message="Validation failed", errors=None):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY, 'VALIDATION_ERROR')
        self.errors = errors


class NotFoundAPIException(APIException):
    """Exception for not found errors."""

    def __init__(self, message="Resource not found"):
        super().__init__(message, status.HTTP_404_NOT_FOUND, 'NOT_FOUND')


class PermissionDeniedAPIException(APIException):
    """Exception for permission denied errors."""

    def __init__(self, message="Permission denied"):
        super().__init__(message, status.HTTP_403_FORBIDDEN, 'PERMISSION_DENIED')
