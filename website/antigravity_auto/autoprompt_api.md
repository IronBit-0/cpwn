# Autoprompt Automation API

The **Autoprompt Server** runs inside the `antibox` container on port **4020**. It provides a unified HTTP interface to control the Antigravity GUI (via Chrome Developer Protocol) and query the internal Universal Proxy.

**Base URL**: `http://localhost:4020`

---

## 1. Submit Prompt

Enters text into the Antigravity chat input and submits it.

*   **Endpoint**: `POST /prompt`
*   **Content-Type**: `application/json`
*   **Body**:
    ```json
    {
      "text": "Your prompt message here"
    }
    ```
*   **Behavior**:
    *   Locates the chat input box (using `data-lexical-editor="true"`).
    *   Focuses the input and types the text.
    *   Clicks the "Submit" button.
    *   Falls back to dispatching the "Enter" key if the button click fails.
*   **Response**: `200 OK` ("Prompt submitted") or `500 Error`.

---

## 2. Select Model

Switches the active AI model using the dropdown menu.

*   **Endpoint**: `POST /model`
*   **Content-Type**: `application/json`
*   **Body**:
    ```json
    {
      "model": "Target Model Name"
    }
    ```
    *   *Example*: `"GPT-OSS 120B"`, `"Gemini 3 Flash"`
*   **Behavior**:
    *   Finds the model dropdown button (using `headlessui-popover-button` ID).
    *   Clicks to open the menu.
    *   Searches for the menu item matching the requested model name.
    *   Clicks the item to select it.
*   **Response**: `200 OK` ("Model selected") or `500 Error`.

---

## 3. List Conversations

Retrieves a list of all conversation IDs from the internal backend.

*   **Endpoint**: `GET /conversations`
*   **Method**: Proxies to Universal Proxy (`getAllCascadeTrajectories`).
*   **Response**: `200 OK`
*   **Body**: JSON Array of objects.
    ```json
    [
      {
        "id": "2a11a0bd-9468-452b-ba69-6081ce41b100",
        "name": "Project Planning"
      },
      {
        "id": "5e9dcd43-54a1-4dd2-99ff-f8bff41dd076",
        "name": "Debugging Session"
      }
    ]
    ```

---

## 4. Get Conversation Details

Retrieves the full history and metadata for a specific conversation.

*   **Endpoint**: `GET /conversation/<cascade_id>`
*   **Method**: Proxies to Universal Proxy (`getCascadeTrajectory`).
*   **Parameters**:
    *   `cascade_id`: The UUID of the conversation.
*   **Response**: `200 OK`
*   **Body**: Complete JSON object of the conversation trajectory (Protobuf-like structure).

---

## Technical Notes

*   **GUI Interaction**: Endpoints `/prompt` and `/model` interact directly with the running Antigravity Electron app using **CDP (Chrome DevTools Protocol)**. They simulate low-level mouse and keyboard events for robustness.
*   **Data Proxy**: Endpoints `/conversations` and `/conversation/...` bypass the GUI entirely and query the local Universal Proxy on port `5555`.
*   **Persistence**: The server script (`autoprompt.py`) is located at `/usr/local/bin/autoprompt.py` inside the container and starts automatically on container boot.
