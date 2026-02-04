import sqlite3
import json
import os
import secrets
import shutil

# Default paths in the container
GLOBAL_DB_PATH = "/root/.config/cursor-data/User/globalStorage/state.vscdb"
WORKSPACE_BASE_PATH = "/root/.config/cursor-data/User/workspaceStorage"

def get_latest_workspace_db():
    try:
        if not os.path.exists(WORKSPACE_BASE_PATH):
            return None
        workspaces = [os.path.join(WORKSPACE_BASE_PATH, d) for d in os.listdir(WORKSPACE_BASE_PATH)]
        if not workspaces:
            return None
        latest = max(workspaces, key=os.path.getmtime)
        return os.path.join(latest, "state.vscdb")
    except:
        return None

def scan_global_bubbles(print_output=True):
    """
    Scans the global DB for bubbles and prints partial content.
    Useful for debugging.
    """
    if not os.path.exists(GLOBAL_DB_PATH):
        if print_output: print("Global DB not found.")
        return

    # Copy to temp
    temp_db = f"/tmp/debug_global_{secrets.token_hex(4)}.vscdb"
    try:
        shutil.copy2(GLOBAL_DB_PATH, temp_db)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM cursorDiskKV WHERE key LIKE 'bubbleId:%'")
        rows = cursor.fetchall()
        
        if print_output: print(f"Found {len(rows)} bubbles in Global DB.")
        
        results = []
        for key, val in rows:
            try:
                data = json.loads(val)
                text = data.get('text', '')[:50]
                has_tools = data.get('toolResults')
                has_caps = data.get('capabilities')
                has_thinking = data.get('allThinkingBlocks')
                
                # Filter for interesting ones
                if has_tools or has_caps or has_thinking or "directory" in text:
                    item = {
                        "key": key,
                        "text_snippet": text,
                        "has_tools": bool(has_tools),
                        "has_thinking": bool(has_thinking)
                    }
                    results.append(item)
                    
                    if print_output:
                        print(f"\nKey: {key}")
                        print(f"Text: {text}...")
                        if has_tools:
                            print(f"Tool Results: {json.dumps(has_tools, indent=2)}")
                        if has_caps:
                            print(f"Capabilities: {json.dumps(has_caps, indent=2)}")
                        if has_thinking:
                            print(f"Thinking: {json.dumps(has_thinking, indent=2)}")
            except:
                pass
        
        conn.close()
        return results

    except Exception as e:
        if print_output: print(f"Error scanning DB: {e}")
        return []
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)

if __name__ == "__main__":
    scan_global_bubbles()
