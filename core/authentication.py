"""
Authentication utilities for JWT token validation with external tenant service.

Refactored to follow a structured interface similar to typical DRF auth backends:
- www_authenticate_realm
- __init__
- authenticate(request)
- authenticate_credentials(token)
- authenticate_header(request)
"""

import logging
import requests
from django.conf import settings
from django.core.cache import cache
from rest_framework import authentication, exceptions
from typing import Optional, Tuple
from types import SimpleNamespace

logger = logging.getLogger(__name__)


class TenantAuthentication(authentication.BaseAuthentication):
    """Authenticate requests using a JWT validated against the tenant service.

    Flow:
    - Read Authorization header in the format: "Bearer <token>"
    - Validate token by calling the tenant service "user me" endpoint
    - Build a lightweight user object from the response
    - Return (user, token) tuple for DRF
    """

    www_authenticate_realm = 'api'

    def __init__(self) -> None:
        # No initialization requirements for now; keep for parity/consistency
        super().__init__()

    def authenticate(self, request) -> Optional[Tuple[object, str]]:
        """Entry point used by DRF.

        Returns None to indicate no attempt when the header is missing or malformed
        (so other authenticators can run). Otherwise delegates to
        authenticate_credentials.
        """
        auth_header = request.META.get('HTTP_AUTHORIZATION', '') or ''
        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1].strip()
        if not token:
            raise exceptions.AuthenticationFailed('Invalid Authorization header')

        return self.authenticate_credentials(token)

    def authenticate_credentials(self, token: str) -> Tuple[object, str]:
        """Validate the token and return (user, token) or raise AuthenticationFailed."""
        try:
            user_data = self._validate_token_with_tenant_api(token)
            if not user_data:
                raise exceptions.AuthenticationFailed('Invalid token')

            user = self._create_user_object(user_data)
            return (user, token)

        except requests.RequestException as exc:
            logger.error(f"Error calling tenant API: {str(exc)}")
            raise exceptions.AuthenticationFailed('Authentication service unavailable')
        except exceptions.AuthenticationFailed:
            raise
        except Exception as exc:  # pragma: no cover - unexpected
            logger.error(f"Authentication error: {str(exc)}")
            raise exceptions.AuthenticationFailed('Authentication failed')

    def authenticate_header(self, request) -> str:  # pragma: no cover - header formatting
        return 'Bearer realm="%s"' % self.www_authenticate_realm

    def _validate_token_with_tenant_api(self, token):
        """
        Validate JWT token with tenant user API.

        Args:
            token: JWT token from request

        Returns:
            dict: User data if valid, None otherwise
        """
        # Cache key for this token
        cache_key = f"tenant_auth_{token[:20]}"
        cached_result = cache.get(cache_key)

        if cached_result:
            return cached_result

        try:
            # Call tenant user API
            tenant_api_url = f"{settings.TENANT_SERVICE_URL}/api/v1/tenant/user/me/"
            headers = {'Authorization': f'Bearer {token}'}

            response = requests.get(tenant_api_url, headers=headers, timeout=10)

            if response.status_code == 200:
                api_response = response.json()

                # Extract user data from the response
                user_data = api_response.get('data', {})

                if user_data:
                    # Cache for 30 minutes (1800 seconds)
                    cache.set(cache_key, user_data, timeout=1800)
                    return user_data

                logger.warning("No user data found in tenant API response")
                return None
            else:
                logger.warning(f"Tenant API returned status {response.status_code}")
                return None

        except requests.RequestException as e:
            logger.error(f"Tenant API request failed: {str(e)}")
            return None

    def _create_user_object(self, user_data):
        """
        Create a user-like object from the API response data.

        Args:
            user_data: Dict containing user information from tenant API

        Returns:
            SimpleNamespace: User object with required attributes
        """
        user = SimpleNamespace()
        user.id = user_data.get('uuid')
        user.tenant_id = user_data.get('tenant_id')
        user.email = user_data.get('email')
        user.first_name = user_data.get('first_name', '')
        user.last_name = user_data.get('last_name', '')
        user.full_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()

        # Extract role information - check direct flags first, then product_roles
        user.is_hr = user_data.get('is_hr', False)
        user.is_admin = user_data.get('is_tenant', False)  # tenant users are typically admins
        user.role = 'Employee'

        # Determine primary role
        if user.is_admin:
            user.role = 'Admin'
        elif user.is_hr:
            user.role = 'HR'
        else:
            # Fallback to product_roles if direct flags don't indicate admin/HR
            product_roles = user_data.get('product_roles', [])
            for product in product_roles:
                if 'roles' in product:
                    for role in product['roles']:
                        role_name = role.get('role_name', '').lower()
                        if role_name == 'admin':
                            user.is_admin = True
                            user.role = 'Admin'
                            break
                        elif 'hr' in role_name:
                            user.is_hr = True
                            user.role = 'HR'
                            break

        user.department = user_data.get('department', '')
        user.position = user_data.get('position', '')
        user.is_authenticated = True

        return user