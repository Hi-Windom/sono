#!/bin/bash
while true; do
  if ! curl -s --max-time 5 http://localhost:8000/health > /dev/null 2>&1; then
    echo "$(date) Backend down, restarting..." >> /workspace/backend/watchdog.log
    pkill -f "uvicorn app:create_app" 2>/dev/null
    sleep 2
    cd /workspace/backend && python3 -m uvicorn app:create_app --host 0.0.0.0 --port 8000 --factory >> /workspace/backend/server.log 2>&1 &
    sleep 5
    if curl -s --max-time 5 http://localhost:8000/health > /dev/null 2>&1; then
      echo "$(date) Backend restarted successfully" >> /workspace/backend/watchdog.log
    else
      echo "$(date) Backend restart failed" >> /workspace/backend/watchdog.log
    fi
  fi
  sleep 10
done
