
# WS Slack Translator

Purpose
-------
WS Slack Translator receives webhook POSTs from Wowza Streaming Engine, converts each event into an English, human-readable message, and forwards it to Slack using an Incoming Webhook. It's intended to make Wowza events (stream starts/stops, recording state, connection issues, app lifecycle, and AI-based Video Intelligence detections) easy to monitor in Slack channels.

**Key Features:**
- 📊 Real-time streaming event notifications
- 🎯 Smart batching for Video Intelligence AI detections
- 🔔 Formatted Slack messages with blocks and fallback text
- 🐳 Docker-first deployment with health checks
- ⚙️ Simple .env file configuration

Relevant docs
-------------
- Wowza webhooks and supported events: https://www.wowza.com/docs/create-webhooks-to-monitor-streaming-events-in-wowza-streaming-engine

## Configuring Wowza Streaming Engine Webhooks

Follow these steps to have Wowza Streaming Engine publish its events to this service (and onward to Slack):

### 1. Confirm the Translator Is Reachable
Ensure the container is running and listening on port `8080`.

Health check:
```bash
curl -s http://wse.translator.slack:8080/health
```
Expected response: `{"status":"healthy"}` (HTTP 200).

**Note:** From the Docker host, use `http://localhost:8080/health`

### 2. Determine the Webhook URL

**Recommended (Docker network):** `http://wse.translator.slack:8080/webhook`
- Use this when Wowza Streaming Engine is in the same Docker Compose network
- This is the standard hostname for the translator service

**Alternative scenarios:**
- Native Wowza on same host: `http://localhost:8080/webhook`
- Different host: `http://<translator_host_ip_or_dns>:8080/webhook` (ensure firewall access)
- Behind reverse proxy: map external URL to internal `:8080`

### 3. Configure Server.xml
Edit your Wowza Streaming Engine Server.xml file to load the WebhookListener module:

1. Open `[wowza-install-dir]/conf/Server.xml` in a text editor.
2. Inside the `<ServerListeners>` element, add as the first entry:
```xml
<ServerListener>
  <BaseClass>com.wowza.wms.webhooks.WebhookListener</BaseClass>
</ServerListener>
```
3. Save the file and restart Wowza Streaming Engine.

### 4. Configure Webhooks.json
Edit the Webhooks.json file to define webhook targets and filters:

1. Open `[wowza-install-dir]/conf/Webhooks.json` in a text editor.
2. Configure your webhook target. Example configuration:
```json
{
  "webhooks": {
    "source": "myWSEInstanceName",
    "filters": [
      {
        "id": "slackTranslatorFilter",
        "enabled": true,
        "criteria": "vHost._defaultVHost_.>",
        "targetRef": "slackTranslator"
      }
    ],
    "targets": [
      {
        "id": "slackTranslator",
        "url": "http://wse.translator.slack:8080/webhook",
        "headers": []
      }
    ]
  }
}
```

**Key configuration notes:**
- `criteria`: Filter pattern for events. Use `vHost._defaultVHost_.>` to capture all events from the default virtual host, or customize for specific apps/streams (e.g., `vHost.*.app.live.appInstance.*.stream.*.state.*`).
- `url`: Your translator webhook endpoint (adjust based on step 2).
- `headers`: Optional HTTP headers if authentication is needed.
- For JWT authentication or advanced filtering, see the [Webhooks.json configuration reference](https://www.wowza.com/docs/wowza-streaming-engine-webhooksjson-configuration-reference).

3. Save the file and restart Wowza Streaming Engine.

### 5. Test With a Manual POST
You can simulate Wowza by sending a test payload to verify the translator is working:
```bash
curl -X POST http://wse.translator.slack:8080/webhook \
	-H 'Content-Type: application/json' \
	-d '{
		"name": "stream.started",
		"timestamp": 1732212345678,
		"context": {
			"app": "live",
			"stream": "demoStream",
			"state": "started",
			"vhost": "_defaultVHost_",
			"appInstance": "_definst_"
		},
		"source": "TestWSE",
		"version": "1.0"
	}'
```
Check your Slack channel for a formatted message. If nothing appears, inspect container logs with `docker-compose logs -f` and confirm `SLACK_WEBHOOK_URL` is set.

### 6. Common Integration Notes
- **Docker deployment (recommended):** Use `http://wse.translator.slack:8080/webhook` when Wowza and the translator share a Docker network.
- **Native Wowza:** If Wowza runs as a native service on the same host, use `http://localhost:8080/webhook`.
- For high-volume environments, consider rate limiting or batching on the Slack side (this translator sends per-event).
- The translator attempts structured "blocks" Slack formatting first; if Slack rejects, it falls back to plain text.
- Unknown or additional fields from Wowza are logged and ignored—they will not break processing.
- After any changes to Server.xml or Webhooks.json, you must restart Wowza Streaming Engine for changes to take effect.

### 7. Supported Webhook Events
This translator handles the following Wowza webhook events:
- **Application events:** `app.started`, `app.shutdown`
- **Stream events:** `stream.started`, `stream.stopped`
- **Recording events:** `recording.started`, `recording.stopped`, `recording.failed`, `recording.segment.started`, `recording.segment.ended`
- **Re-streaming events:** `connection.started`, `connection.success`, `connection.failure`
- **Video Intelligence events:** `video.intelligence.detection` (AI-based object detection with smart batching)
- **Custom events:** Unknown events are logged and sent to Slack with raw JSON payload

For detailed event structures and additional configuration options, see the [Wowza webhook documentation](https://www.wowza.com/docs/create-webhooks-to-monitor-streaming-events-in-wowza-streaming-engine).

### 8. Webhook Payload Structure
Wowza Streaming Engine sends webhook events with the following structure:
```json
{
  "id": "unique-event-id",
  "timestamp": 1758657755812,
  "name": "stream.started",
  "source": "myWSEInstanceName",
  "version": "1.0",
  "context": {
    "app": "live",
    "appInstance": "_definst_",
    "stream": "myStream",
    "state": "started",
    "vhost": "_defaultVHost_"
  },
  "data": {}
}
```

**Key fields:**
- `name`: Event type (e.g., `stream.started`, `recording.failed`)
- `context`: Contains app, stream, vhost, and state information
- `data`: Additional event-specific data (e.g., output file for recordings, error messages)
- `timestamp`: Unix timestamp in milliseconds
- `source`: Your Wowza Streaming Engine instance name

The translator automatically parses these fields and formats them into human-readable Slack messages. Unknown fields are logged and safely ignored.

If you need to support an event that is not currently rendered cleanly in Slack, capture a sample payload from logs and open an issue or extend `translate_payload` in `http_server.py`.

## Video Intelligence (AI Detection) Support

The translator includes intelligent batching for Video Intelligence (AI object detection) events to prevent Slack notification spam.

### How It Works
- **Smart Batching:** AI detection events are aggregated over a configurable time window (default: 10 seconds) per stream
- **Automatic Summarization:** Batched detections are combined into a single summary message showing:
  - Total detection count
  - Object class breakdown (e.g., "15× person", "8× car")
  - Average confidence scores per class
  - Detection period duration
- **Spam Prevention:** Instead of sending hundreds of individual messages for continuous AI detections, you receive periodic summaries

### Configuration
Set the batching window via environment variable:
```bash
VI_BATCH_WINDOW=10  # seconds (default: 10)
```

In `.env` file:
```env
VI_BATCH_WINDOW=15  # Adjust based on your monitoring needs
```

### Example Slack Message
```
🔍 AI Detection Summary
Stream: myStream
App: live
Duration: 9.8s
Total Detections: 147
Classes: 89× person (avg 94%), 45× car (avg 88%), 13× bicycle (avg 82%)
Period: 14:23:10 - 14:23:20
```

### Notes
- Each stream's detections are batched independently
- The batch timer resets with each new detection
- Batches are flushed automatically after the configured window expires
- Useful for high-frequency AI analysis scenarios (e.g., crowd monitoring, traffic analysis)

## Deployment

This application is designed for Docker deployment. See **[DOCKER_README.md](DOCKER_README.md)** for complete instructions.

### Quick Start

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your Slack webhook URL
nano .env  # or notepad .env on Windows

# Start with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f
```

Or use the quick start scripts:
- **Linux/Mac:** `./docker-quickstart.sh`
- **Windows:** `.\docker-quickstart.ps1`

### Configuration
- **`SLACK_WEBHOOK_URL`** (required): Your Slack Incoming Webhook URL
- **`LOG_LEVEL`** (optional): Logging verbosity - `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`)
- **`PORT`** (optional): External port to expose (default: `8080`)
- **`VI_BATCH_WINDOW`** (optional): Video Intelligence detection batching window in seconds (default: `10`)
  - Increase for less frequent AI detection summaries
  - Decrease for more real-time updates (may increase Slack message volume)

## Troubleshooting

- **Webhooks return 404:** Ensure the container is running (`docker-compose ps`) and listening on port 8080. Check container logs with `docker-compose logs -f`.
- **Slack messages not appearing:** Verify `SLACK_WEBHOOK_URL` is correctly set in `.env`. Check container logs for errors.
- **Container won't start:** Ensure port 8080 is not already in use. Check Docker logs: `docker-compose logs`.
- **Health check failing:** Verify the container is running and accessible: `curl http://localhost:8080/health`


License
-------
- MIT. See `LICENSE`.

