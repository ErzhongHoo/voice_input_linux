#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_SRC="$ROOT/voice_input/service/voice-input-linux.service"
SERVICE_DST="$HOME/.config/systemd/user/voice-input-linux.service"
CONFIG_DST="$HOME/.config/voice-input-linux.env"

echo "Creating virtualenv: $VENV"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"

mkdir -p "$HOME/.config/systemd/user"
mkdir -p "$HOME/.config"
if [[ ! -f "$CONFIG_DST" ]]; then
  if [[ -f "$ROOT/.env" ]]; then
    cp "$ROOT/.env" "$CONFIG_DST"
  else
    cp "$ROOT/.env.example" "$CONFIG_DST"
  fi
  chmod 600 "$CONFIG_DST"
fi

sed \
  -e "s|__PROJECT_DIR__|$ROOT|g" \
  -e "s|__PYTHON__|$VENV/bin/python|g" \
  -e "s|__CONFIG_FILE__|$CONFIG_DST|g" \
  "$SERVICE_SRC" > "$SERVICE_DST"

systemctl --user daemon-reload

echo "Installed systemd user service:"
echo "  $SERVICE_DST"
echo "Config file:"
echo "  $CONFIG_DST"
echo
echo "Run now:"
echo "  systemctl --user start voice-input-linux.service"
echo
echo "Enable autostart:"
echo "  systemctl --user enable voice-input-linux.service"
