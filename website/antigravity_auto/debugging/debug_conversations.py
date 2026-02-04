import urllib.request
import json

def debug_conversations():
    url = "http://localhost:4020/conversations" 
    # Wait, I want to query the PROXY directly to see the raw data, 
    # OR modify the server to dump it. 
    # Since I can't easily reach port 5555 from host (only mapped 6080, 5000, 4020),
    # I will run this script INSIDE the container.
    
    proxy_url = "http://localhost:5555/rpc"
    req_body = {
        "method": "getAllCascadeTrajectories",
        "requestClass": "GetAllCascadeTrajectoriesRequest",
        "payload": {}
    }
    data = json.dumps(req_body).encode('utf-8')
    req = urllib.request.Request(proxy_url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read().decode()
            print(raw)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_conversations()
