#!/bin/bash
# Test script for Docker deployment

set -e

echo "=== Testing Wowza Webhook to Slack Translator ==="
echo ""

# Check if container is running
if ! docker ps | grep -q wowza-webhook-to-slack; then
    echo "❌ Container is not running!"
    echo "Start with: docker-compose up -d"
    exit 1
fi

echo "✓ Container is running"

# Test health endpoint
echo ""
echo "Testing health endpoint..."
if curl -s http://localhost:8080/health | grep -q "healthy"; then
    echo "✓ Health check passed"
else
    echo "❌ Health check failed"
    exit 1
fi

# Test webhook endpoint with sample data
echo ""
echo "Testing webhook endpoint with sample Wowza event..."
response=$(curl -s -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "name": "stream.started",
    "context": {
      "stream": "test_stream",
      "app": "live",
      "appInstance": "_definst_",
      "vhost": "_defaultVHost_",
      "state": "started"
    },
    "source": "Wowza",
    "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"
  }')

if echo "$response" | grep -q "success"; then
    echo "✓ Webhook endpoint responded successfully"
    echo ""
    echo "Response: $response"
    echo ""
    echo "⚠️  Check Slack to verify the message was received!"
else
    echo "❌ Webhook endpoint failed"
    echo "Response: $response"
    exit 1
fi

echo ""
echo "=== All tests passed! ==="
echo ""
echo "View logs: docker-compose logs -f"
