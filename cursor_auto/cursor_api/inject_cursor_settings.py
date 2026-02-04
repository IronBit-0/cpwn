import sqlite3
import json
import os
import sys

# Constants
DB_PATH = os.getenv("CURSOR_DB_PATH", "/root/.config/cursor-data/User/globalStorage/state.vscdb")
KEY_APP_USER = "src.vs.platform.reactivestorage.browser.reactiveStorageServiceImpl.persistentStorage.applicationUser"

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
    return conn

def read_json_from_db(cursor, key):
    try:
        cursor.execute("SELECT value FROM ItemTable WHERE key=?", (key,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
    except Exception as e:
        print(f"Error reading {key}: {e}")
    return {}

def write_json_to_db(cursor, key, data):
    try:
        json_str = json.dumps(data)
        cursor.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", (key, json_str))
        print(f"Updated {key}")
    except Exception as e:
        print(f"Error writing {key}: {e}")

def update_app_user_settings(data):
    """
    Updates the main application user settings.
    Only enabling Yolo mode and ensuring Agent exists with AutoRun.
    REMOVED: Explicit Deep mode forcing.
    """
    changed = False

    # 1. Ensure global composer state exists
    if "composerState" not in data:
        data["composerState"] = {}
    
    comp_state = data["composerState"]
    
    # 2. Enable "Yolo" mode (Run Everything)
    if not comp_state.get("yoloEnableRunEverything"):
        comp_state["yoloEnableRunEverything"] = True
        changed = True

    # 3. Configure Agent Mode (Generic AutoRun)
    modes = comp_state.get("modes4", [])
    agent_mode = next((m for m in modes if m.get("id") == "agent"), None)
    
    if not agent_mode:
        # Create default agent mode if missing
        agent_mode = {
            "id": "agent",
            "name": "Agent",
            "autoRun": True,
            "fullAutoRun": True,
            "enabledTools": [],
            "enabledMcpServers": []
        }
        modes.append(agent_mode)
        comp_state["modes4"] = modes
        changed = True
    else:
        # Update existing
        if not agent_mode.get("fullAutoRun") or not agent_mode.get("autoRun"):
            agent_mode["fullAutoRun"] = True
            agent_mode["autoRun"] = True
            changed = True

    return changed

def main():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Update Application User Settings
        app_user_data = read_json_from_db(cursor, KEY_APP_USER)
        if update_app_user_settings(app_user_data):
            write_json_to_db(cursor, KEY_APP_USER, app_user_data)
        else:
            print("App user settings already up to date.")

        conn.commit()
        print("Settings injection completed successfully.")

    except Exception as e:
        print(f"Fatal error during injection: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
