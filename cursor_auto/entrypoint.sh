#!/bin/bash
set -e

# Cleanup
rm -f /tmp/.X1-lock
rm -f /tmp/.X11-unix/X1

# Start Xvfb
Xvfb :1 -screen 0 ${VNC_RESOLUTION}x24 &
export PID_XVFB=$!
sleep 2

# Start Openbox
openbox-session &
export PID_OPENBOX=$!

x11vnc -display :1 -nopw -listen localhost -xkb -forever &
export PID_X11VNC=$!

# Start noVNC
websockify --web=/usr/share/novnc ${NO_VNC_PORT} localhost:5900 &
export PID_NOVNC=$!

# Start Cursor Control API
python3 /root/cursor_api/inject_cursor_settings.py
python3 /root/cursor_api/server.py &
export PID_API=$!

# Auto-start Cursor
# We wait a bit for things to settle
sleep 2
# Launch cursor with no-sandbox and user-data-dir as required for root
# Use direct binary to avoid wrapper issues and ensure CDP port binds
# Open /home/chal by default
/usr/share/cursor/cursor --no-sandbox --user-data-dir /root/.config/cursor-data --disable-gpu --remote-debugging-port=9222 /home/chal &

# Wait for essential processes (Xvfb, Openbox, VNC)
# If any of these die, we should exit.
wait -n $PID_XVFB $PID_OPENBOX $PID_X11VNC $PID_NOVNC
