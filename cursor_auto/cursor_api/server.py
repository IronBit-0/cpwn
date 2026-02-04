from flask import Flask, jsonify, request
from cursor_controller import CursorController
import threading
import time
import os

app = Flask(__name__)
cursor = CursorController()

@app.route('/health', methods=['GET'])
def health():
    targets = cursor.get_targets()
    connected = cursor.connect()
    return jsonify({
        "status": "ok",
        "cursor_connected": connected,
        "targets_found": len(targets)
    })

@app.route('/login', methods=['GET'])
def login():
    res = cursor.click_login()
    return jsonify(res)

@app.route('/login-url', methods=['GET'])
def get_login_url():
    return jsonify(cursor.get_login_url())

@app.route('/continue', methods=['GET'])
def continue_action():
    res = cursor.click_continue()
    return jsonify(res)

@app.route('/eval', methods=['POST'])
def eval_expression():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    code = data.get("expression")
    if not code:
        return jsonify({"error": "No expression provided"}), 400
        
    res = cursor.send_command("Runtime.evaluate", {"expression": code})
    return jsonify(res)

@app.route('/login-url', methods=['GET'])
def login_url():
    try:
        if not os.path.exists('/tmp/cursor_login_url.txt'):
             return jsonify({"url": None})
             
        with open('/tmp/cursor_login_url.txt', 'r') as f:
            url = f.read().strip()
            return jsonify({"url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/conversations', methods=['GET'])
def list_conversations():
    try:
        convs = cursor.get_conversations()
        return jsonify({"conversations": convs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/conversations/<composer_id>', methods=['GET'])
def get_conversation(composer_id):
    try:
        content = cursor.get_conversation_content(composer_id)
        if content is None:
            return jsonify({"error": "Conversation not found"}), 404
        return jsonify(content)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/conversations/<composer_id>/render', methods=['GET'])
def render_conversation(composer_id):
    try:
        content = cursor.render_conversation_text(composer_id)
        return jsonify({"text": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/conversations/send', methods=['POST'])
def send_chat_message():
    try:
        data = request.get_json(force=True, silent=True) or {}
        message = data.get('message')
        if not message:
             return jsonify({"error": "Message required"}), 400
            
        res = cursor.send_chat_message(str(message))
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/conversations/new', methods=['POST'])
def new_conversation():
    try:
        res = cursor.new_conversation()
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/conversations/wait', methods=['POST'])
def wait_for_completion():
    # Polls until generation is complete
    return jsonify(cursor.wait_for_completion())

@app.route('/conversations/status', methods=['GET'])
def generation_status():
    # Immediate check
    gen = cursor.is_generating()
    return jsonify({
        "generating": gen,
        "status": "generating" if gen else "idle",
        "success": True
    })



@app.route('/sidebar/toggle', methods=['POST'])
def toggle_sidebar():
    try:
        data = request.get_json(force=True, silent=True) or {}
        target_state = data.get('open') # True, False, or None
        if target_state is not None:
            target_state = bool(target_state)
            
        res = cursor.toggle_sidebar(target_state)
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/model/change', methods=['POST'])
def change_model():
    try:
        data = request.get_json(force=True, silent=True) or {}
        model_name = data.get('name')
        if not model_name:
             return jsonify({"error": "Model name required"}), 400
            
        res = cursor.change_model(str(model_name))
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/sidebar/status', methods=['GET'])
def sidebar_status():
    try:
        is_open = cursor.is_sidebar_open()
        return jsonify({"open": is_open})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/set-deep-mode', methods=['POST', 'GET'])
def set_deep_mode_ui():
    try:
        res = cursor.set_deep_mode_ui()
        return jsonify(res)
    except Exception as e:
        # Log error but return 500
        print(f"Error setting deep mode: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Start in background thread to not block if needed, but here main is fine
    app.run(host='0.0.0.0', port=5000)
