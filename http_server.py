from flask import Flask, request, jsonify
import requests
import logging
import os
import json
from pathlib import Path
from datetime import datetime, timezone

# Configure logging to log to both a file and the console
LOG_DIR = Path(os.environ.get('LOG_DIR', 'logs'))
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"

# Get log level from environment variable
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, LOG_LEVEL, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='a'),  # Log to a file in append mode
        logging.StreamHandler()                  # Log to the console
    ]
)

# Application folder (where config.json will live)
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / 'config.json'


def load_config():
    """Load configuration from config.json or environment variables.

    Priority: config.json > SLACK_WEBHOOK_URL env var
    Returns a dict (may be empty).
    """
    cfg = {}
    # Try config file
    try:
        if CONFIG_PATH.exists():
            # Use utf-8-sig to gracefully handle files written with a UTF-8 BOM (PowerShell Out-File may add one)
            with CONFIG_PATH.open('r', encoding='utf-8-sig') as f:
                cfg = json.load(f)
            logging.info("Loaded config.json from %s", CONFIG_PATH)
    except json.JSONDecodeError as e:
        logging.error("Failed to parse config.json (%s): %s", CONFIG_PATH, e)
    except Exception:
        logging.exception("Failed to load config.json")

    # Fallback to environment variable
    if 'slack_webhook_url' not in cfg or not cfg.get('slack_webhook_url'):
        env_url = os.environ.get('SLACK_WEBHOOK_URL')
        if env_url:
            cfg['slack_webhook_url'] = env_url

    return cfg


# Load configuration at import time
CONFIG = load_config()

# Initialize Flask app
app = Flask(__name__)

# Test log message to confirm logging works
logging.info("HTTP server is starting. Logging is configured correctly.")


def translate_payload(payload):
    """
    Translate Wowza JSON payload into both a fallback text message and a Slack Blocks list.

    This function implements per-event templates for supported Wowza webhook
    events (application, live stream, recording, re-streaming/connection).

    Returns: (text, blocks, severity)
      - text: simple human-readable string (fallback)
      - blocks: list suitable for Slack 'blocks' field
      - severity: 'low' | 'medium' | 'high'
    """
    try:
        context = payload.get("context", {}) or {}
        data = payload.get("data") or {}
        event_name = (payload.get("name") or payload.get("eventType") or "unknown").lower()
        stream = context.get("stream") or context.get("name") or data.get("stream") or "N/A"
        vhost = context.get("vhost") or "N/A"
        app = context.get("app") or "N/A"
        state = (context.get("state") or payload.get("state") or payload.get("status") or "N/A")
        source = payload.get("source", "Wowza")
        raw_ts = payload.get("timestamp") or payload.get("time") or payload.get("eventTime")

        ts_str = format_timestamp(raw_ts)

        # Default values
        severity = 'low'
        header_icon = ":information_source:"
        title = f"{event_name}"
        detail_lines = [f"*Source:* {source}", f"*Time:* {ts_str}"]

        # Helper to build standard blocks
        def build_blocks(title_text, details_list, raw_payload=None):
            blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{title_text}*"}}]
            if details_list:
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(details_list)}})
            if raw_payload:
                try:
                    raw_json_short = json.dumps(raw_payload, indent=2)
                    if len(raw_json_short) > 1500:
                        raw_json_short = raw_json_short[:1500] + "\n... (truncated)"
                    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Raw Event (truncated):*\n```{raw_json_short}```"}})
                except Exception:
                    pass
            return blocks

        # Per-event templates (based on Wowza docs)
        # Application events
        if event_name in ("app.started",):
            title = "Application started"
            detail_lines = [f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*VHost:* `{vhost}`", f"*Source:* {source}", f"*Time:* {ts_str}"]
            header_icon = ":white_check_mark:"
        elif event_name in ("app.shutdown",):
            title = "Application shutdown"
            detail_lines = [f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*VHost:* `{vhost}`", f"*Source:* {source}", f"*Time:* {ts_str}"]
            header_icon = ":warning:"
            severity = 'medium'

        # Live stream events
        elif event_name in ("stream.started",):
            title = "Live stream started"
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*VHost:* `{vhost}`", f"*State:* `{state}`", f"*Time:* {ts_str}"]
            header_icon = ":arrow_up_small:"
        elif event_name in ("stream.stopped",):
            title = "Live stream stopped"
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*VHost:* `{vhost}`", f"*State:* `{state}`", f"*Time:* {ts_str}"]
            header_icon = ":arrow_down_small:"

        # Recording events
        elif event_name in ("recording.started",):
            title = "Recording started"
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*Output:* {data.get('outputFile', 'N/A')}", f"*RecorderMode:* {data.get('recorderMode', 'N/A')}", f"*Time:* {ts_str}"]
            header_icon = ":black_circle:"
        elif event_name in ("recording.stopped",):
            title = "Recording stopped"
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*Output:* {data.get('outputFile', 'N/A')}", f"*Time:* {ts_str}"]
            header_icon = ":black_square_button:"
        elif event_name in ("recording.failed",):
            title = "Recording failed"
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*Error:* {data.get('error', data.get('message', 'Unknown'))}", f"*Time:* {ts_str}"]
            header_icon = ":rotating_light:"
            severity = 'high'
        elif event_name in ("recording.segment.started",):
            title = "Recording segment started"
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*Segment:* {data.get('segmentId', data.get('segment','N/A'))}", f"*Time:* {ts_str}"]
        elif event_name in ("recording.segment.ended",):
            title = "Recording segment ended"
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*Segment:* {data.get('segmentId', data.get('segment','N/A'))}", f"*Time:* {ts_str}"]

        # Re-streaming / MediaCaster / connection events
        elif event_name in ("connection.failure", "connect.failure", "connect.failed"):
            title = "Connection failure"
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*Error:* {data.get('error', data.get('message','Unknown'))}", f"*Endpoint:* {context.get('endpoint','N/A')}", f"*VHost:* `{vhost}`", f"*Time:* {ts_str}"]
            header_icon = ":rotating_light:"
            severity = 'high'
        elif event_name in ("connection.started", "connect.started", "connect.started"):
            title = "Connection started"
            detail_lines = [f"*Endpoint:* {context.get('endpoint','N/A')}", f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*VHost:* `{vhost}`", f"*Time:* {ts_str}"]
            header_icon = ":arrow_forward:"
        elif event_name in ("connection.success", "connect.success", "connect.success", "connect.success"):
            title = "Connection success"
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*AppInstance:* `{context.get('appInstance','_definst_')}`", f"*Endpoint:* {context.get('endpoint','N/A')}", f"*VHost:* `{vhost}`", f"*Time:* {ts_str}"]
            header_icon = ":white_check_mark:"

        # Generic fallback: look for 'failed' or 'error' in payload to mark high severity
        else:
            # If any 'failed' like token exists, escalate
            searchable = json.dumps(payload).lower()
            if any(tok in searchable for tok in ('fail', 'failed', 'error', 'failure', 'exception')):
                severity = 'high'
                header_icon = ":rotating_light:"
            title = event_name.replace('.', ' ').title()
            detail_lines = [f"*Stream:* `{stream}`", f"*App:* `{app}`", f"*VHost:* `{vhost}`", f"*State:* `{state}`", f"*Time:* {ts_str}"]

        # Prepend the icon to title for visual emphasis
        full_title = f"{header_icon} {title}"

        blocks = build_blocks(full_title, detail_lines, payload)
        text = f"{title}: {stream} ({app}) - {state} at {ts_str}"
        if severity == 'high' and not text.startswith(':'):
            text = ":rotating_light: " + text

        return text, blocks, severity
    except Exception as e:
        logging.error("Failed to translate payload: %s", e, exc_info=True)
        return "Failed to translate payload.", [], 'low'


@app.route('/webhook', methods=['POST'])
def wowza_webhook():
    """
    Endpoint to receive JSON payloads from Wowza.
    """
    logging.info("/webhook route triggered.")
    try:
        logging.debug("Raw request data: %s", request.get_data(as_text=True))
        payload = request.get_json()
        if not payload:
            logging.warning("No JSON payload received.")
            return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

        logging.info("Parsed payload: %s", payload)

        message = translate_payload(payload)
        logging.info("Translated message: %s", message)

        send_to_slack(message)

        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error("An error occurred while processing the webhook: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for Docker health checks and monitoring.
    """
    return jsonify({"status": "healthy", "service": "wowza-webhook-to-slack"}), 200


def format_timestamp(raw_ts):
    """Format the raw timestamp into a human-readable string in the server's local timezone.

    Accepts numeric epoch (sec or ms) or ISO-like strings. Falls back to str(raw_ts) when parsing fails.
    """
    try:
        if raw_ts is None:
            return datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')

        # Numeric epoch (seconds or milliseconds)
        if isinstance(raw_ts, (int, float)):
            ts = float(raw_ts)
            if ts > 1e12:  # likely milliseconds
                ts = ts / 1000.0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
            return dt.strftime('%Y-%m-%d %H:%M:%S %Z')

        # String: try ISO parse
        if isinstance(raw_ts, str):
            # Try to parse as integer string
            if raw_ts.isdigit():
                ts = float(raw_ts)
                if ts > 1e12:
                    ts = ts / 1000.0
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
                return dt.strftime('%Y-%m-%d %H:%M:%S %Z')

            try:
                # fromisoformat handles many ISO formats
                dt = datetime.fromisoformat(raw_ts)
                # If naive, assume UTC then convert to local
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc).astimezone()
                else:
                    dt = dt.astimezone()
                return dt.strftime('%Y-%m-%d %H:%M:%S %Z')
            except Exception:
                # Last resort: return the original string
                return raw_ts

        # Unknown type: stringify
        return str(raw_ts)
    except Exception:
        return str(raw_ts)


def send_to_slack(message):
    """
    Send the translated message to Slack.
    """
    try:
        slack_url = CONFIG.get('slack_webhook_url') or os.environ.get('SLACK_WEBHOOK_URL')
        if not slack_url:
            logging.warning("No Slack webhook configured. Skipping send_to_slack.")
            return

        # If translate_payload returns blocks, prefer blocks by default
        if isinstance(message, tuple) and len(message) >= 2:
            text, blocks, severity = message[0], message[1], (message[2] if len(message) > 2 else 'low')
        else:
            text = str(message)
            blocks = []
            severity = 'low'

        # If high severity, prefix the text with a stronger emoji for fallback plain text
        if severity == 'high' and not text.startswith(':'):
            text = ":rotating_light: " + text

        # Try sending blocks first (Blocks enabled by default)
        if blocks:
            payload_blocks = {"text": text, "blocks": blocks}
            try:
                resp = requests.post(slack_url, json=payload_blocks)
                if resp.status_code == 200:
                    logging.info("Slack Blocks message sent successfully.")
                    return
                else:
                    # If Slack rejects blocks (legacy workspace or webhook), log and fall back
                    logging.warning("Slack Blocks send failed (status %s). Falling back to plain text. Response: %s", resp.status_code, resp.text)
            except Exception as e:
                logging.warning("Exception when sending Blocks to Slack: %s. Falling back to plain text.", e, exc_info=True)

        # Fall back to plain text
        slack_payload = {"text": text}
        response = requests.post(slack_url, json=slack_payload)
        if response.status_code == 200:
            logging.info("Plain text message sent to Slack successfully.")
        else:
            logging.error("Failed to send plain text message to Slack: %s", response.text)
    except Exception as e:
        logging.error("An exception occurred while sending to Slack: %s", e, exc_info=True)

if __name__ == '__main__':
    # Get port from environment variable or default to 8080
    port = int(os.environ.get('PORT', 8080))
    # Run the Flask app
    logging.info("Starting Flask app on port %s.", port)
    app.run(host='0.0.0.0', port=port)