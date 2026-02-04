import socket
import json
import secrets
import struct
import base64
import urllib.request
import time
import threading
import os
import shutil
import sqlite3

class CursorController:
    def __init__(self, host="127.0.0.1", port=9222):
        self.host = host
        self.port = port
        self.sock = None
        self.target_id = None
        self.lock = threading.Lock()
        
    def log(self, msg):
        print(f"[CursorController] {msg}")

    def get_targets(self):
        url = f"http://{self.host}:{self.port}/json/list"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.loads(response.read())
        except Exception as e:
            self.log(f"Failed to get targets: {e}")
            return []

    def connect(self):
        with self.lock:
            if self.sock: return True
            
            targets = self.get_targets()
            for t in targets:
                if t.get("type") == "page" and "Superuser" in t.get("title", ""):
                    self.target_id = t["id"]
                    break
            
            if not self.target_id and targets:
                self.target_id = targets[0]["id"]
                
            if not self.target_id:
                self.log("No targets found")
                return False
                
            self.log(f"Connecting to {self.target_id}...")
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(10.0)
                self.sock.connect((self.host, self.port))
                
                nonce = base64.b64encode(secrets.token_bytes(16)).decode()
                handshake = (
                    f"GET /devtools/page/{self.target_id} HTTP/1.1\r\n"
                    f"Host: {self.host}:{self.port}\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {nonce}\r\n"
                    "Sec-WebSocket-Version: 13\r\n"
                    "\r\n"
                )
                self.sock.sendall(handshake.encode())
                
                response = self.sock.recv(4096)
                if b"101 " not in response:
                    self.log("Handshake failed")
                    self.sock.close()
                    self.sock = None
                    return False
                    
                self.log("Connected!")
                return True
            except Exception as e:
                self.log(f"Connection error: {e}")
                if self.sock:
                    self.sock.close()
                    self.sock = None
                return False

    def create_ws_frame(self, message):
        frame = bytearray([0x81])
        payload = message.encode()
        length = len(payload)
        mask_key = secrets.token_bytes(4)
        if length < 126:
            frame.append(length | 0x80)
        elif length < 65536:
            frame.append(126 | 0x80)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(127 | 0x80)
            frame.extend(struct.pack("!Q", length))
        frame.extend(mask_key)
        masked_payload = bytearray(length)
        for i in range(length):
            masked_payload[i] = payload[i] ^ mask_key[i % 4]
        frame.extend(masked_payload)
        return frame

    def send_command(self, method, params=None):
        if not self.connect():
            return {"error": "Not connected"}
            
        cmd_id = int(time.time() * 1000) % 100000
        cmd = {
            "id": cmd_id,
            "method": method
        }
        if params:
            cmd["params"] = params
            
        try:
            with self.lock:
                self.sock.sendall(self.create_ws_frame(json.dumps(cmd)))
                
                # Simple read until we get response with matching ID
                # In robust implementation, we'd have a reader thread
                start = time.time()
                while time.time() - start < 5:
                    data = self.sock.recv(65536)
                    if not data: break
                    
                    # Frame decoding logic
                    # This is naive and assumes single frame response for simplicity of this framework
                    # Ideally use a websocket lib, but keeping it dep-free for now as requested
                    if len(data) > 2:
                        length = data[1] & 0x7F
                        offset = 2
                        if length == 126: offset = 4
                        elif length == 127: offset = 10
                        if len(data) < offset: continue
                        
                        payload = data[offset:]
                        try:
                            msg = json.loads(payload.decode('utf-8', errors='ignore'))
                            if msg.get("id") == cmd_id:
                                return msg.get("result", {})
                        except:
                            pass
                            
            return {"status": "sent"}
        except Exception as e:
            self.log(f"Send failed: {e}")
            self.sock.close()
            self.sock = None
            return {"error": str(e)}

    def click_login(self):
        js = """
        (function() {
            // Unified selector for all known button types
            const selectors = [
                '.onboarding-v2-welcome-button', 
                'button', 
                'a', 
                'div[role="button"]', 
                '.monaco-button'
            ].join(',');
            
            const buttons = Array.from(document.querySelectorAll(selectors));
            const loginBtn = buttons.find(b => {
                const text = b.innerText || b.title || "";
                return text.trim().toLowerCase() === 'log in';
            });
            
            if (loginBtn) {
                loginBtn.click();
                return {success: true};
            }
            
            return {success: false, reason: "not_found"};
        })()
        """
        res = self.send_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
        return res

    def click_continue(self):
        js = """
        (function() {
            // Unified selector for all known button types
            const selectors = [
                '.onboarding-v2-welcome-button', 
                'button', 
                'a', 
                'div[role="button"]', 
                '.monaco-button'
            ].join(',');
            
            const buttons = Array.from(document.querySelectorAll(selectors));
            const continueBtn = buttons.find(b => {
                const text = b.innerText || b.title || "";
                return text.trim().toLowerCase() === 'continue';
            });
            
            if (continueBtn) {
                continueBtn.click();
                return {success: true};
            }
            
            return {success: false, reason: "not_found"};
        })()
        """
        res = self.send_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
        res = self.send_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
        return res

    def get_login_url(self):
        """
        Reads the login URL captured by stub_xdg_open.sh
        """
        try:
            if os.path.exists('/tmp/cursor_login_url.txt'):
                with open('/tmp/cursor_login_url.txt', 'r') as f:
                    return {"success": True, "url": f.read().strip()}
        except Exception as e:
            return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "URL not found yet"}

    def _get_workspace_db_path(self):
        # Find the most recently modified workspaceStorage directory
        workspace_base = os.path.expanduser("/root/.config/cursor-data/User/workspaceStorage")
        if not os.path.exists(workspace_base):
            return None
        
        workspaces = [os.path.join(workspace_base, d) for d in os.listdir(workspace_base)]
        if not workspaces:
            return None
            
        # Sort by modification time, newest first
        latest_workspace = max(workspaces, key=os.path.getmtime)
        return os.path.join(latest_workspace, "state.vscdb")

    def _get_global_db_path(self):
        return os.path.expanduser("/root/.config/cursor-data/User/globalStorage/state.vscdb")

    def _read_db_value(self, db_path, table, key):
        if not db_path or not os.path.exists(db_path):
            return None

        # Copy DB to temp to avoid locking
        temp_db = f"/tmp/cursor_read_{secrets.token_hex(4)}.vscdb"
        try:
            shutil.copy2(db_path, temp_db)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT value FROM {table} WHERE key = ?", (key,))
            row = cursor.fetchone()
            
            conn.close()
            
            if row:
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError:
                    return row[0]
            return None
            
        except Exception as e:
            print(f"Error reading DB {db_path}: {e}")
            return None
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)

    def _read_global_bubbles(self, composer_id):
        """
        Retrieves all message bubbles for a specific composer conversation from the global DB.
        """
        db_path = self._get_global_db_path()
        if not db_path or not os.path.exists(db_path):
            return []

        temp_db = f"/tmp/cursor_bubbles_{secrets.token_hex(4)}.vscdb"
        bubbles = []
        try:
            shutil.copy2(db_path, temp_db)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()

            
            # Query for all keys starting with bubbleId:<composer_id>
            query_key = f"bubbleId:{composer_id}%"
            cursor.execute("SELECT value FROM cursorDiskKV WHERE key LIKE ?", (query_key,))
            
            rows = cursor.fetchall()
            for row in rows:
                try:
                    bubble_data = json.loads(row[0])
                    bubbles.append(bubble_data)
                except:
                    continue
            
            conn.close()
            
            # Sort by creation time if available
            bubbles.sort(key=lambda x: x.get('createdAt', ''))
            
            return bubbles
            
        except Exception as e:
            print(f"Error reading global bubbles: {e}")
            return []
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)

    def get_conversations(self):
        """
        Retrieves a list of conversations from the current workspace state.
        """
        db_path = self._get_workspace_db_path()
        if not db_path:
            return []
            
        # Read composer data which contains the list of conversations
        # The key is 'composer.composerData' in the workspace 'state.vscdb'
        
        data = self._read_db_value(db_path, "ItemTable", "composer.composerData")
        if not data:
            return []
            
        return data.get("allComposers", [])

    def get_conversation_content(self, composer_id):
        """
        Retrieves the full content (messages) of a specific conversation.
        Combines metadata from 'composerData:<id>' effectively.
        """
        # Retrieve bubbles from global DB
        bubbles = self._read_global_bubbles(composer_id)
        
        # Simplified message format
        messages = []
        for b in bubbles:
            msg = {
                "id": b.get("bubbleId", ""),
                "type": b.get("type", "unknown"),
                "createdAt": b.get("createdAt", ""),
                "model": b.get("modelInfo", {}).get("modelName", "unknown"),
            }

            # handle standard text
            text = b.get("text", "")
            if text:
                msg["text"] = text

            # handle explicit thinking blocks
            thinking = b.get("allThinkingBlocks", [])
            if thinking:
                msg["thinking"] = thinking

            # handle tool usage (capabilityType 15 seems to be tool use)
            tool_data = b.get("toolFormerData")
            if tool_data:
                msg["toolCall"] = {
                    "name": tool_data.get("name"),
                    "params": tool_data.get("params"),
                    "result": tool_data.get("result"),
                    "status": tool_data.get("status")
                }
            
            messages.append(msg)
            
        return {
            "composerId": composer_id,
            "messageCount": len(messages),
            "messages": messages
        }

    def render_conversation_text(self, composer_id):
        """
        Returns a formatted string representation of the conversation,
        including hidden thinking blocks and tool calls.
        """
        data = self.get_conversation_content(composer_id)
        messages = data.get("messages", [])
        
        output = []
        output.append(f"Found {len(messages)} messages.")
        
        for i, msg in enumerate(messages):
            # Format Thinking
            if "thinking" in msg:
                 output.append(f"\n[MSG {i}] --- THINKING ---")
                 for block in msg.get("thinking", []):
                     output.append(str(block))
            
            # Format Tool Call
            if "toolCall" in msg:
                tc = msg["toolCall"]
                output.append(f"\n[MSG {i}] --- TOOL CALL: {tc.get('name')} ---")
                output.append(f"Params: {tc.get('params')}")
                res = tc.get('result', '')
                if res and len(res) > 200:
                    res = res[:200] + "..."
                output.append(f"Result: {res}")
            
            # Format Text
            text = msg.get("text", "")
            if text:
                output.append(f"\n[MSG {i}] --- TEXT ---")
                output.append(text.strip())
                
        return "\n".join(output)

    def send_key(self, output_key, modifiers=0):
        """
        Sends a key combination via CDP.
        modifiers: 1=Alt, 2=Ctrl, 4=Meta/Command, 8=Shift
        """
        # Minimal mapping for sidebar toggle (S), Settings (J), Close (W)
        key_map = {
            'S': {'windowsVirtualKeyCode': 83, 'code': 'KeyS', 'key': 's'},
            'J': {'windowsVirtualKeyCode': 74, 'code': 'KeyJ', 'key': 'j'},
            'W': {'windowsVirtualKeyCode': 87, 'code': 'KeyW', 'key': 'w'},
        }
        
        meta = key_map.get(output_key, {'text': output_key})
        
        cmd_down = {
            "type": "keyDown",
            "modifiers": modifiers,
            "text": meta.get('key', output_key.lower()),
            "unmodifiedText": meta.get('key', output_key.lower()),
            "key": meta.get('key', output_key.lower()),
            "code": meta.get('code', ''),
            "windowsVirtualKeyCode": meta.get('windowsVirtualKeyCode', 0)
        }
        self.send_command("Input.dispatchKeyEvent", cmd_down)
        
        cmd_up = {
             "type": "keyUp",
             "modifiers": modifiers,
             "key": meta.get('key', output_key),
             "code": meta.get('code', ''),
             "windowsVirtualKeyCode": meta.get('windowsVirtualKeyCode', 0)
        }
        self.send_command("Input.dispatchKeyEvent", cmd_up)
        return {"success": True}

    def is_sidebar_open(self):
        # We identified 'workbench.parts.unifiedsidebar' as the AI sidebar
        js = """
        (function() {
            const sidebar = document.getElementById('workbench.parts.unifiedsidebar');
            if (sidebar && sidebar.offsetParent !== null) {
                return true;
            }
            // Fallback: check standard sidebar
            const stdSidebar = document.getElementById('workbench.parts.sidebar');
            return !!(stdSidebar && stdSidebar.offsetParent !== null);
        })()
        """
        res = self.send_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
        return res.get('result', {}).get('value', False)

    def toggle_sidebar(self, target_state=None):
        current = self.is_sidebar_open()
        if target_state is not None:
            if current == target_state:
                return {"success": True, "state": current}
        
        # Toggle using Ctrl+Alt+S
        # Ctrl=2, Alt=1 -> Modifiers=3
        self.send_key('S', modifiers=3)
        
        time.sleep(1.0) # Wait for animation
        new_state = self.is_sidebar_open()
        return {"success": True, "state": new_state}

    def new_conversation(self):
        # Allow sidebar to open if closed, but we try clicking regardless (user flow)
        if not self.is_sidebar_open():
            self.toggle_sidebar(True)
            
        # Click the "New Agent" button
        js = """
        (function() {
            const btn = document.querySelector('.new-agent-sidebar-new-button');
            if (btn && btn.offsetParent !== null) {
                btn.click();
                return true;
            }
            return false;
        })()
        """
        res = self.send_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
        clicked = res.get('result', {}).get('value', False)
        
        return {"success": str(clicked).lower() == 'true'}

    def change_model(self, model_name):
        # 1. Click the model dropdown (usually text "Auto" or current model)
        js_click = """
        (function() {
            // Priority: .composer-unified-dropdown-model
            const dropdown = document.querySelector('.composer-unified-dropdown-model');
            if (dropdown && dropdown.offsetParent !== null) {
                dropdown.click();
                return true;
            }
            return false;
        })()
        """
        res_click = self.send_command("Runtime.evaluate", {"expression": js_click, "returnByValue": True})
        clicked = res_click.get('result', {}).get('value', False)
        
        if not clicked:
             return {"success": False, "error": "Model dropdown not found"}
        
        time.sleep(3.0) # Wait for dropdown to render

        # 2. Find and type in the search box
        # We use dispatchKeyEvent for typing (Input.insertText might not work if not focused, 
        # but the click ensures focus)
        js = f"""
        (function() {{
            const input = document.querySelector('input[placeholder="Search models"]');
            if (input && input.offsetParent !== null) {{
                input.focus();
                input.value = ''; // clear
                document.execCommand('insertText', false, '{model_name}');
                return true;
            }}
            return false;
        }})()
        """
        res = self.send_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
        found = res.get('result', {}).get('value', False)
        
        if not found:
            return {"success": False, "error": "Search model input not found"}

        time.sleep(2.0) # Wait for search results
        
        # 3. Find and click first result
        js_select = """
        (function() {
            const items = document.querySelectorAll('.composer-unified-context-menu-item');
            if (items.length > 0) {
                items[0].click();
                return true;
            }
            return false;
        })()
        """
        res_select = self.send_command("Runtime.evaluate", {"expression": js_select, "returnByValue": True})
        selected = res_select.get('result', {}).get('value', False)
        
        if not selected:
             return {"success": False, "error": "Model result item not found"}
        
        return {"success": True, "model": model_name}

    def send_chat_message(self, message):
        # 1. Focus the chat input and set text
        # Selector found: .aislash-editor-input (contenteditable div)
        js = f"""
        (function() {{
            const input = document.querySelector('.aislash-editor-input');
            if (input && input.offsetParent !== null) {{
                input.focus();
                // Direct DOM manipulation to clear
                input.textContent = '';
                document.execCommand('insertText', false, {json.dumps(message)});
                return true;
            }}
            return false;
        }})()
        """
        res = self.send_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
        typed = res.get('result', {}).get('value', False)
        
        if not typed:
            return {"success": False, "error": "Chat input not found"}
            
        time.sleep(0.5)
        # 2. Click Send button
        # Selector: .send-with-mode .anysphere-icon-button (usually has arrow icon)
        js_click = """
        (function() {
            const btnContainer = document.querySelector('.send-with-mode');
            if (btnContainer) {
                 const btn = btnContainer.querySelector('.anysphere-icon-button');
                 if (btn) {
                     btn.click();
                     return true;
                 }
            }
            // Fallback: look for codicon-arrow-up-two parent
            const arrow = document.querySelector('.codicon-arrow-up-two');
            if (arrow && arrow.parentElement) {
                arrow.parentElement.click();
                return true;
            }
            return false;
        })()
        """
        res_click = self.send_command("Runtime.evaluate", {"expression": js_click, "returnByValue": True})
        clicked = res_click.get('result', {}).get('value', False)
        
        if not clicked:
              return {"success": False, "error": "Send button not found"}
        
        return {"success": True, "message": message}

    def is_generating(self):
        """
        Checks if the agent is currently generating a response.
        Looks for 'Stop' buttons or indicators.
        """
        js = """
        (function() {
            // 1. Look for explicit 'Stop Generating' text
            const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
            const stopText = buttons.find(b => {
                const text = (b.innerText || b.title || "").toLowerCase();
                return text.includes('stop generating') || text === 'stop';
            });
            if (stopText && stopText.offsetParent !== null) return true;

            // 2. Look for Stop icons (codicon-debug-stop, etc.)
            const stopIcon = document.querySelector('.codicon-debug-stop, .codicon-stop-circle');
            if (stopIcon && stopIcon.offsetParent !== null) return true;

            // 3. Fallback: Check if Send button is hidden/replaced
            // This is heuristic: if we can't find the Send button but we know we are in a chat, we might be generating.
            // But relying on "Stop" presence is safer.
            
            return false;
        })()
        """
        res = self.send_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
        return res.get('result', {}).get('value', False)

    def wait_for_completion(self, timeout=300, interval=2):
        """
        Waits until is_generating() returns False.
        timeout: max seconds to wait (default 300s / 5 mins)
        """
        start_time = time.time()
        generating_seen = False
        
        while time.time() - start_time < timeout:
            gen = self.is_generating()
            
            if gen:
                generating_seen = True
            elif generating_seen:
                # We were generating, now we are not -> Done
                return {"success": True, "status": "completed"}
            else:
                # Haven't seen generation yet. Could be too fast or hasn't started.
                # If we've waited a bit (e.g. 5 sec) and still nothing, maybe it's done already or never started.
                if time.time() - start_time > 5:
                     return {"success": True, "status": "idle"}
            
            time.sleep(interval)
            
        return {"success": False, "error": "timeout"}

    def set_deep_mode_ui(self):
        """
        Automates the UI to set Default Approach to Deep.
        1. Open Settings (Ctrl+Shift+J)
        2. Click Agents
        3. Scroll down
        4. Select Deep
        5. Close tab
        """
        # 1. Open Settings (Ctrl+Shift+J)
        # J = 74
        self.log("Opening settings...")
        self.send_key('J', modifiers=8|2) # 8=Shift, 2=Ctrl
        
        time.sleep(2.0) # Wait for settings to open

        # 2. Click "Agents"
        # We need to find the "Agents" item in the sidebar/list.
        # Try multiple selectors and container constraints
        js_click_agents = """
        (function() {
            // Strategy 1: Look in settings TOC wrapper
            const userSettings = document.querySelector('.settings-toc-wrapper');
            if (userSettings) {
                const items = Array.from(userSettings.querySelectorAll('.monaco-list-row'));
                const agentsItem = items.find(el => el.innerText.includes('Agents') || el.title.includes('Agents'));
                if (agentsItem) {
                    agentsItem.click();
                    return {success: true, strategy: "toc"};
                }
            }

            // Strategy 2: Broad search for visible elements with exact text "Agents"
            const allItems = Array.from(document.querySelectorAll('.item-label, .monaco-list-row, span'));
            const exactItem = allItems.find(el => {
                return (el.innerText.trim() === 'Agents' || el.title === 'Agents') && el.offsetParent !== null;
            });
            
            if (exactItem) {
                exactItem.click();
                return {success: true, strategy: "exact_broad"};
            }

            return {success: false, reason: "Agents item not found"};
        })()
        """
        self.log("Clicking Agents...")
        # Retry loop for agents click (sometimes TOC loads slowly)
        for i in range(3):
            res_agents = self.send_command("Runtime.evaluate", {"expression": js_click_agents, "returnByValue": True})
            if res_agents.get('result', {}).get('value', {}).get('success'):
                self.log("Clicked Agents!")
                break
            time.sleep(1.0)
        
        time.sleep(1.0)
        
        # 3. Find "Default Approach" or the "Quick" dropdown
        # It seems the user said "click quick to open dropdown, clicks deep"
        # So we look for a button/element with text "Quick"
        
        js_switch_deep = """
        (function() {
            // Helper to wait/sleep matching Python speed
            
            // 1. Find "Quick" button (the dropdown trigger)
            // It might be a select-box or a tailored dropdown
            const buttons = Array.from(document.querySelectorAll('div[role="button"], .monaco-select-box'));
            const quickBtn = buttons.find(b => b.innerText.trim() === 'Quick' || b.innerText.includes('Quick'));
            
            if (!quickBtn) return {success: false, step: "find_quick"};
            
            quickBtn.click();
            
            // We can't wait in JS easily without async, so we return intermediate state or rely on python sleep
            // But let's assume we can trigger the dropdown now.
            return {success: true, step: "clicked_quick"};
        })()
        """
        
        self.log("Clicking 'Quick' dropdown...")
        res_quick = self.send_command("Runtime.evaluate", {"expression": js_switch_deep, "returnByValue": True})
        
        if not res_quick.get('result', {}).get('value', {}).get('success'):
            self.log("Could not find 'Quick' button. Maybe already Deep or scrolled out?")
            # Try scrolling down just in case
            self.send_command("Runtime.evaluate", {"expression": "document.querySelector('.settings-body, .monaco-scrollable-element').scrollTop = 1000;"})
            time.sleep(1.0)
            res_quick = self.send_command("Runtime.evaluate", {"expression": js_switch_deep, "returnByValue": True})
            
        time.sleep(1.0)
        
        # 4. Click "Deep" in the dropdown
        js_click_deep = """
        (function() {
            // The dropdown content usually appears in a separate layer or context view.
            // .monaco-list-row or .action-item
            const items = Array.from(document.querySelectorAll('.monaco-list-row, .action-item, .monaco-select-box-dropdown-container span'));
            const deepItem = items.find(el => el.innerText.trim() === 'Deep');
            
            if (deepItem) {
                deepItem.click();
                return {success: true};
            }
            return {success: false, reason: "Deep option not found"};
        })()
        """
        self.log("Clicking 'Deep'...")
        final_res = self.send_command("Runtime.evaluate", {"expression": js_click_deep, "returnByValue": True})
        
        time.sleep(1.0)
        
        # 5. Close Tab (Ctrl+W)
        self.log("Closing settings tab...")
        # W = 87
        self.send_key('W', modifiers=2) # Ctrl+W
        
        return final_res.get('result', {}).get('value', {})



