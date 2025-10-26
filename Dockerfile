# Use Python 3.13 slim image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DJANGO_SETTINGS_MODULE=config.settings.development

# Install runtime system dependencies and uv
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Create app directory and non-root user
WORKDIR /app
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app

# Copy dependency files and install dependencies
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

# Copy application code
COPY --chown=app:app . .

# Create logs and static directories
RUN mkdir -p /app/logs /app/staticfiles /app/media && chown -R app:app /app/logs /app/staticfiles /app/media

# Switch to non-root user
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Use entrypoint script for proper log handling
ENTRYPOINT ["/app/docker-entrypoint.sh"]
