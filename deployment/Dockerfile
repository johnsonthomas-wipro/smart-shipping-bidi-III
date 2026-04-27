# Dockerfile for Google Cloud Run - SmartShip Voice Bidi Assistant
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and README.md for dependencies
COPY pyproject.toml .
COPY README.md .

# Install uv for faster dependency installation
RUN pip install --no-cache-dir uv

# Install dependencies using uv
RUN uv pip install --system --no-cache -e .

# Copy application files
COPY app/ .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV SHOW_CONVERSATION=no
ENV PYTHONPATH=/app

# Cloud Run expects the app to listen on $PORT
EXPOSE 8080

# Use uvicorn for FastAPI with WebSocket support
# --timeout-graceful-shutdown: Graceful shutdown timeout
# --limit-concurrency: Limit concurrent connections
CMD exec uvicorn main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --timeout-keep-alive 300 \
    --timeout-graceful-shutdown 5 \
    --ws-ping-interval 20 \
    --ws-ping-timeout 300 \
    --limit-concurrency 1000 \
    --log-level info
