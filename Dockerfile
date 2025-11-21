# Use official Python runtime as base image
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Install wget for health checks
RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY http_server.py .

# Create directory for logs
RUN mkdir -p /app/logs

# Expose port 8080
EXPOSE 8080

# Set environment variables with defaults
ENV SLACK_WEBHOOK_URL=""
ENV LOG_LEVEL="INFO"
ENV LOG_DIR="/app/logs"

# Run the application with unbuffered output for proper logging
CMD ["python", "-u", "http_server.py"]
