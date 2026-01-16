#!/bin/bash

while true; do
    clear
    echo "=== Antigravity Bot Monitor (Docker) ==="
    echo "Time: $(date)"
    echo ""
    
    # Check container status
    echo "[Container Status]"
    docker-compose ps
    echo ""
    
    # Check recent errors
    echo "[Recent Errors (last 5) - Engine]"
    docker-compose logs --tail=100 engine 2>/dev/null | grep -i "error\|critical" | tail -5 || echo "No recent errors"
    echo ""
    
    # Check 110007 errors
    echo "[110007 Errors (last hour) - Engine]"
    docker-compose logs --since=1h engine 2>/dev/null | grep -c "110007" 2>/dev/null || echo "0"
    echo ""
    
    # Check for system_online
    echo "[Bot Status]"
    docker-compose logs --tail=100 engine 2>/dev/null | grep "system_online" | tail -1 || echo "Bot not online yet"
    echo ""
    
    # Check alerts file
    echo "[Recent Alerts]"
    if [ -f "/opt/cryptobot/storage/alerts.log" ]; then
        tail -3 /opt/cryptobot/storage/alerts.log || echo "No alerts"
    else
        echo "No alerts file"
    fi
    echo ""
    
    echo "Press Ctrl+C to exit"
    sleep 10
done
