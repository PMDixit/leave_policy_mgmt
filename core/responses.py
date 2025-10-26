"""
Unified response structures for consistent API responses.
"""

from rest_framework.response import Response
from rest_framework import status


class APIResponse:
    """Base class for standardized API responses."""

    @staticmethod
    def success(data=None, message="Success", status_code=status.HTTP_200_OK):
        """Return a success response."""
        response_data = {
            "success": True,
            "message": message,
        }
        if data is not None:
            response_data["data"] = data
        return Response(response_data, status=status_code)

    @staticmethod
    def error(message="An error occurred", errors=None, error_code=None, status_code=status.HTTP_400_BAD_REQUEST):
        """Return an error response."""
        response_data = {
            "success": False,
            "message": message,
        }
        if errors:
            response_data["errors"] = errors
        if error_code:
            response_data["error_code"] = error_code
        return Response(response_data, status=status_code)

    @staticmethod
    def created(data=None, message="Resource created successfully"):
        """Return a created response."""
        return APIResponse.success(data, message, status.HTTP_201_CREATED)

    @staticmethod
    def no_content(message="No content"):
        """Return a no content response."""
        return APIResponse.success(None, message, status.HTTP_204_NO_CONTENT)

    @staticmethod
    def not_found(message="Resource not found"):
        """Return a not found response."""
        return APIResponse.error(message, status_code=status.HTTP_404_NOT_FOUND)

    @staticmethod
    def unauthorized(message="Unauthorized access"):
        """Return an unauthorized response."""
        return APIResponse.error(message, status_code=status.HTTP_401_UNAUTHORIZED)

    @staticmethod
    def forbidden(message="Forbidden access"):
        """Return a forbidden response."""
        return APIResponse.error(message, status_code=status.HTTP_403_FORBIDDEN)

    @staticmethod
    def bad_request(message="Bad request", errors=None):
        """Return a bad request response."""
        return APIResponse.error(message, errors, status_code=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def validation_error(message="Validation failed", errors=None):
        """Return a validation error response."""
        return APIResponse.error(message, errors, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
