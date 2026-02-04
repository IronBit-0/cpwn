FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    openbox \
    xterm \
    xvfb \
    x11vnc \
    novnc \
    python3-websockify \
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
    gnupg \
    sudo \
    && rm -rf /var/lib/apt/lists/*
    
# Install Antigravity
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://us-central1-apt.pkg.dev/doc/repo-signing-key.gpg | \
      gpg --dearmor --yes -o /etc/apt/keyrings/antigravity-repo-key.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/antigravity-repo-key.gpg] https://us-central1-apt.pkg.dev/projects/antigravity-auto-updater-dev/ antigravity-debian main" | \
      tee /etc/apt/sources.list.d/antigravity.list > /dev/null \
    && apt-get update \
    && apt-get install -y antigravity

# Install CTF tools and standard utils
RUN apt-get update && apt-get install -y \
    binutils \
    net-tools \
    iputils-ping \
    iproute2 \
    zip \
    unzip \
    bzip2 \
    tree \
    htop \
    lsof \
    less \
    nano \
    man-db \
    gdb \
    gdb-multiarch \
    ltrace \
    strace \
    binwalk \
    foremost \
    openssl \
    gnupg \
    hashcat \
    john \
    nmap \
    sqlmap \
    gobuster \
    dirb \
    hydra \
    netcat-openbsd \
    socat \
    tcpdump \
    tshark \
    steghide \
    exiftool \
    pngcheck \
    sleuthkit \
    testdisk \
    python3 \
    python3-pip \
    python3-dev \
    ruby \
    ruby-dev \
    php \
    nodejs \
    npm \
    gcc \
    g++ \
    make \
    nasm \
    jq \
    imagemagick \
    poppler-utils \
    p7zip-full \
    unrar-free \
    cpio \
    squashfs-tools \
    libffi-dev \
    libssl-dev \
    libgmp-dev \
    zlib1g-dev \
    build-essential \
    cmake \
    git \
    curl \
    wget \
    vim \
    tmux \
    file \
    xxd \
    bsdmainutils \
    dos2unix \
    patchelf \
    elfutils \
    qemu-system \
    qemu-user \
    qemu-user-static \
    fcrackzip \
    pdfcrack \
    masscan \
    dnsutils \
    whois \
    ncat \
    hashdeep \
    ssdeep \
    capstone-tool \
    libcapstone-dev \
    z3 \
    libz3-dev \
    python3-pillow \
    python3-requests \
    python3-flask \
    python3-numpy \
    python3-scapy \
    perl \
    php-cli \
    golang \
    rustc \
    cargo \
    clang \
    llvm \
    valgrind \
    patool \
    cabextract \
    libarchive-tools \
    ntfs-3g \
    e2fsprogs \
    dosfstools \
    sslscan \
    whatweb \
    smbclient \
    xclip \
    graphviz \
    && rm -rf /var/lib/apt/lists/*


RUN ln -s /usr/share/novnc/vnc.html /usr/share/novnc/index.html

ENV DISPLAY=:1
ENV NO_VNC_PORT=6080
ENV VNC_RESOLUTION=1280x800

COPY entrypoint.sh /entrypoint.sh
COPY extension_patched.js /usr/share/antigravity/resources/app/extensions/antigravity/dist/extension.js
COPY autoprompt_server.py /usr/local/bin/autoprompt.py

RUN chmod +x /entrypoint.sh

EXPOSE 6080 5000

CMD ["/entrypoint.sh"]