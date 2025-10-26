"""
Custom pagination classes for consistent pagination across the API.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination class with consistent response structure."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        """Return paginated response with metadata."""
        return Response({
            'success': True,
            'message': 'Data retrieved successfully',
            'data': {
                'count': self.page.paginator.count,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'results': data,
                'page_size': self.page_size,
                'current_page': self.page.number,
                'total_pages': self.page.paginator.num_pages,
            }
        })


class LargeResultsSetPagination(StandardResultsSetPagination):
    """Pagination for large datasets."""

    page_size = 50
    max_page_size = 500


class SmallResultsSetPagination(StandardResultsSetPagination):
    """Pagination for small datasets."""

    page_size = 10
    max_page_size = 50
