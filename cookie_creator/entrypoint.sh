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

# Start Antigravity
sleep 2
/usr/bin/antigravity --remote-debugging-port=9222 --no-sandbox --disable-gpu --user-data-dir /root/.config/antigravity-data /home/chal &

# Start Automation Server
sleep 5
python3 -u /usr/local/bin/autoprompt.py > /var/log/autoprompt.log 2>&1 &

# Wait for essential processes (Xvfb, Openbox, VNC)
# If any of these die, we should exit.
wait -n $PID_XVFB $PID_OPENBOX $PID_X11VNC $PID_NOVNC