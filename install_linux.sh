#!/usr/bin/env bash
set -euo pipefail

# install_linux.sh
# Minimal interactive installer for WS_Slack_Translator on Linux.
# - copies the current repo into INSTALL_DIR (default /opt/ws_slack_translator)
# - creates a dedicated system user
# - creates a python venv and installs requirements
# - installs a systemd service to run the chosen entrypoint

################################################################################
# Configuration defaults (override by environment or during prompts)
DEFAULT_INSTALL_DIR="/opt/ws_slack_translator"
SERVICE_NAME="ws_slack_translator"
SYSTEM_USER="ws_slack"

################################################################################
echo "WS_Slack_Translator Linux installer"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found in PATH. Please install Python 3.8+ and rerun this script." >&2
  exit 1
fi

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

read -r -p "Install directory [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

read -r -p "Create system user for service (will use '$SYSTEM_USER')? [Y/n]: " yn
yn="${yn:-Y}"
if [[ "$yn" =~ ^[Yy] ]]; then
  CREATE_USER=1
else
  CREATE_USER=0
fi

# Choose entrypoint script
echo "Available candidate entrypoint scripts (in current repo):"
for s in websocket_listener.py http_server.py main.py app.py run.py; do
  if [ -f "$CURRENT_DIR/$s" ]; then
    echo "  - $s"
  fi
done

read -r -p "Entrypoint script to run as service (default: websocket_listener.py if present): " ENTRY
if [ -z "$ENTRY" ]; then
  if [ -f "$CURRENT_DIR/websocket_listener.py" ]; then
    ENTRY=websocket_listener.py
  elif [ -f "$CURRENT_DIR/http_server.py" ]; then
    ENTRY=http_server.py
  else
    echo "No default entrypoint found. Please specify a python script present in the repo." >&2
    exit 1
  fi
fi

FULL_ENTRY_SRC="$CURRENT_DIR/$ENTRY"
if [ ! -f "$FULL_ENTRY_SRC" ]; then
  echo "Entrypoint $ENTRY not found at $FULL_ENTRY_SRC" >&2
  exit 1
fi

echo "Installing into: $INSTALL_DIR"

# Need sudo for system paths
SUDO=""
if [ "$EUID" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO=sudo
  else
    echo "This installer needs root privileges to write to $INSTALL_DIR and /etc/systemd. Please run as root or install sudo." >&2
    exit 1
  fi
fi

echo "Creating install dir..."
$SUDO mkdir -p "$INSTALL_DIR"

echo "Copying files to $INSTALL_DIR (excluding .git and venv)..."
# Use rsync when available for reliable copies
if command -v rsync >/dev/null 2>&1; then
  $SUDO rsync -a --exclude='.git' --exclude='venv' --exclude='__pycache__' "$CURRENT_DIR/" "$INSTALL_DIR/"
else
  # fallback to tar
  (cd "$CURRENT_DIR" && tar --exclude='.git' --exclude='venv' --exclude='__pycache__' -c .) | $SUDO tar -C "$INSTALL_DIR" -x
fi

echo "Creating system user $SYSTEM_USER (if requested)..."
if [ "$CREATE_USER" -eq 1 ]; then
  if id -u "$SYSTEM_USER" >/dev/null 2>&1; then
    echo "User $SYSTEM_USER already exists"
  else
    $SUDO useradd --system --no-create-home --shell /usr/sbin/nologin "$SYSTEM_USER" || true
    echo "Created system user $SYSTEM_USER"
  fi
  OWNER="$SYSTEM_USER"
else
  OWNER=$(id -un)
fi

echo "Setting ownership of $INSTALL_DIR to $OWNER"
$SUDO chown -R "$OWNER":"$OWNER" "$INSTALL_DIR"

echo "Creating Python virtual environment..."
PYTHON_BIN=$(command -v python3)
$SUDO -u "$OWNER" "$PYTHON_BIN" -m venv "$INSTALL_DIR/venv"

echo "Upgrading pip and installing requirements (if present)..."
REQ_FILE="$INSTALL_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
  $SUDO "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
  $SUDO "$INSTALL_DIR/venv/bin/pip" install -r "$REQ_FILE"
else
  echo "No requirements.txt found in repo. Skipping pip install.";
fi

# Copy example config if present
if [ -f "$INSTALL_DIR/config.json.example" ] && [ ! -f "$INSTALL_DIR/config.json" ]; then
  echo "Copying config.json.example to config.json (edit it before starting the service)"
  $SUDO cp "$INSTALL_DIR/config.json.example" "$INSTALL_DIR/config.json"
  $SUDO chown "$OWNER":"$OWNER" "$INSTALL_DIR/config.json"
fi

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
echo "Creating systemd service: $SERVICE_FILE"

EXEC_START="$INSTALL_DIR/venv/bin/python -u $INSTALL_DIR/$ENTRY"

cat <<EOF | $SUDO tee "$SERVICE_FILE" >/dev/null
[Unit]
Description=WS_Slack_Translator service
After=network.target

[Service]
Type=simple
User=$OWNER
Group=$OWNER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$EXEC_START
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SERVICE_NAME"

echo "Service installed. Start it now? [Y/n]"
read -r start_now
start_now="${start_now:-Y}"
if [[ "$start_now" =~ ^[Yy] ]]; then
  $SUDO systemctl start "$SERVICE_NAME"
  echo "Service started. status:"
  $SUDO systemctl status --no-pager "$SERVICE_NAME" || true
else
  echo "Service enabled but not started. You can start it with: sudo systemctl start $SERVICE_NAME"
fi

echo "Installation complete. Edit $INSTALL_DIR/config.json as needed and check logs with: sudo journalctl -u $SERVICE_NAME -f"
