"""
Structured logging utilities for the application.
"""

import logging
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = record.request_id
        if hasattr(record, 'endpoint'):
            log_entry['endpoint'] = record.endpoint

        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def get_logger(name):
    """Get a configured logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = JSONFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_api_request(logger, request, response, duration):
    """Log API request details."""
    logger.info(
        'API Request',
        extra={
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'duration': duration,
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'remote_addr': request.META.get('REMOTE_ADDR', ''),
        }
    )


def log_model_change(logger, model_name, instance_id, action, user=None):
    """Log model instance changes."""
    logger.info(
        'Model Change',
        extra={
            'model': model_name,
            'instance_id': instance_id,
            'action': action,
            'user_id': user.id if user else None,
        }
    )
