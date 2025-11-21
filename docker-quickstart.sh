#!/bin/bash
# Quick start script for Docker deployment

set -e

echo "=== Wowza Webhook to Slack Translator - Docker Quick Start ==="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file and add your Slack Webhook URL!"
    echo ""
    echo "Run: nano .env"
    echo "Then set: SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    echo ""
    read -p "Press Enter after you've configured .env..."
fi

# Check if SLACK_WEBHOOK_URL is set
source .env
if [ -z "$SLACK_WEBHOOK_URL" ] || [ "$SLACK_WEBHOOK_URL" = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL" ]; then
    echo "❌ Error: SLACK_WEBHOOK_URL not configured in .env"
    echo "Please edit .env and set your Slack webhook URL"
    exit 1
fi

echo "✓ Configuration found"
echo ""

# Create logs directory
mkdir -p logs

# Build and start
echo "Building Docker image..."
docker-compose build

echo ""
echo "Starting container..."
docker-compose up -d

echo ""
echo "✓ Container started successfully!"
echo ""
echo "Webhook endpoint: http://$(hostname -I | awk '{print $1}'):${PORT:-8080}/webhook"
echo ""
echo "View logs: docker-compose logs -f"
echo "Stop: docker-compose down"
echo ""
echo "Configure Wowza to send webhooks to the endpoint above."
