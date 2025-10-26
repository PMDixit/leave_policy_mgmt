
from drf_spectacular.extensions import OpenApiAuthenticationExtension

class TenantAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'core.authentication.TenantAuthentication'  # full import path
    # IMPORTANT: must match SPECTACULAR_SETTINGS.SECURITY key
    name = 'TenantAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': 'JWT authentication using Tenant Service tokens.'
        }