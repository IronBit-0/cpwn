import requests
import time
import json
import os

API_BASE = "http://localhost:5000"
GROQ_API_KEY_FILE = "api_key"

def read_file(path):
    with open(path, 'r') as f:
        return f.read().strip()

def get_groq_key():
    return read_file(GROQ_API_KEY_FILE)

def api_post(endpoint, data=None):
    url = f"{API_BASE}{endpoint}"
    headers = {"Content-Type": "application/json"}
    try:
        if data:
            resp = requests.post(url, json=data, headers=headers)
        else:
            resp = requests.post(url, headers=headers)
        return resp.json()
    except Exception as e:
        print(f"Error calling {endpoint}: {e}")
        return {}

def api_get(endpoint):
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.get(url)
        return resp.json()
    except Exception as e:
        print(f"Error calling {endpoint}: {e}")
        return {}

def main():
    print(">>> 1. Clicking Login...")
    # Using existing endpoint or direct click via controller if exposed?
    # server.py exposes /login which calls cursor.click_login()
    try:
        res = requests.get(f"{API_BASE}/login").json()
        print(f"Login click result: {res}")
    except Exception as e:
        print(f"Login failed: {e}")

    print("\n>>> 2. Please Login manually interactively.")
    print("Fetching Login URL...")
    time.sleep(2) # Wait for file to be written
    try:
        url_res = requests.get(f"{API_BASE}/login-url").json()
        if url_res.get("success"):
            print(f"LOGIN URL: {url_res.get('url')}")
            print("(Open this URL in your browser to log in)")
        else:
             print("Login URL not found yet. Please check container logs if needed.")
    except Exception as e:
        print(f"Error fetching URL: {e}")

    input("Press Enter after you have successfully logged in...")

    print("\n>>> 3. Pressing Continue (x2)...")
    requests.get(f"{API_BASE}/continue")
    time.sleep(2)
    requests.get(f"{API_BASE}/continue")
    time.sleep(2)

    print("\n>>> 4. Toggling Sidebar...")
    api_post("/sidebar/toggle")
    time.sleep(1)

    print("\n>>> 5. Starting New Conversation...")
    api_post("/conversations/new")
    time.sleep(2)

    print("\n>>> 6. Changing Model to 'Sonnet 4.5'...")
    # User requested literal "Sonnet 4.5"
    api_post("/model/change", {"name": "Sonnet 4.5"})
    time.sleep(1)

    print("\n>>> 7. Entering Prompt from prompt.txt...")
    prompt_text = read_file("prompt.txt")
    print(f"Prompt: {prompt_text[:50]}...")
    api_post("/conversations/send", {"message": prompt_text})

    print("\n>>> 8. Waiting for completion...")
    while True:
        status = api_get("/conversations/status")
        if status.get("status") == "idle" and not status.get("generating"):
            print("Generation Complete.")
            break
        print("Agent is generating...", end="\r")
        time.sleep(2)

    print("\n>>> 9. Finding Conversation with largest Context Usage...")
    # Wait a moment for backend to sync
    time.sleep(2)
    conv_data = api_get("/conversations")
    conversations = conv_data.get("conversations", [])
    
    if not conversations:
        print("No conversations found!")
        return

    # Find largest contextUsagePercent or fallback to message count/length
    # Inspecting structure: we assume contextUsagePercent exists or we calculate
    # Based on previous implementation, we might not have exposed contextUsagePercent in /backend/conversations
    # Let's try to find it, otherwise rely on openning the most recent one (since we just created it)
    
    target_conv = None
    max_usage = -1
    
    # If user creates new conversation, it is usually first or last depending on sort
    # Recent createdAt is safest if usage stats aren't exposed
    # But user specifically asked for "largest contextUsagePercent"
    
    # Let's look for the key
    for c in conversations:
        usage = c.get("contextUsagePercent", 0)
        if usage > max_usage:
            max_usage = usage
            target_conv = c
            
    # Fallback: if all 0 (maybe not calculated yet), take the one we just made (newest)
    if max_usage <= 0:
        print("Context usage not found or 0, selecting newest conversation...")
        target_conv = max(conversations, key=lambda x: x.get("createdAt", 0))
    
    if not target_conv:
        print("Could not find target conversation.")
        return

    composer_id = target_conv.get("composerId")
    print(f"Selected Conversation: {composer_id} (Usage: {max_usage}%)")

    print("\n>>> 10. Getting content...")
    # Use new render endpoint to get formatted text with thinking/tools
    render_data = api_get(f"/conversations/{composer_id}/render")
    rendered_text = render_data.get("text", "")
    
    if not rendered_text:
        print("No content returned.")
        sys.exit(1)
        
    print(rendered_text)
    
    # Heuristic for flag extraction: Use raw content to find last assistant text
    # But for visual confirmation, rendered_text is what we wanted.
    
    # We still need the last text message for Groq.
    # We can call the raw endpoint again or just rely on visual output for now.
    # The prompt sends "last message content", let's quickly get raw for that.
    content_data = api_get(f"/conversations/{composer_id}")
    messages = content_data.get("messages", [])
    last_text = ""
    for msg in messages:
         if msg.get("text"):
             last_text = msg.get("text")

    print("\n>>> 11. Asking Groq to check for flag...")
    if not os.path.exists(GROQ_API_KEY_FILE):
        print(f"Error: {GROQ_API_KEY_FILE} not found.")
        return

    groq_key = get_groq_key()
    
    # Groq API Call
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    
    # Constructing the query
    payload = {
        "model": "qwen/qwen3-32b",
        "messages": [
            {
                "role": "system",
                "content": "You are a helper. Check if the provided text contains a 'flag' or 'key' (usually in format flag{...} or similar). If it does, output ONLY the key. If not, output 'NO'."
            },
            {
                "role": "user",
                "content": f"Does this output contain a key?\n\n{last_text}"
            }
        ],
        "temperature": 0
    }
    
    try:
        resp = requests.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            result = resp.json()
            answer = result['choices'][0]['message']['content'].strip()
            
            if answer == "NO":
                print("Groq analysis: No key found. Quitting.")
            else:
                print(f"\n[SUCCESS] Key Found: {answer}")
        else:
            print(f"Groq API Error: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Groq Request Failed: {e}")

if __name__ == "__main__":
    main()
