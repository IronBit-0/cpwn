import http.server
import socketserver
import json
import urllib.request
import socket
import struct
import base64
import os
import time
import sys

PORT = 4020
PROXY_URL = "http://localhost:5555/rpc"

# --- CDP Helpers ---
def create_mask():
    return os.urandom(4)

def encode_frame(data, mask=True):
    frame = bytearray()
    frame.append(0x81) # Text
    length = len(data)
    b2 = 0x80 if mask else 0
    if length <= 125:
        b2 |= length
        frame.append(b2)
    elif length <= 65535:
        b2 |= 126
        frame.append(b2)
        frame.extend(struct.pack("!H", length))
    else:
        b2 |= 127
        frame.append(b2)
        frame.extend(struct.pack("!Q", length))
    if mask:
        masking_key = create_mask()
        frame.extend(masking_key)
        data_bytes = data.encode('utf-8')
        masked_data = bytearray(len(data_bytes))
        for i in range(len(data_bytes)):
            masked_data[i] = data_bytes[i] ^ masking_key[i % 4]
        frame.extend(masked_data)
    else:
        frame.extend(data.encode('utf-8'))
    return frame

def read_frame(sock):
    try:
        head = sock.recv(2)
        if not head: return None
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", sock.recv(8))[0]
        data = b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk: break
            data += chunk
        return data.decode('utf-8', errors='ignore')
    except:
        return None

def send_cdp_command(sock, method, params=None, await_result=True):
    msg_id = int(time.time() * 100000) % 1000000
    msg = {"id": msg_id, "method": method}
    if params:
        msg["params"] = params
    sock.send(encode_frame(json.dumps(msg)))
    
    if not await_result:
        return None

    start = time.time()
    while time.time() - start < 10:
        data = read_frame(sock)
        if data:
            try:
                resp = json.loads(data)
                if resp.get("id") == msg_id:
                    return resp
            except:
                pass
    return None

def get_page_targets():
    targets = []
    try:
        with urllib.request.urlopen("http://localhost:9222/json") as response:
            targets = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error getting targets: {e}")
        return []
    return [t for t in targets if t.get("type") == "page"]

def connect_to_target(t):
    target_ws = t.get("webSocketDebuggerUrl")
    if not target_ws: return None

    parts = target_ws.split('/')
    host = parts[2].split(':')[0]
    port = int(parts[2].split(':')[1])
    path = '/' + '/'.join(parts[3:])

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((host, port))
        key = base64.b64encode(os.urandom(16)).decode('utf-8')
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        s.send(req.encode())
        while b'\r\n\r\n' not in s.recv(4096): pass
        return s
    except Exception as e:
        print(f"Socket error: {e}")
        return None

def click_node_id(sock, node_id):
    res = send_cdp_command(sock, "DOM.getBoxModel", {"nodeId": node_id})
    if not res or 'result' not in res or 'model' not in res['result']:
        print(f"Could not get box model for nodeId {node_id}.")
        return False
        
    quad = res['result']['model']['content']
    x = (quad[0] + quad[2] + quad[4] + quad[6]) / 4
    y = (quad[1] + quad[3] + quad[5] + quad[7]) / 4
    
    print(f"Clicking nodeId {node_id} at {x}, {y}")
    
    send_cdp_command(sock, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    time.sleep(0.05)
    send_cdp_command(sock, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return True

def get_node_by_text(root, text, tag_filter=None):
    q = [(root, None)]
    text_lower = text.lower()
    index = 0
    while index < len(q):
        node, parent = q[index]
        index += 1
        
        attrs = node.get("attributes", [])
        attr_dict = {}
        for i in range(0, len(attrs), 2):
            attr_dict[attrs[i]] = attrs[i+1]
        
        if node.get("nodeType") == 3: # Text
            val = node.get("nodeValue", "")
            if text_lower in val.lower():
                 return node, parent
        
        children = node.get("children", [])
        for child in children:
            q.append((child, node))
        shadows = node.get("shadowRoots", [])
        for shadow in shadows:
            q.append((shadow, node))
        content_doc = node.get("contentDocument")
        if content_doc:
            q.append((content_doc, node))
    return None, None

def get_node_by_attr_includes(root, attr_name, attr_value_part):
     q = [root]
     attr_value_part = attr_value_part.lower()
     index = 0
     while index < len(q):
        node = q[index]
        index += 1
        attrs = node.get("attributes", [])
        found_id_match = False
        for i in range(0, len(attrs), 2):
            name = attrs[i]
            val = attrs[i+1]
            if name == attr_name and attr_value_part in val.lower():
                return node
        children = node.get("children", [])
        for child in children:
            q.append(child)
        shadows = node.get("shadowRoots", [])
        for shadow in shadows:
            q.append(shadow)
        content_doc = node.get("contentDocument")
        if content_doc:
            q.append(content_doc)
     return None

def find_and_interact(text_to_type):
    page_targets = get_page_targets()
    for t in page_targets:
        print(f"Trying target: {t.get('title')}")
        s = connect_to_target(t)
        if not s: continue
        res = send_cdp_command(s, "DOM.getDocument", {"depth": -1, "pierce": True})
        if not res or 'result' not in res:
            s.close()
            continue
        root = res['result']['root']
        editor_node = get_node_by_attr_includes(root, "data-lexical-editor", "true")
        if editor_node:
             print("Editor found via CDP.")
             click_node_id(s, editor_node['nodeId'])
             print(f"Inserting text: {text_to_type}")
             send_cdp_command(s, "Input.insertText", {"text": text_to_type})
             time.sleep(1.0)
             submit_node, submit_parent = get_node_by_text(root, "Submit")
             clicked = False
             if submit_node and submit_parent:
                  print(f"Submit text found. Clicking parent {submit_parent['nodeId']}...")
                  clicked = click_node_id(s, submit_parent['nodeId'])
             if not clicked:
                  print("Submit click failed or not found. Dispatching Enter...")
                  send_cdp_command(s, "Input.dispatchKeyEvent", {"type": "rawKeyDown", "windowsVirtualKeyCode": 13, "code": "Enter", "key": "Enter", "text": "\r", "unmodifiedText": "\r"})
                  send_cdp_command(s, "Input.dispatchKeyEvent", {"type": "char", "text": "\r"})
                  send_cdp_command(s, "Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13, "code": "Enter", "key": "Enter"})
             s.close()
             return True
        s.close()
    return False

def find_and_select_model(model_name):
    page_targets = get_page_targets()
    for t in page_targets:
        print(f"Trying target (model): {t.get('title')}")
        s = connect_to_target(t)
        if not s: continue
        res = send_cdp_command(s, "DOM.getDocument", {"depth": -1, "pierce": True})
        if not res or 'result' not in res:
            s.close()
            continue
        root = res['result']['root']
        print(f"Looking for dropdown button...")
        btn_node = get_node_by_attr_includes(root, "id", "headlessui-popover-button")
        if btn_node:
             print(f"Dropdown button found (NodeId: {btn_node['nodeId']}). Clicking...")
             if click_node_id(s, btn_node['nodeId']):
                 time.sleep(1.0)
                 res = send_cdp_command(s, "DOM.getDocument", {"depth": -1, "pierce": True})
                 root = res['result']['root']
                 print(f"Searching for model text: {model_name}")
                 text_node, parent_node = get_node_by_text(root, model_name)
                 if text_node and parent_node:
                     print(f"Model text found (Parent NodeId: {parent_node['nodeId']}). Clicking parent...")
                     if click_node_id(s, parent_node['nodeId']):
                         print("Model clicked.")
                         s.close()
                         return True
                     else:
                         print("Failed to click model parent.")
                 else:
                     print("Model text not found.")
        else:
             print("Dropdown button not found.")
        s.close()
    return False

# --- Proxy Helpers ---
def call_proxy(method, request_class, payload):
    req_body = {
        "method": method,
        "requestClass": request_class,
        "payload": payload
    }
    data = json.dumps(req_body).encode('utf-8')
    req = urllib.request.Request(PROXY_URL, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode())
    except Exception as e:
        print(f"Proxy call failed: {e}")
        return 500, str(e)

class PromptHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/conversations':
            status, resp = call_proxy("getAllCascadeTrajectories", "GetAllCascadeTrajectoriesRequest", {})
            if status == 200 and isinstance(resp, dict):
                # Extract IDs and names (summary)
                summaries = resp.get("trajectorySummaries", {})
                conversations = []
                for k, v in summaries.items():
                    conversations.append({
                        "id": k,
                        "name": v.get("summary", "Untitled")
                    })
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(conversations).encode('utf-8'))
            else:
                self.send_response(status)
                self.end_headers()
                self.wfile.write(str(resp).encode('utf-8'))
        
        elif self.path.startswith('/conversation/'):
            cascade_id = self.path.split('/')[-1]
            if not cascade_id:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing cascade ID")
                return
            
            status, resp = call_proxy("getCascadeTrajectory", "GetCascadeTrajectoryRequest", {"cascadeId": cascade_id})
            self.send_response(status)
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode('utf-8'))
            
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        if self.path == '/prompt':
            text = data.get('text', '')
            if not text:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing 'text' field")
                return

            print(f"Received prompt: {text}")
            success = find_and_interact(text)
            
            if success:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Prompt submitted")
            else:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to locate or interact with prompt box")
        
        elif self.path == '/model':
            model = data.get('model', '')
            if not model:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing 'model' field")
                return

            print(f"Received model request: {model}")
            success = find_and_select_model(model)
            
            if success:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Model selected")
            else:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to locate model dropdown or option")
        
        else:
            self.send_response(404)
            self.end_headers()

class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    with ReuseAddrTCPServer(("", PORT), PromptHandler) as httpd:
        print(f"Server serving at port {PORT}")
        httpd.serve_forever()
