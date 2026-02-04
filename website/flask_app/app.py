import os
import stat
import shutil
import docker
import requests
import time
from flask import Flask, render_template, request, jsonify, redirect, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', '/app/uploads')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload
app.config['ACCOUNTS_FOLDER'] = os.environ.get('ACCOUNTS_FOLDER', '/accounts')
app.config['ANTIGRAVITY_AUTO_PATH'] = os.environ.get('ANTIGRAVITY_AUTO_PATH', '/antigravity_auto')
app.config['CONTAINER_DATA_PATH'] = os.environ.get('CONTAINER_DATA_PATH', '/app/container_data')
# Host paths for Docker volume mounts (when running in Docker, need host paths for sibling containers)
app.config['HOST_CONTAINER_DATA_PATH'] = os.environ.get('HOST_CONTAINER_DATA_PATH', '/app/container_data')
app.config['HOST_ACCOUNTS_PATH'] = os.environ.get('HOST_ACCOUNTS_PATH', '/accounts')
# Docker host for accessing sibling containers' published ports
app.config['DOCKER_HOST'] = os.environ.get('DOCKER_HOST_ADDRESS', 'host.docker.internal')

NETWORK_NAME = 'boxnet'
NETWORK_SUBNET = '10.4.4.0/24'
NETWORK_GATEWAY = '10.4.4.1'
CONTAINER_PREFIX = 'antibox_'

AVAILABLE_MODELS = [
    "Gemini Pro 3 (High)",
    "Gemini Pro 3 (Low)",
    "Gemini 3 Flash",
    "Claude Sonnet 4.5",
    "Claude Sonnet 4.5 (Thinking)",
    "Claude Opus 4.5 (Thinking)",
    "GPT-OSS 120B (Medium)",
]

def get_docker_client():
    return docker.from_env()

def ensure_network_exists():
    """Ensure the boxnet network exists with the correct subnet."""
    client = get_docker_client()
    try:
        network = client.networks.get(NETWORK_NAME)
        # Check if subnet is correct
        network_config = network.attrs.get('IPAM', {}).get('Config', [])
        if network_config and network_config[0].get('Subnet') != NETWORK_SUBNET:
            # Wrong subnet, recreate
            network.remove()
            raise docker.errors.NotFound("Recreating network")
        return network
    except docker.errors.NotFound:
        # Create network with specific subnet
        ipam_pool = docker.types.IPAMPool(subnet=NETWORK_SUBNET, gateway=NETWORK_GATEWAY)
        ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])
        return client.networks.create(NETWORK_NAME, driver='bridge', ipam=ipam_config)

def get_accounts():
    """Get list of account folders."""
    accounts_path = app.config['ACCOUNTS_FOLDER']
    if not os.path.exists(accounts_path):
        return []
    return [d for d in os.listdir(accounts_path)
            if os.path.isdir(os.path.join(accounts_path, d))]

def get_next_container_number():
    """Get the next available container number."""
    client = get_docker_client()
    containers = client.containers.list(all=True)
    existing_numbers = []
    for container in containers:
        if container.name.startswith(CONTAINER_PREFIX):
            try:
                num = int(container.name.replace(CONTAINER_PREFIX, ''))
                existing_numbers.append(num)
            except ValueError:
                pass
    if not existing_numbers:
        return 1
    return max(existing_numbers) + 1

def get_deployed_containers():
    """Get list of all deployed antibox containers."""
    client = get_docker_client()
    containers = client.containers.list(all=True)
    antibox_containers = []
    for container in containers:
        if container.name.startswith(CONTAINER_PREFIX):
            # Get container IP
            ip_address = None
            try:
                networks = container.attrs['NetworkSettings']['Networks']
                if NETWORK_NAME in networks:
                    ip_address = networks[NETWORK_NAME]['IPAddress']
            except (KeyError, TypeError):
                pass

            # Get port mappings
            ports = {}
            try:
                port_bindings = container.attrs['NetworkSettings']['Ports']
                for internal, bindings in (port_bindings or {}).items():
                    if bindings:
                        ports[internal] = bindings[0]['HostPort']
            except (KeyError, TypeError):
                pass

            # Read nickname from metadata
            import json
            nickname = container.name
            container_data_path = os.path.join(app.config['CONTAINER_DATA_PATH'], container.name)
            metadata_file = os.path.join(container_data_path, 'metadata.json')
            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        nickname = metadata.get('nickname', container.name)
                except:
                    pass

            antibox_containers.append({
                'name': container.name,
                'display_name': nickname,
                'id': container.short_id,
                'status': container.status,
                'ip_address': ip_address,
                'ports': ports,
                'novnc_port': ports.get('6080/tcp'),
                'api_port': ports.get('4020/tcp')
            })

    # Sort by container number
    antibox_containers.sort(key=lambda x: int(x['name'].replace(CONTAINER_PREFIX, '')))
    return antibox_containers

def find_available_port(start_port, count=3):
    """Find a set of consecutive available ports."""
    import socket
    client = get_docker_client()
    containers = client.containers.list(all=True)

    # Collect all used ports
    used_ports = set()
    for container in containers:
        try:
            port_bindings = container.attrs['NetworkSettings']['Ports']
            for internal, bindings in (port_bindings or {}).items():
                if bindings:
                    used_ports.add(int(bindings[0]['HostPort']))
        except (KeyError, TypeError, ValueError):
            pass

    port = start_port
    while port < 65535:
        # Check if this port and next (count-1) ports are available
        ports_available = True
        for i in range(count):
            if (port + i) in used_ports:
                ports_available = False
                break
            # Also check if port is in use by system
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    result = s.connect_ex(('127.0.0.1', port + i))
                    if result == 0:
                        ports_available = False
                        break
            except:
                pass

        if ports_available:
            return port
        port += count

    raise Exception("No available ports found")

@app.route('/')
def index():
    return redirect(url_for('deploy'))

@app.route('/deploy', methods=['GET', 'POST'])
def deploy():
    if request.method == 'POST':
        # Get form data
        account = request.form.get('account')
        model = request.form.get('model', 'Gemini Pro 3 High')
        nickname = request.form.get('nickname', '')
        flag_detection = request.form.get('flag_detection', 'off') == 'on'
        challenge_description = request.form.get('challenge_description', '')

        # Handle file uploads
        files = request.files.getlist('files')

        # Validate
        if not account:
            return jsonify({'error': 'Please select an account'}), 400

        try:
            result = deploy_container(account, model, nickname, flag_detection, challenge_description, files)
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # GET request - show deploy form
    accounts = get_accounts()
    return render_template('deploy.html', accounts=accounts, models=AVAILABLE_MODELS)

def deploy_container(account, model, nickname, flag_detection, challenge_description, files):
    """Deploy a new antibox container."""
    client = get_docker_client()

    # Ensure network exists
    ensure_network_exists()

    # Get next container number and name
    container_num = get_next_container_number()
    container_name = f"{CONTAINER_PREFIX}{container_num}"

    # Find available ports (need 3: 6080, 5000, 4020)
    base_port = find_available_port(6080 + (container_num - 1) * 10, 3)
    port_6080 = base_port
    port_5000 = base_port + 1
    port_4020 = base_port + 2

    # Create temporary directories for this container
    # Local paths (inside this container, for file operations)
    container_data_path = os.path.join(app.config['CONTAINER_DATA_PATH'], container_name)
    chal_path = os.path.join(container_data_path, 'chal')
    antigravity_data_path = os.path.join(container_data_path, 'antigravity-data')

    # Host paths (for Docker volume mounts on sibling containers)
    host_container_data_path = os.path.join(app.config['HOST_CONTAINER_DATA_PATH'], container_name)
    host_chal_path = os.path.join(host_container_data_path, 'chal')
    host_antigravity_data_path = os.path.join(host_container_data_path, 'antigravity-data')

    # Clean up if exists
    if os.path.exists(container_data_path):
        shutil.rmtree(container_data_path)

    os.makedirs(chal_path, exist_ok=True)
    os.makedirs(antigravity_data_path, exist_ok=True)

    # Save container metadata (nickname, etc.)
    import json
    metadata = {
        'nickname': nickname or container_name,
        'account': account,
        'model': model,
        'flag_detection': flag_detection
    }
    with open(os.path.join(container_data_path, 'metadata.json'), 'w') as f:
        json.dump(metadata, f)

    # Copy account data to antigravity-data (skip socket files and other special files)
    def ignore_special_files(directory, files):
        ignored = []
        for f in files:
            filepath = os.path.join(directory, f)
            # Skip socket files, pipes, and device files
            if os.path.exists(filepath):
                try:
                    mode = os.stat(filepath).st_mode
                    if stat.S_ISSOCK(mode) or stat.S_ISFIFO(mode) or stat.S_ISBLK(mode) or stat.S_ISCHR(mode):
                        ignored.append(f)
                except (OSError, IOError):
                    ignored.append(f)
        return ignored

    account_source = os.path.join(app.config['ACCOUNTS_FOLDER'], account)
    if os.path.exists(account_source):
        shutil.copytree(account_source, antigravity_data_path, dirs_exist_ok=True, ignore=ignore_special_files)

    # Save uploaded files to chal directory
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(chal_path, filename))

    # Build the image if not exists
    image_name = 'antigravity_auto'
    try:
        client.images.get(image_name)
    except docker.errors.ImageNotFound:
        # Build from antigravity_auto directory
        print(f"Building image {image_name}...")
        client.images.build(
            path=app.config['ANTIGRAVITY_AUTO_PATH'],
            tag=image_name,
            rm=True
        )

    # Calculate IP address for this container
    ip_address = f"10.4.4.{container_num + 1}"

    # Create and start container (use host paths for volumes so sibling containers can access)
    container = client.containers.run(
        image_name,
        name=container_name,
        hostname=container_name,
        detach=True,
        ports={
            '6080/tcp': port_6080,
            '5000/tcp': port_5000,
            '4020/tcp': port_4020
        },
        volumes={
            host_chal_path: {'bind': '/home/chal', 'mode': 'rw'},
            host_antigravity_data_path: {'bind': '/root/.config/antigravity-data', 'mode': 'rw'}
        },
        environment={
            'VNC_RESOLUTION': '1280x800'
        },
        shm_size='2g',
        network=NETWORK_NAME
    )

    # Start background initialization (model change, prompt) so deploy returns immediately
    import threading
    def background_init():
        docker_host = app.config['DOCKER_HOST']
        api_url = f"http://{docker_host}:{port_4020}"
        
        # Wait for API to be available
        max_retries = 60
        for i in range(max_retries):
            try:
                response = requests.get(f"{api_url}/conversations", timeout=2)
                if response.status_code in [200, 500]:  # API is up
                    break
            except requests.exceptions.RequestException:
                pass
            time.sleep(2)
        
        # Wait additional time for the Antigravity extension to fully initialize
        time.sleep(15)
        
        # Change model if not default
        if model != "Gemini Pro 3 (High)":
            try:
                requests.post(
                    f"{api_url}/model",
                    json={'model': model},
                    timeout=30
                )
            except requests.exceptions.RequestException as e:
                print(f"Warning: Failed to set model: {e}")
        
        # Send challenge description as prompt
        if challenge_description:
            try:
                requests.post(
                    f"{api_url}/prompt",
                    json={'text': challenge_description},
                    timeout=30
                )
            except requests.exceptions.RequestException as e:
                print(f"Warning: Failed to send prompt: {e}")
    
    threading.Thread(target=background_init, daemon=True).start()

    return {
        'success': True,
        'container_name': container_name,
        'container_id': container.short_id,
        'ip_address': ip_address,
        'ports': {
            'novnc': port_6080,
            'api': port_4020,
            'reserved': port_5000
        }
    }

@app.route('/monitor')
def monitor():
    containers = get_deployed_containers()
    return render_template('monitor.html', containers=containers)

@app.route('/api/containers')
def api_containers():
    """Get list of deployed containers."""
    return jsonify(get_deployed_containers())

@app.route('/api/containers/status')
def api_containers_status():
    """Get status of all containers including conversation completion state."""
    containers = get_deployed_containers()
    docker_host = app.config['DOCKER_HOST']
    result = []
    
    for container in containers:
        container_info = {
            'name': container['name'],
            'status': container['status'],
            'conversations': []
        }
        
        if container['status'] == 'running' and container.get('api_port'):
            try:
                # Get conversations list
                response = requests.get(
                    f"http://{docker_host}:{container['api_port']}/conversations",
                    timeout=5
                )
                if response.status_code == 200 and response.text:
                    conversations = response.json()
                    for conv in conversations:
                        conv_status = {'id': conv.get('id'), 'name': conv.get('name', ''), 'completed': False}
                        # Get individual conversation status
                        try:
                            conv_response = requests.get(
                                f"http://{docker_host}:{container['api_port']}/conversation/{conv['id']}",
                                timeout=5
                            )
                            if conv_response.status_code == 200:
                                conv_data = conv_response.json()
                                status = conv_data.get('status', '')
                                conv_status['completed'] = status == 'CASCADE_RUN_STATUS_IDLE'
                                conv_status['run_status'] = status
                        except:
                            pass
                        container_info['conversations'].append(conv_status)
            except:
                pass
        
        result.append(container_info)
    
    return jsonify(result)

@app.route('/api/container/<container_name>/conversations')
def api_conversations(container_name):
    """Get conversations for a specific container."""
    containers = get_deployed_containers()
    container = next((c for c in containers if c['name'] == container_name), None)

    if not container:
        return jsonify({'error': 'Container not found'}), 404

    if container['status'] != 'running':
        return jsonify({'error': 'Container is not running'}), 400

    api_port = container.get('api_port')
    if not api_port:
        return jsonify({'error': 'API port not found'}), 400

    try:
        docker_host = app.config['DOCKER_HOST']
        response = requests.get(
            f"http://{docker_host}:{api_port}/conversations",
            timeout=10
        )
        if response.status_code != 200:
            return jsonify({'error': f'API returned status {response.status_code}: {response.text[:200]}'}), response.status_code
        if not response.text:
            return jsonify([])  # Return empty array if no content
        try:
            return jsonify(response.json())
        except ValueError as e:
            return jsonify({'error': f'Invalid JSON response: {response.text[:200]}'}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/container/<container_name>/conversation/<cascade_id>')
def api_conversation_detail(container_name, cascade_id):
    """Get conversation details for a specific container."""
    containers = get_deployed_containers()
    container = next((c for c in containers if c['name'] == container_name), None)

    if not container:
        return jsonify({'error': 'Container not found'}), 404

    if container['status'] != 'running':
        return jsonify({'error': 'Container is not running'}), 400

    api_port = container.get('api_port')
    if not api_port:
        return jsonify({'error': 'API port not found'}), 400

    try:
        docker_host = app.config['DOCKER_HOST']
        response = requests.get(
            f"http://{docker_host}:{api_port}/conversation/{cascade_id}",
            timeout=10
        )
        if response.status_code != 200:
            return jsonify({'error': f'API returned status {response.status_code}: {response.text[:200]}'}), response.status_code
        if not response.text:
            return jsonify({'error': 'Empty response from API'}), 500
        try:
            return jsonify(response.json())
        except ValueError as e:
            return jsonify({'error': f'Invalid JSON response: {response.text[:200]}'}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/container/<container_name>/delete', methods=['POST'])
def api_delete_container(container_name):
    """Delete a specific container."""
    client = get_docker_client()

    try:
        container = client.containers.get(container_name)
        container.stop()
        container.remove()

        # Also clean up the data directory
        container_data_path = os.path.join(app.config['CONTAINER_DATA_PATH'], container_name)
        if os.path.exists(container_data_path):
            shutil.rmtree(container_data_path)

        return jsonify({'success': True})
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============== FLAGS FUNCTIONALITY ==============

FLAGS_FILE = os.path.join(os.path.dirname(__file__), 'flags.json')

def get_groq_key():
    """Read Groq API key from file."""
    key_file = os.path.join(os.path.dirname(__file__), 'groq_key.txt')
    if os.path.exists(key_file):
        with open(key_file, 'r') as f:
            return f.read().strip()
    return None

def load_flags():
    """Load flags from storage."""
    if os.path.exists(FLAGS_FILE):
        with open(FLAGS_FILE, 'r') as f:
            import json
            return json.load(f)
    return []

def save_flag(container_name, display_name, flag):
    """Save a found flag to storage."""
    import json
    from datetime import datetime
    flags = load_flags()
    flags.append({
        'container_name': container_name,
        'display_name': display_name,
        'flag': flag,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    with open(FLAGS_FILE, 'w') as f:
        json.dump(flags, f, indent=2)

def extract_flag_with_groq(text):
    """Use Groq API to extract flag from text."""
    groq_key = get_groq_key()
    if not groq_key:
        return None
    
    try:
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {groq_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'llama-3.3-70b-versatile',
                'messages': [
                    {
                        'role': 'system',
                        'content': 'You are a CTF flag extractor. Analyze the given text and determine if it contains a CTF flag. CTF flags usually look like: flag{...}, FLAG{...}, CTF{...}, or similar formats with braces. If you find a flag, respond with ONLY the flag itself (e.g., "flag{example}"). If no flag is found, respond with exactly "NO_FLAG_FOUND". Do not include any other text or explanation.'
                    },
                    {
                        'role': 'user',
                        'content': f'Extract the CTF flag from this text if present:\n\n{text[-8000:]}'  # Limit to last 8000 chars
                    }
                ],
                'temperature': 0.1,
                'max_tokens': 200
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            # Clean up any thinking tags that qwen might add
            if '</think>' in answer:
                answer = answer.split('</think>')[-1].strip()
            if answer and answer != 'NO_FLAG_FOUND' and '{' in answer and '}' in answer:
                return answer
    except Exception as e:
        print(f"Groq API error: {e}")
    
    return None

@app.route('/flags')
def flags():
    """Display found flags page."""
    all_flags = load_flags()
    return render_template('flags.html', flags=all_flags)

@app.route('/api/flags')
def api_flags():
    """Get all found flags as JSON."""
    return jsonify(load_flags())

def process_container_flag(container_name):
    """Core logic to check for flag in a container."""
    import json
    
    # Get container metadata
    container_data_path = os.path.join(app.config['CONTAINER_DATA_PATH'], container_name)
    metadata_file = os.path.join(container_data_path, 'metadata.json')
    
    if not os.path.exists(metadata_file):
        return {'error': 'Container metadata not found', 'code': 404}
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    if not metadata.get('flag_detection', False):
        return {'flag_detection': False, 'message': 'Flag detection not enabled'}
    
    # Get container info
    containers = get_deployed_containers()
    container = next((c for c in containers if c['name'] == container_name), None)
    
    if not container or container['status'] != 'running':
        return {'error': 'Container not running', 'code': 400}
    
    api_port = container.get('api_port')
    if not api_port:
        return {'error': 'API port not found', 'code': 400}
    
    docker_host = app.config['DOCKER_HOST']
    
    try:
        # Get conversations
        conv_response = requests.get(f"http://{docker_host}:{api_port}/conversations", timeout=10)
        if conv_response.status_code != 200:
            return {'error': 'Failed to get conversations', 'code': 500}
        
        conversations = conv_response.json()
        if not conversations:
            return {'no_conversations': True}
        
        # Check the first (main) conversation
        conv_id = conversations[0].get('id')
        detail_response = requests.get(f"http://{docker_host}:{api_port}/conversation/{conv_id}", timeout=10)
        
        if detail_response.status_code != 200:
            return {'error': 'Failed to get conversation details', 'code': 500}
        
        conv_data = detail_response.json()
        status = conv_data.get('status', '')
        
        if status != 'CASCADE_RUN_STATUS_IDLE':
            return {'completed': False, 'status': status}
        
        # Check if we already found a flag for this container
        existing_flags = load_flags()
        if any(f['container_name'] == container_name for f in existing_flags):
            return {'completed': True, 'already_checked': True}
        
        # Get the final response text from the conversation
        steps = []
        if conv_data.get('state') and conv_data['state'].get('trajectory'):
            steps = conv_data['state']['trajectory'].get('steps', [])
        elif conv_data.get('trajectory'):
            steps = conv_data['trajectory'].get('steps', [])
        
        # Find text from the last few steps (both model responses and tool outputs)
        final_text = ''
        
        # Look at the last 5 steps to be safe
        recent_steps = steps[-5:] if len(steps) > 5 else steps
        
        for step in recent_steps:
            # Check planner response
            if step.get('type') == 'CORTEX_STEP_TYPE_PLANNER_RESPONSE':
                planner_resp = step.get('plannerResponse', {})
                text = planner_resp.get('rawModelResponse', '') or planner_resp.get('response', '')
                if text:
                    final_text += text + "\n\n"
            
            # Check tool outputs (e.g. if flag was printed)
            elif step.get('type') == 'CORTEX_STEP_TYPE_RUN_COMMAND':
                cmd_resp = step.get('runCommandResponse', {})
                output = cmd_resp.get('stdout', '')
                if output:
                    final_text += f"Command Output: {output}\n\n"
            
            # Check file reads
            elif step.get('type') == 'CORTEX_STEP_TYPE_READ_FILE':
                read_resp = step.get('readFileResponse', {})
                content = read_resp.get('content', '')
                if content:
                    final_text += f"File Content: {content}\n\n"

        if not final_text:
            return {'completed': True, 'no_content': True}
        
        # Use Groq to extract flag
        flag = extract_flag_with_groq(final_text)
        
        if flag:
            display_name = metadata.get('nickname', container_name)
            save_flag(container_name, display_name, flag)
            return {'completed': True, 'flag_found': True, 'flag': flag}
        
        # Mark as checked even if no flag found (to avoid repeated checks)
        save_flag(container_name, metadata.get('nickname', container_name), '[No flag detected]')
        return {'completed': True, 'flag_found': False}
        
    except Exception as e:
        return {'error': str(e), 'code': 500}

@app.route('/api/container/<container_name>/check_flag', methods=['POST'])
def api_check_flag(container_name):
    """Check for flag in container's completed conversation."""
    result = process_container_flag(container_name)
    if 'error' in result:
        return jsonify(result), result.get('code', 500)
    return jsonify(result)

def background_flag_monitor():
    """Periodically check all running containers for flags."""
    import time
    print("Starting background flag monitor...")
    while True:
        try:
            containers = get_deployed_containers()
            for container in containers:
                if container['status'] == 'running':
                    # We utilize the same logic, but ignore errors
                    try:
                        result = process_container_flag(container['name'])
                        if result.get('flag_found'):
                             print(f"Background Monitor: Flag found for {container['name']}!")
                    except Exception as e:
                        print(f"Error checking flag for {container['name']}: {e}")
            
            # Sleep for 10 seconds
            time.sleep(10)
        except Exception as e:
            print(f"Background monitor error: {e}")
            time.sleep(10)

if __name__ == '__main__':
    # Ensure upload and container data directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CONTAINER_DATA_PATH'], exist_ok=True)

    # Start background flag monitor
    import threading
    monitoring_thread = threading.Thread(target=background_flag_monitor, daemon=True)
    monitoring_thread.start()

    app.run(host='0.0.0.0', port=8080, debug=True)
