FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    openbox \
    xterm \
    xvfb \
    x11vnc \
    novnc \
    python3-websockify \
    python3-numpy \
    curl \
    sqlite3 \
    wget \
    firefox-esr \
    ca-certificates \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libasound2 \
    libgbm1 \
    libnss3 \
    libxss1 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    dbus-x11 \
    python3-flask \
    python3-requests \
    && rm -rf /var/lib/apt/lists/*
    
# Clean up bad sources if any were added during previous steps (safety measure)
RUN rm -f /etc/apt/sources.list.d/cursor.list

RUN curl -L -o /tmp/cursor.deb "https://api2.cursor.sh/updates/download/golden/linux-x64-deb/cursor/2.3" \
    && apt-get update && apt-get install -y /tmp/cursor.deb \
    && rm /tmp/cursor.deb \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/share/novnc/vnc.html /usr/share/novnc/index.html

ENV DISPLAY=:1
ENV NO_VNC_PORT=6080
ENV VNC_RESOLUTION=1280x800

COPY entrypoint.sh /entrypoint.sh

COPY cursor_api /root/cursor_api
COPY stub_xdg_open.sh /usr/bin/xdg-open
RUN chmod +x /entrypoint.sh && chmod +x /usr/bin/xdg-open

EXPOSE 6080 5000

CMD ["/entrypoint.sh"]
