from flask import Flask, request, jsonify
import requests
import logging
import os
import json
from pathlib import Path
from datetime import datetime, timezone
import threading
import time
from collections import defaultdict

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

def load_config():
    """Load configuration from environment variables.
    
    Returns a dict with configuration.
    """
    cfg = {}
    slack_url = os.environ.get('SLACK_WEBHOOK_URL')
    if slack_url:
        cfg['slack_webhook_url'] = slack_url
    else:
        logging.warning("SLACK_WEBHOOK_URL not configured - Slack notifications will be skipped")
    
    return cfg


# Load configuration at import time
CONFIG = load_config()

# Initialize Flask app
app = Flask(__name__)

# Security configuration
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB limit for large VI webhooks
app.config['JSON_SORT_KEYS'] = False  # Preserve JSON order for logging

# Create requests session for connection pooling and timeouts
http_session = requests.Session()
http_session.timeout = 10  # Default 10s timeout

# Video Intelligence batching configuration
VI_BATCH_WINDOW = int(os.environ.get('VI_BATCH_WINDOW', '10'))  # seconds
vi_batch_lock = threading.Lock()
vi_batch_data = defaultdict(lambda: {'detections': [], 'first_seen': None, 'last_seen': None})
vi_batch_timer = None

# Shutdown flag for graceful termination
shutdown_flag = threading.Event()

def sanitize_url(url):
    """Sanitize webhook URL for safe logging."""
    if not url:
        return "<not configured>"
    # Show only protocol and domain, hide path/token
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/***"
    except:
        return "<configured>"

# Test log message to confirm logging works
slack_url = CONFIG.get('slack_webhook_url')
logging.info(f"HTTP server is starting. Slack webhook: {sanitize_url(slack_url)}")


def flush_vi_batch():
    """Flush accumulated video intelligence detections to Slack as a summary."""
    global vi_batch_timer
    
    with vi_batch_lock:
        if not vi_batch_data:
            vi_batch_timer = None
            return
        
        # Process each stream's batched data
        for stream_key, batch in list(vi_batch_data.items()):
            app_name, stream_name = stream_key.split('|', 1)
            detections = batch['detections']
            first_seen = batch['first_seen']
            last_seen = batch['last_seen']
            
            # Aggregate statistics
            total_count = len(detections)
            class_counts = defaultdict(int)
            confidence_sum = defaultdict(float)
            
            for det in detections:
                cls = det['class_name']
                class_counts[cls] += 1
                confidence_sum[cls] += det['confidence']
            
            # Calculate averages
            class_summary = []
            for cls in sorted(class_counts.keys(), key=lambda x: -class_counts[x]):
                count = class_counts[cls]
                avg_conf = confidence_sum[cls] / count
                class_summary.append(f"{count}× {cls} (avg {avg_conf:.0%})")
            
            duration = (last_seen - first_seen).total_seconds() if first_seen and last_seen else 0
            
            # Build Slack message
            title = f":eye: AI Detection Summary"
            detail_lines = [
                f"*Stream:* `{stream_name}`",
                f"*App:* `{app_name}`",
                f"*Duration:* {duration:.1f}s",
                f"*Total Detections:* {total_count}",
                f"*Classes:* {', '.join(class_summary)}",
                f"*Period:* {first_seen.strftime('%H:%M:%S')} - {last_seen.strftime('%H:%M:%S')}"
            ]
            
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(detail_lines)}}
            ]
            
            text = f"AI Detection: {total_count} objects detected on {stream_name} over {duration:.1f}s"
            message = (text, blocks, 'low')
            
            # Send to Slack
            try:
                send_to_slack(message)
                logging.info(f"Flushed VI batch for {stream_key}: {total_count} detections")
            except Exception as e:
                logging.error(f"Failed to send batched VI summary: {e}", exc_info=True)
        
        # Clear batch
        vi_batch_data.clear()
        vi_batch_timer = None


def schedule_vi_batch_flush():
    """Schedule a batch flush after the configured window."""
    global vi_batch_timer
    
    with vi_batch_lock:
        if vi_batch_timer is not None:
            return  # Timer already running
        
        vi_batch_timer = threading.Timer(VI_BATCH_WINDOW, flush_vi_batch)
        vi_batch_timer.daemon = True
        vi_batch_timer.start()


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
                    if len(raw_json_short) > 2800:
                        raw_json_short = raw_json_short[:2800] + "\n... (truncated)"
                    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Raw Event:*\n```{raw_json_short}```"}})
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

        # Video Intelligence events - BATCH mode
        elif event_name in ("video.intelligence.detection",):
            # Add detections to batch instead of immediate send
            vi_data = data.get('vi_data', [])
            stream_key = f"{app}|{stream}"
            current_time = datetime.now()
            
            with vi_batch_lock:
                batch = vi_batch_data[stream_key]
                
                # Initialize timestamps
                if batch['first_seen'] is None:
                    batch['first_seen'] = current_time
                batch['last_seen'] = current_time
                
                # Add all detections to batch
                for frame_data in vi_data:
                    for detection in frame_data.get('detections', []):
                        batch['detections'].append({
                            'class_name': detection.get('class_name', 'unknown'),
                            'confidence': detection.get('confidence', 0),
                            'frame_id': detection.get('frame_id', 0)
                        })
                
                logging.debug(f"Batched {len(vi_data)} VI frames for {stream_key}, total: {len(batch['detections'])}")
            
            # Schedule flush if not already scheduled
            schedule_vi_batch_flush()
            
            # Return None to skip immediate Slack send
            return None

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

        # Generic fallback: send raw JSON in Slack blocks for unrecognized events
        else:
            logging.info("Unrecognized event '%s', sending raw JSON payload to Slack.", event_name)
            
            # If any 'failed' like token exists, escalate severity
            searchable = json.dumps(payload).lower()
            if any(tok in searchable for tok in ('fail', 'failed', 'error', 'failure', 'exception')):
                severity = 'high'
                header_icon = ":rotating_light:"
            else:
                header_icon = ":grey_question:"
            
            title = f"Unknown Event: {event_name.replace('.', ' ').title()}"
            full_title = f"{header_icon} {title}"
            
            # Build blocks with only raw JSON (no detail_lines)
            try:
                raw_json = json.dumps(payload, indent=2)
                if len(raw_json) > 2800:  # Leave room for markdown syntax
                    raw_json = raw_json[:2800] + "\n... (truncated)"
            except Exception:
                raw_json = str(payload)
            
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{full_title}*"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"```{raw_json}```"}}
            ]
            
            text = f"{title} - Raw payload logged"
            if severity == 'high':
                text = ":rotating_light: " + text
            
            return text, blocks, severity

        # Prepend the icon to title for visual emphasis (for recognized events)
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

        # Log payload only at DEBUG level to avoid sensitive data exposure
        event_name = payload.get('name', 'unknown')
        logging.info(f"Received event: {event_name}")
        logging.debug("Full payload: %s", payload)

        message = translate_payload(payload)
        
        # Skip Slack send if batching (message will be None for VI detections)
        if message is not None:
            logging.info("Translated message: %s", message)
            send_to_slack(message)
        else:
            logging.debug("Message batched, skipping immediate Slack send")

        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error("An error occurred while processing the webhook: %s", e, exc_info=True)
        # Don't expose internal error details to external callers
        return jsonify({"status": "error", "message": "Internal processing error"}), 500


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
                resp = http_session.post(slack_url, json=payload_blocks, timeout=10)
                if resp.status_code == 200:
                    logging.info("Slack Blocks message sent successfully.")
                    return
                else:
                    # If Slack rejects blocks (legacy workspace or webhook), log and fall back
                    logging.warning("Slack Blocks send failed (status %s). Falling back to plain text.", resp.status_code)
            except requests.exceptions.Timeout:
                logging.error("Timeout sending Blocks to Slack. Falling back to plain text.")
            except Exception as e:
                logging.warning("Exception when sending Blocks to Slack: %s. Falling back to plain text.", str(e))

        # Fall back to plain text
        slack_payload = {"text": text}
        try:
            response = http_session.post(slack_url, json=slack_payload, timeout=10)
            if response.status_code == 200:
                logging.info("Plain text message sent to Slack successfully.")
            else:
                logging.error("Failed to send plain text message to Slack (status %s)", response.status_code)
        except requests.exceptions.Timeout:
            logging.error("Timeout sending plain text to Slack")
        except Exception as e:
            logging.error("Exception sending plain text to Slack: %s", str(e))
    except Exception as e:
        logging.error("An exception occurred while sending to Slack: %s", e, exc_info=True)

def shutdown_handler(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT."""
    logging.info("Shutdown signal received (%s). Flushing pending data...", signum)
    shutdown_flag.set()
    
    # Flush any pending VI batches
    try:
        flush_vi_batch()
        logging.info("VI batches flushed successfully.")
    except Exception as e:
        logging.error("Error flushing VI batches during shutdown: %s", e)
    
    # Cancel any pending timers
    global vi_batch_timer
    if vi_batch_timer is not None:
        vi_batch_timer.cancel()
        logging.info("Cancelled pending VI batch timer.")
    
    # Close HTTP session
    try:
        http_session.close()
        logging.info("HTTP session closed.")
    except Exception as e:
        logging.error("Error closing HTTP session: %s", e)
    
    logging.info("Graceful shutdown complete.")

if __name__ == '__main__':
    import signal
    
    # Register shutdown handlers
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    # Get port from environment variable or default to 8080
    port = int(os.environ.get('PORT', 8080))
    # Run the Flask app (development mode only - use Gunicorn in production)
    logging.info("Starting Flask development server on port %s.", port)
    logging.warning("WARNING: Using Flask development server. Use Gunicorn in production.")
    app.run(host='0.0.0.0', port=port)