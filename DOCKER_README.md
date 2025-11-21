# Wowza Webhook to Slack Translator - Docker Setup

This Docker image translates Wowza Streaming Engine webhook events into formatted Slack messages.

## Quick Start

### Using Docker Compose (Recommended)

1. **Clone or download this repository**

2. **Create environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` file with your Slack webhook URL:**
   ```env
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   LOG_LEVEL=INFO
   PORT=8080
   ```

4. **Start the container:**
   ```bash
   docker-compose up -d
   ```

5. **Check the logs:**
   ```bash
   docker-compose logs -f
   ```

6. **Configure Wowza to send webhooks to:**
   ```
   http://YOUR_SERVER_IP:8080/webhook
   ```

### Using Docker CLI

1. **Build the image:**
   ```bash
   docker build -t wowza-webhook-to-slack .
   ```

2. **Run the container:**
   ```bash
   docker run -d \
     --name wowza-webhook-to-slack \
     -p 8080:8080 \
     -e SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL" \
     -v $(pwd)/logs:/app/logs \
     --restart unless-stopped \
     wowza-webhook-to-slack
   ```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SLACK_WEBHOOK_URL` | Yes | - | Your Slack Incoming Webhook URL |
| `LOG_LEVEL` | No | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `PORT` | No | 8080 | External port to expose (container always runs on 8080 internally) |

### Alternative: Using config.json

Instead of environment variables, you can mount a `config.json` file:

1. **Create `config.json`:**
   ```json
   {
     "slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
   }
   ```

2. **Mount it in docker-compose.yml** (already configured):
   ```yaml
   volumes:
     - ./config.json:/app/config.json:ro
   ```

**Note:** Environment variables take precedence over `config.json`.

## Getting Your Slack Webhook URL

1. Go to [Slack API](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name your app and select your workspace
4. In the left sidebar, click "Incoming Webhooks"
5. Toggle "Activate Incoming Webhooks" to On
6. Click "Add New Webhook to Workspace"
7. Select the channel to post to
8. Copy the webhook URL

## Configuring Wowza Streaming Engine

1. **Edit Wowza Webhooks configuration:**
   - File location: `[wowza-install]/conf/Webhooks.json`

2. **Add webhook endpoint:**
   ```json
   {
     "webhooks": [
       {
         "url": "http://YOUR_DOCKER_HOST_IP:8080/webhook",
         "events": [
           "stream.started",
           "stream.stopped",
           "recording.started",
           "recording.stopped",
           "recording.failed",
           "app.started",
           "app.shutdown",
           "connection.failure"
         ],
         "headers": {
           "Content-Type": "application/json"
         }
       }
     ]
   }
   ```

3. **Restart Wowza Streaming Engine**

## Supported Wowza Events

The translator supports all Wowza webhook events with enhanced formatting for:

- **Application Events:** `app.started`, `app.shutdown`
- **Live Stream Events:** `stream.started`, `stream.stopped`
- **Recording Events:** `recording.started`, `recording.stopped`, `recording.failed`, `recording.segment.started`, `recording.segment.ended`
- **Connection Events:** `connection.started`, `connection.success`, `connection.failure`

## Health Check

The container includes a health check endpoint:

```bash
curl http://localhost:8080/health
# or from inside the container:
wget --spider http://localhost:8080/health
```

Response:
```json
{"status": "healthy", "service": "wowza-webhook-to-slack"}
```

## Logs

Logs are stored in the `logs` directory (mounted volume) and also sent to stdout:

```bash
# View logs with docker-compose
docker-compose logs -f

# View logs with docker
docker logs -f wowza-webhook-to-slack

# View log file
cat logs/server.log
```

## Testing

Test the webhook endpoint manually:

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "name": "stream.started",
    "context": {
      "stream": "test_stream",
      "app": "live",
      "vhost": "_defaultVHost_",
      "state": "started"
    },
    "source": "Wowza",
    "timestamp": "2025-11-21T12:00:00Z"
  }'
```

**Automated Testing:**

Use the provided test scripts to verify the deployment:

```bash
# Linux/Mac
./test-docker.sh

# Windows
.\test-docker.ps1
```

These scripts will:
1. Check if the container is running
2. Test the health endpoint
3. Send a sample webhook event
4. Verify the response

## Troubleshooting

### Container won't start
- Check logs: `docker-compose logs`
- Verify `SLACK_WEBHOOK_URL` is set correctly in `.env`
- Ensure port 8080 is not already in use: `netstat -an | grep 8080` (Linux) or `netstat -an | findstr 8080` (Windows)
- Check Docker daemon is running: `docker ps`

### Webhooks not being received
- Verify Wowza can reach the Docker host IP: `ping <docker-host-ip>` from Wowza server
- Check firewall rules on the Docker host allow port 8080
- Test connectivity from Wowza server: `curl http://<docker-host-ip>:8080/health`
- Verify Docker port mapping: `docker ps` should show `0.0.0.0:8080->8080/tcp`
- Check if container is healthy: `docker inspect wowza-webhook-to-slack | grep Health`

### Slack messages not sending
- Verify the webhook URL is correct and not expired
- Check container logs for specific errors: `docker-compose logs | grep -i error`
- Test the webhook URL manually with curl
- Ensure the Slack app has permissions to post to the channel
- Verify no network restrictions blocking outbound HTTPS to Slack

### Log files not persisting
- Ensure `./logs` directory exists and has proper permissions
- Check volume mount: `docker inspect wowza-webhook-to-slack | grep Mounts`
- Verify LOG_LEVEL is set correctly in `.env`

### Performance issues
- Check container resource usage: `docker stats wowza-webhook-to-slack`
- Review logs for slow response times
- Consider using the production compose file with resource limits: `docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d`

## Updating

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

## Production Considerations

### Using Production Configuration

For production deployment with resource limits and optimized settings:

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production configuration includes:
- Resource limits (CPU: 0.5 cores, Memory: 256MB)
- WARNING log level (reduces log verbosity)
- Always restart policy
- Service labels for monitoring

### Best Practices

1. **Use a reverse proxy** (nginx, Traefik, Caddy) for HTTPS:
   ```nginx
   server {
       listen 443 ssl;
       server_name wowza-webhooks.example.com;
       
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
       
       location / {
           proxy_pass http://localhost:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

2. **Set up monitoring** using the `/health` endpoint:
   - Use tools like Prometheus, Datadog, or simple cron scripts
   - Alert on health check failures
   - Monitor log file size growth

3. **Configure log rotation** for the log files:
   ```bash
   # Add to /etc/logrotate.d/wowza-webhook
   /path/to/WS_Slack_Translator/logs/server.log {
       daily
       rotate 7
       compress
       delaycompress
       notifempty
       missingok
       postrotate
           docker-compose -f /path/to/docker-compose.yml restart
       endscript
   }
   ```

4. **Use secrets management** for the Slack webhook URL:
   - Use Docker secrets or environment variable management tools
   - Never commit `.env` to version control
   - Rotate webhook URLs periodically

5. **Backup considerations**:
   - Logs directory should be backed up regularly
   - Configuration files (`.env`) should be stored securely
   - Document your Slack webhook URL recovery process

6. **Update strategy**:
   ```bash
   # Pull latest changes
   git pull
   
   # Rebuild with no cache to ensure fresh build
   docker-compose build --no-cache
   
   # Restart with zero downtime (if using multiple instances)
   docker-compose up -d --force-recreate
   ```

### Security Recommendations

1. **Network Security**:
   - Use firewall rules to restrict access to port 8080
   - Only allow Wowza server IP addresses
   - Consider using a VPN or private network

2. **Container Security**:
   - Run as non-root user (add to Dockerfile if needed)
   - Keep base image updated: `docker pull python:3.11-slim`
   - Scan for vulnerabilities: `docker scan wowza-webhook-to-slack`

3. **Secrets Management**:
   - Use Docker secrets or external secret stores
   - Rotate Slack webhook URL periodically
   - Monitor for unauthorized access attempts

## License

See LICENSE file for details.

## Support

For issues, questions, or contributions, please visit the project repository.
