
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

The translator includes intelligent batching and object tracking for Video Intelligence (AI object detection) events to prevent Slack notification spam and provide actionable insights.

### How It Works
- **Smart Batching:** AI detection events are aggregated over a configurable time window (default: 10 seconds) per stream
- **Object Tracking:** Advanced multi-frame tracking using Intersection over Union (IoU) algorithms to count unique people across frames
- **Automatic Summarization:** Batched detections are combined into a single summary message showing:
  - **Unique object count** - tracks individual people across frames (not just raw detections)
  - **Peak occupancy** - maximum number of people in a single frame
  - **Detection statistics** - per-class breakdown with confidence ranges
  - **Detection rate** - detections per second
  - **Time period** - start and end timestamps
- **Memory Protection:** Automatic early flush when batch size exceeds limits to prevent memory issues
- **Spam Prevention:** Instead of sending hundreds of individual messages for continuous AI detections, you receive periodic summaries

### Configuration
Configure via environment variables in your `.env` file:

```env
# Batching time window in seconds (default: 10)
VI_BATCH_WINDOW=10

# Maximum detections per batch before early flush (default: 10000)
VI_MAX_BATCH_SIZE=10000

# Optional: Fine-tune tracking algorithm
VI_TRACK_EXPIRY=30      # Frames before track expires (default: 30)
VI_IOU_THRESHOLD=0.3    # IoU threshold for matching (default: 0.3)
```

**Recommendations:**
- **High-traffic streams:** Decrease `VI_BATCH_WINDOW` to 5-10s for more frequent updates
- **Low-traffic streams:** Increase to 15-30s to reduce message frequency
- **Memory-constrained environments:** Lower `VI_MAX_BATCH_SIZE` to 5000 or less

### Example Slack Message
```
👁️ AI Detection Summary

Stream: lobby-camera | App: live
Duration: 9.8s (14:23:10 - 14:23:20)
━━━━━━━━━━━━━━━━━━━━━━

Unique People: ~12 tracked
Peak Occupancy: 8 people (max in single frame)
Frames Analyzed: 147 frames

Detection Stats:
 • Person: 147 detections, 94% avg (88% - 98%)
 • Detection rate: 15.0/sec
```

### How Object Tracking Works
The translator uses sophisticated computer vision algorithms to identify unique individuals:

1. **Bounding Box Analysis:** Each detection includes position and size information
2. **IoU Matching:** Tracks objects across frames by comparing bounding box overlap
3. **Temporal Tracking:** Maintains object identity even with brief occlusions
4. **Class Filtering:** Only matches detections of the same class (person-to-person)

This means you get accurate people counts, not just detection counts. If the same person appears in 50 consecutive frames, it's counted as 1 unique person, not 50 detections.

### Use Cases
- **Crowd Monitoring:** Track unique visitor counts and peak occupancy
- **Traffic Analysis:** Monitor vehicle flow and congestion
- **Security:** Alert on unusual occupancy patterns
- **Retail Analytics:** Understand customer flow and dwell times
- **Queue Management:** Monitor line lengths and wait times

### Notes
- Each stream's detections are batched and tracked independently
- Batches flush automatically after the configured window expires
- Early flush triggers if `VI_MAX_BATCH_SIZE` is exceeded (memory protection)
- Tracking state resets between batches
- Works with any Wowza Video Intelligence detection events

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

**Required:**
- **`SLACK_WEBHOOK_URL`**: Your Slack Incoming Webhook URL

**Optional:**
- **`LOG_LEVEL`**: Logging verbosity - `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`)
- **`PORT`**: External port to expose (default: `8080`)

**Video Intelligence Settings:**
- **`VI_BATCH_WINDOW`**: Detection batching window in seconds (default: `10`)
  - Increase for less frequent AI detection summaries
  - Decrease for more real-time updates (may increase Slack message volume)
- **`VI_MAX_BATCH_SIZE`**: Maximum detections per batch before early flush (default: `10000`)
  - Prevents memory issues on high-volume streams
  - Triggers automatic flush when exceeded
- **`VI_TRACK_EXPIRY`**: Frames before object track expires (default: `30`)
  - Lower for fast-moving objects, higher for slow scenes
- **`VI_IOU_THRESHOLD`**: IoU threshold for object matching, 0.0-1.0 (default: `0.3`)
  - Higher values = stricter matching (may split tracks)
  - Lower values = looser matching (may merge tracks)

## Troubleshooting

- **Webhooks return 404:** Ensure the container is running (`docker-compose ps`) and listening on port 8080. Check container logs with `docker-compose logs -f`.
- **Slack messages not appearing:** Verify `SLACK_WEBHOOK_URL` is correctly set in `.env`. Check container logs for errors.
- **Container won't start:** Ensure port 8080 is not already in use. Check Docker logs: `docker-compose logs`.
- **Health check failing:** Verify the container is running and accessible: `curl http://localhost:8080/health`


License
-------
- MIT. See `LICENSE`.

