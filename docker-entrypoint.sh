#!/bin/bash
set -e

# Function to log messages with timestamps
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" >&2
}

log "Starting Leave Policy Management API..."

# Execute the command with timestamped logs
exec "$@" 2>&1 | while read line; do
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $line"
done
