# Antigravity Manager

A Flask-based web application for deploying and monitoring Antigravity automation containers. This application provides a web interface to manage multiple instances of the `antigravity_auto` Docker container, each with its own account credentials, challenge files, and model configuration.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [File Structure](#file-structure)
- [Installation & Running](#installation--running)
- [Pages](#pages)
  - [Deploy Page](#deploy-page)
  - [Monitor Page](#monitor-page)
- [API Endpoints](#api-endpoints)
- [Docker Configuration](#docker-configuration)
- [Antigravity Container Integration](#antigravity-container-integration)
- [Technical Details](#technical-details)

---

## Overview

The Antigravity Manager allows you to:

- **Deploy** new Antigravity container instances with custom:
  - Account credentials (browser profile data)
  - Challenge files (copied to `/home/chal` in the container)
  - Model selection (Gemini Pro 3 High, GPT-OSS 120B, Claude Sonnet 4, etc.)
  - Initial prompt/challenge description

- **Monitor** running containers with:
  - Live noVNC viewer (view-only mode)
  - Full conversation history display
  - Tool call visualization (commands, file edits, file views)
  - Collapsible sections for thinking and tool outputs

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Host Machine                             │
│                                                                  │
│  ┌──────────────────────┐     ┌──────────────────────────────┐  │
│  │  antigravity-manager │     │      antibox_1               │  │
│  │  (Flask App)         │     │  ┌────────────────────────┐  │  │
│  │                      │     │  │ Antigravity IDE        │  │  │
│  │  Port 8080 ─────────────────► │ noVNC: 6080            │  │  │
│  │                      │     │  │ API: 4020              │  │  │
│  │  Docker Socket ◄─────┤     │  └────────────────────────┘  │  │
│  └──────────────────────┘     └──────────────────────────────┘  │
│                               ┌──────────────────────────────┐  │
│                               │      antibox_2               │  │
│                               │  noVNC: 6090, API: 6092      │  │
│                               └──────────────────────────────┘  │
│                                                                  │
│  Network: boxnet (10.4.4.0/24)                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
/home/cpwn/boxes/website/
├── flask_app/                      # Main Flask application
│   ├── app.py                      # Flask application code
│   ├── Dockerfile                  # Docker image for Flask app
│   ├── docker-compose.yml          # Docker Compose configuration
│   ├── requirements.txt            # Python dependencies
│   ├── run.sh                      # Manual run script
│   ├── .dockerignore               # Docker build ignore file
│   ├── templates/
│   │   ├── base.html               # Base template with header/nav
│   │   ├── deploy.html             # Deploy page template
│   │   └── monitor.html            # Monitor page template
│   ├── static/                     # Static assets (empty)
│   ├── uploads/                    # Temporary upload storage
│   └── container_data/             # Per-container data storage
│       └── antibox_N/
│           ├── chal/               # Challenge files
│           └── antigravity-data/   # Account/browser data
│
├── accounts/                       # Account profiles
│   └── 1/                          # Account "1" (Chromium profile)
│       ├── Cookies
│       ├── Session Storage/
│       └── ...
│
├── antigravity_auto/               # Antigravity container source
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── entrypoint.sh
│   ├── autoprompt_server.py        # API server (port 4020)
│   └── extension_patched.js        # Patched extension for RPC
│
└── out.json                        # Example conversation data
```

---

## Installation & Running

### Prerequisites

- Docker and Docker Compose installed
- Sudo access (for initial setup)
- The `antigravity_auto` image built

### Build and Start

```bash
cd /home/cpwn/boxes/website/flask_app

# Build and start the Flask container
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Build the Antigravity Image (if not already built)

```bash
cd /home/cpwn/boxes/website/antigravity_auto
docker build -t antigravity_auto .
```

### Access

- **Web Interface**: http://localhost:8080
- **Deploy Page**: http://localhost:8080/deploy
- **Monitor Page**: http://localhost:8080/monitor

---

## Pages

### Deploy Page

**URL**: `/deploy`

The deploy page allows you to create new Antigravity container instances.

#### Form Fields

| Field | Description |
|-------|-------------|
| **Account** | Select from available account folders in `/accounts/`. Each account contains browser profile data (cookies, session storage, etc.) |
| **Model** | Select the AI model to use. Options: Gemini Pro 3 High (default), GPT-OSS 120B, Gemini 3 Flash, Claude Sonnet 4, Claude Opus 4 |
| **Challenge Files** | Drag & drop or click to upload files. These are copied to `/home/chal` in the container |
| **Challenge Description** | Initial prompt sent to the AI after container startup |

#### Deployment Process

1. Creates a new Docker network `boxnet` (10.4.4.0/24) if it doesn't exist
2. Assigns the next available container name (`antibox_1`, `antibox_2`, etc.)
3. Finds available host ports for noVNC, reserved, and API
4. Copies account data to container's antigravity-data directory (skips socket files)
5. Copies uploaded challenge files to container's chal directory
6. Starts the container with appropriate volume mounts
7. Waits for the API to become available (up to 2 minutes)
8. Waits additional 15 seconds for extension initialization
9. Sends model change request (if not using default "Gemini Pro 3 High")
10. Sends the challenge description as the initial prompt

#### Response

```json
{
  "success": true,
  "container_name": "antibox_1",
  "container_id": "a1b2c3d4",
  "ip_address": "10.4.4.2",
  "ports": {
    "novnc": 6080,
    "api": 6082,
    "reserved": 6081
  }
}
```

---

### Monitor Page

**URL**: `/monitor`

The monitor page displays all deployed containers and allows you to view their status, noVNC screen, and conversation history.

#### Layout

```
┌─────────────┬──────────────────────────┬─────────────────────┐
│ Containers  │      noVNC Viewer        │   Conversations     │
│             │                          │                     │
│ antibox_1   │  [Live VNC Stream]       │  [1] [2] [3]        │
│ antibox_2   │  (view-only mode)        │                     │
│             │                          │  User: Hello        │
│ [Delete]    │                          │  Assistant: Hi...   │
│             │                          │  [Tool: Run Cmd]    │
└─────────────┴──────────────────────────┴─────────────────────┘
```

#### Features

- **Container List** (Left Panel)
  - Shows all `antibox_*` containers
  - Displays status (running/stopped), IP address, ports
  - Delete button for each container
  - Refresh button to update list
  - Auto-refreshes every 30 seconds

- **noVNC Viewer** (Center Panel)
  - Embeds noVNC in view-only mode
  - Shows live desktop of selected container
  - Uses `?autoconnect=true&view_only=true&resize=scale`

- **Conversation Panel** (Right Panel)
  - Numbered tabs for each conversation
  - Full message history display
  - Message types:
    - **User**: Blue background, user input
    - **Assistant**: Dark background with green header, AI responses
    - **Tool Calls**: Green border, collapsible by default
      - Run Command: Shows command and output
      - Code Edit: Shows file path and instruction
      - View File: Shows file path and content
      - List Directory: Shows path and entries
    - **Notifications**: Yellow border, system notifications
    - **Errors**: Red border, error messages
  - Collapsible "Thinking" sections for AI reasoning

---

## API Endpoints

### Flask Application Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Redirects to `/deploy` |
| GET | `/deploy` | Deploy page |
| POST | `/deploy` | Create new container |
| GET | `/monitor` | Monitor page |
| GET | `/api/containers` | List all antibox containers |
| GET | `/api/container/<name>/conversations` | Get conversations for container |
| GET | `/api/container/<name>/conversation/<id>` | Get conversation details |
| POST | `/api/container/<name>/delete` | Delete container |

### Container API Endpoints (port 4020)

These are the endpoints exposed by each Antigravity container:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/prompt` | Submit a prompt to the AI |
| POST | `/model` | Change the AI model |
| GET | `/conversations` | List all conversations |
| GET | `/conversation/<cascade_id>` | Get conversation trajectory |

#### POST /prompt

```json
{
  "text": "Your prompt message here"
}
```

#### POST /model

```json
{
  "model": "GPT-OSS 120B"
}
```

#### GET /conversations Response

```json
[
  {
    "id": "uuid-here",
    "name": "Conversation title"
  }
]
```

---

## Docker Configuration

### Flask App Container (`antigravity-manager`)

**docker-compose.yml**:

```yaml
services:
  antigravity-manager:
    build: .
    container_name: antigravity-manager
    hostname: antigravity-manager
    ports:
      - "8080:8080"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /home/cpwn/boxes/website/accounts:/accounts:ro
      - /home/cpwn/boxes/website/antigravity_auto:/antigravity_auto:ro
      - /home/cpwn/boxes/website/flask_app/container_data:/app/container_data
      - /home/cpwn/boxes/website/flask_app/uploads:/app/uploads
    environment:
      - FLASK_ENV=production
      - ACCOUNTS_FOLDER=/accounts
      - ANTIGRAVITY_AUTO_PATH=/antigravity_auto
      - HOST_CONTAINER_DATA_PATH=/home/cpwn/boxes/website/flask_app/container_data
      - HOST_ACCOUNTS_PATH=/home/cpwn/boxes/website/accounts
    restart: unless-stopped
```

**Key Points**:
- Mounts Docker socket for container management
- Uses `host.docker.internal` to access sibling container ports
- Separate paths for internal use vs. Docker volume mounts (HOST_* vars)

### Antigravity Container (`antibox_N`)

Each deployed container uses:

```yaml
ports:
  - "6080:6080"   # noVNC
  - "6081:5000"   # Reserved
  - "6082:4020"   # API
volumes:
  - ./chal:/home/chal
  - ./antigravity-data:/root/.config/antigravity-data
environment:
  - VNC_RESOLUTION=1280x800
shm_size: 2gb
network: boxnet
```

### Network Configuration

```
Network: boxnet
Driver: bridge
Subnet: 10.4.4.0/24
Gateway: 10.4.4.1
Container IPs: 10.4.4.2, 10.4.4.3, ...
```

---

## Antigravity Container Integration

### Internal Architecture

The Antigravity container runs:

1. **Xvfb** - Virtual X11 framebuffer (display :1, 1280x800)
2. **Openbox** - Window manager
3. **x11vnc** - VNC server (port 5900)
4. **noVNC** - Web VNC client (port 6080)
5. **Antigravity** - Electron-based IDE with Chrome debugging (port 9222)
6. **Autoprompt Server** - Python HTTP API (port 4020)
7. **Universal Proxy** - Internal RPC bridge (port 5555)

### Conversation Data Structure

The conversation API returns trajectory data with this structure:

```json
{
  "trajectory": {
    "steps": [
      {
        "type": "CORTEX_STEP_TYPE_USER_INPUT",
        "userInput": {
          "items": [{"text": "User message"}]
        }
      },
      {
        "type": "CORTEX_STEP_TYPE_PLANNER_RESPONSE",
        "plannerResponse": {
          "response": "AI response text",
          "thinking": "AI reasoning (optional)"
        }
      },
      {
        "type": "CORTEX_STEP_TYPE_RUN_COMMAND",
        "runCommand": {
          "commandLine": "ls -la",
          "combinedOutput": {"full": "output here"}
        }
      },
      {
        "type": "CORTEX_STEP_TYPE_CODE_ACTION",
        "codeAction": {
          "actionSpec": {
            "createFile": {
              "path": {"absoluteUri": "file:///path/to/file"}
            }
          }
        }
      }
    ]
  }
}
```

### Step Types

| Type | Description | Key Fields |
|------|-------------|------------|
| `CORTEX_STEP_TYPE_USER_INPUT` | User message | `userInput.items[].text` |
| `CORTEX_STEP_TYPE_PLANNER_RESPONSE` | AI response | `plannerResponse.response`, `.thinking` |
| `CORTEX_STEP_TYPE_RUN_COMMAND` | Shell command | `runCommand.commandLine`, `.combinedOutput` |
| `CORTEX_STEP_TYPE_COMMAND_STATUS` | Command result | `commandStatus.combined` |
| `CORTEX_STEP_TYPE_CODE_ACTION` | File edit | `codeAction.actionSpec.createFile.path.absoluteUri` |
| `CORTEX_STEP_TYPE_VIEW_FILE` | File read | `viewFile.absolutePathUri`, `.content` |
| `CORTEX_STEP_TYPE_LIST_DIRECTORY` | Directory list | `listDirectory.absolutePathUri`, `.entries` |
| `CORTEX_STEP_TYPE_NOTIFY_USER` | Notification | `notifyUser.notificationContent` |
| `CORTEX_STEP_TYPE_ERROR_MESSAGE` | Error | `errorMessage.error.userErrorMessage` |

---

## Technical Details

### Account Data Handling

When copying account data, the application skips special files that cannot be copied:
- Socket files (`.sock`)
- Named pipes (FIFOs)
- Block devices
- Character devices

This prevents errors like `[Errno 6] No such device or address`.

### Port Allocation

The application finds available ports starting from 6080:
1. Checks all existing container port bindings
2. Checks if ports are in use by the system
3. Allocates 3 consecutive ports (noVNC, reserved, API)

### Container Naming

Containers are named sequentially: `antibox_1`, `antibox_2`, etc.
The next number is determined by finding the highest existing number and adding 1.

### Startup Timing

After container creation:
1. Initial 5-second wait
2. Poll API endpoint for up to 2 minutes (60 retries, 2 seconds each)
3. Additional 15-second wait for extension initialization
4. Then send model change and initial prompt

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UPLOAD_FOLDER` | `/app/uploads` | Upload directory path |
| `ACCOUNTS_FOLDER` | `/accounts` | Accounts directory path |
| `ANTIGRAVITY_AUTO_PATH` | `/antigravity_auto` | Antigravity source path |
| `CONTAINER_DATA_PATH` | `/app/container_data` | Container data path (internal) |
| `HOST_CONTAINER_DATA_PATH` | Same as above | Host path for Docker volumes |
| `HOST_ACCOUNTS_PATH` | `/accounts` | Host path for accounts |
| `DOCKER_HOST_ADDRESS` | `host.docker.internal` | Host for accessing container ports |

---

## Troubleshooting

### Container won't start

1. Check if the `antigravity_auto` image exists: `docker images | grep antigravity`
2. Check Docker logs: `docker logs antibox_1`
3. Ensure the `boxnet` network exists: `docker network ls`

### API returns empty/error

1. Wait longer - the extension takes time to initialize
2. Check container logs: `docker logs antibox_1`
3. Verify the API is responding: `curl http://localhost:6082/conversations`

### Conversation not showing latest messages

1. Click "Refresh" or reload the page
2. The conversation data is fetched on-demand, not real-time

### noVNC not connecting

1. Ensure the container is running
2. Check if the noVNC port is accessible: `curl http://localhost:6080`
3. Try accessing noVNC directly: `http://localhost:6080/vnc.html`
