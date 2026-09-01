#!/bin/bash
# Starts (or restarts) a public Cloudflare quick tunnel pointed at the local MedPulse server.
# Prints the public URL once it's ready. The server itself (server.py) must already be running
# on port 8000 - this script only creates the public entry point to it.
#
# Note: a "quick tunnel" is free and needs no account, but its URL is randomly generated every
# time it starts and is not guaranteed to stay up long-term. If you want a permanent, stable
# URL, that requires a free Cloudflare account and a named tunnel instead - ask Claude to set
# that up if you want it.

set -e
cd "$(dirname "$0")"

LOG_FILE="/tmp/medpulse_tunnel.log"

if ! curl -s -o /dev/null http://localhost:8000; then
  echo "The MedPulse server doesn't seem to be running on port 8000."
  echo "Start it first with: python3 server.py  (or ./start.sh)"
  exit 1
fi

echo "Starting Cloudflare quick tunnel..."
nohup ./.bin/cloudflared tunnel --url http://localhost:8000 > "$LOG_FILE" 2>&1 &
disown

for i in $(seq 1 15); do
  sleep 1
  URL=$(grep -o 'https://[a-zA-Z0-9.-]*trycloudflare\.com' "$LOG_FILE" | head -1)
  if [ -n "$URL" ]; then
    echo ""
    echo "Public URL: $URL"
    echo "(Share this link with anyone. It stays live as long as this Mac is on and this tunnel process keeps running.)"
    exit 0
  fi
done

echo "Tunnel did not report a URL in time - check $LOG_FILE for details."
exit 1
