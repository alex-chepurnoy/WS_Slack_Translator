
# WS Slack Translator

Purpose
-------
WS Slack Translator receives webhook POSTs from Wowza Streaming Engine, converts each event into an English, human-readable message, and forwards it to Slack using an Incoming Webhook. It's intended to make Wowza events (stream starts/stops, recording state, connection issues, app lifecycle) easy to monitor in Slack channels.

Relevant docs
-------------
- Wowza webhooks and supported events: https://www.wowza.com/docs/create-webhooks-to-monitor-streaming-events-in-wowza-streaming-engine

## Configuring Wowza Streaming Engine Webhooks

Follow these steps to have Wowza Streaming Engine publish its events to this service (and onward to Slack):

### 1. Confirm the Translator Is Reachable
Ensure the container or process is running and listening on port `8080`.

Health check:
```bash
curl -s http://localhost:8080/health
```
Expected response: `{"status":"ok"}` (HTTP 200).

### 2. Determine the Webhook URL
- Same host (native Wowza, translator in Docker): use `http://localhost:8080/webhook`.
- Same host (both in Docker Compose user-defined network): use `http://wowza-webhook-to-slack:8080/webhook` from the Wowza container if you add both services to the same network.
- Different host: use `http://<translator_host_ip_or_dns>:8080/webhook` and ensure firewall access.
- Behind reverse proxy: map external URL to internal `:8080` and use that external URL.

### 3. Add Webhook via Wowza Manager (GUI)
1. Log in to Wowza Streaming Engine Manager.
2. Navigate: Server > Webhooks (or Events/Webhooks section depending on version).
3. Click "Add Webhook".
4. Set Name: `SlackTranslator` (any descriptive name).
5. URL: `http://localhost:8080/webhook` (adjust based on step 2).
6. Method: `POST`.
7. Select events you want (e.g. stream start/stop, recording start/stop, transcoder start/stop). The translator will ignore fields it does not understand and log them.
8. Enable the webhook and Save.

### 4. Add Webhook via REST API (Alternative)
Wowza's REST API usually listens on port `8088`. Replace credentials and events to match your setup.
```bash
curl -u admin:yourPassword \
	-H 'Content-Type: application/json' \
	-X POST \
	http://localhost:8088/api/v1/webhooks \
	-d '{
		"name": "SlackTranslator",
		"url": "http://localhost:8080/webhook",
		"enabled": true,
		"events": ["streamStart","streamStop","recordingStart","recordingStop","transcoderStart","transcoderStop","publish","unpublish"]
	}'
```
Event identifiers vary by Wowza version; consult the official docs for the definitive list.

### 5. Test With a Manual POST
You can simulate Wowza by sending a minimal payload:
```bash
curl -X POST http://localhost:8080/webhook \
	-H 'Content-Type: application/json' \
	-d '{
		"event": "streamStart",
		"appName": "live",
		"streamName": "demoStream",
		"timestamp": 1732212345678
	}'
```
Check your Slack channel for a formatted message. If nothing appears, inspect container logs and confirm `SLACK_WEBHOOK_URL` is set.

### 6. Common Integration Notes
- If Wowza runs as a Windows service and translator runs in Docker on the same Windows host, `localhost` works.
- If Wowza is inside Docker, ensure both containers share a user-defined bridge network and reference the translator service name.
- For high-volume environments, consider rate limiting or batching on the Slack side (this translator sends per-event).
- The translator attempts structured "blocks" Slack formatting first; if Slack rejects, it falls back to plain text.
- Unknown or additional fields from Wowza are logged and ignored—they will not break processing.

### 7. Updating / Removing the Webhook
Use Wowza Manager (edit or disable) or issue a REST `PUT`/`DELETE` to the webhook endpoint (see Wowza docs) if you need to change URLs (e.g., move to `achepw0wz` published image).

### 8. Basic Payload Shape (Example)
```json
{
	"event": "streamStart",
	"appName": "live",
	"streamName": "demoStream",
	"timestamp": 1732212345678
}
```
Additional Wowza-specific fields (e.g. `instanceName`, `ipAddress`, `sessionId`) will be logged and may be included in Slack formatting as support expands.

If you need to support an event that is not currently rendered cleanly in Slack, capture a sample payload from logs and open an issue or extend `translate_payload` in `http_server.py`.

## Deployment Options

Choose one of the following deployment methods:

### Option 1: Docker (Recommended for Production)

The easiest way to deploy this application is using Docker. See **[DOCKER_README.md](DOCKER_README.md)** for complete instructions.

**Quick Start:**
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
- Linux/Mac: `./docker-quickstart.sh`
- Windows: `.\docker-quickstart.ps1`

### Option 2: Windows Native Install

Recommended: use the provided installer script which automates Python, dependencies, and service registration.

1. Download the project from GitHub (clone or Download ZIP) and extract.
2. Open PowerShell as Administrator in the extracted folder.
3. Run the installer (example):

```powershell
.\install_windows.ps1 -InstallDir "C:\Program Files\WS_Slack_Translator" -WebhookUrl "https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

What the installer does (summary)
- Ensures Python is installed (optionally downloading official installer)
- Installs Python packages from `requirements.txt`
- Downloads NSSM and registers an NSSM service to run the translator under the chosen install directory
- Optionally writes `config.json` with the provided webhook URL

Notes for Windows
- The installer requires Administrator rights.
- The service created by the installer runs the translator with its working directory set to the install folder so `config.json` is found.

Manual Windows (only for development/testing)
- If you don't want to use the installer, install Python, create `config.json` or set `SLACK_WEBHOOK_URL`, and run `python http_server.py` from the project folder. This is intended for testing, not production.

### Option 3: Linux Native Install
This section describes a straightforward manual setup using a virtualenv and a systemd service. You can adapt these steps to your distro and preferred user account.

1. Clone the repo on the target machine and create a virtualenv:

```bash
git clone <repo-url> /opt/ws-slack-translator
cd /opt/ws-slack-translator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Create `config.json` in the project folder with your Slack webhook URL, for example:

```json
{
	"slack_webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ"
}
```

3. Create a `systemd` service unit (example `/etc/systemd/system/ws-slack-translator.service`):

```ini
[Unit]
Description=WS Slack Translator
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/ws-slack-translator
ExecStart=/opt/ws-slack-translator/venv/bin/python /opt/ws-slack-translator/http_server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

4. Enable & start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ws-slack-translator
sudo systemctl start ws-slack-translator
sudo journalctl -u ws-slack-translator -f
```

Configuration
-------------
- `config.json` currently only stores the Slack Incoming Webhook URL (key: `slack_webhook_url`).
- Alternatively set `SLACK_WEBHOOK_URL` in the environment for the service.


Troubleshooting
---------------
- If webhooks return 404: ensure the running process is the translator (and not another file) and that it is listening on port 8080. Restart the service to pick up code changes.
- If Slack messages fail: check `logs/` (service stdout/stderr) and confirm `config.json` or `SLACK_WEBHOOK_URL` is set.


License
-------
- MIT. See `LICENSE`.

