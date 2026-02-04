import re
import os

print("Starting FINAL patch process...")
original_path = '/usr/share/antigravity/resources/app/extensions/antigravity/dist/extension.js'

# Read content
with open(original_path, 'r') as f:
    content = f.read()

def replace_assignment(pattern_prefix, global_target, content):
    regex = re.compile(pattern_prefix + r'=([a-zA-Z0-9_]+)')
    matches = list(regex.finditer(content))
        
    for m in matches:
        val = m.group(1)
        full_match = m.group(0)
        
        if val in ['void', 'null', 'undefined']:
            continue
            
        print(f'Replacing {full_match} with global export...')
        replacement = f'{full_match.split("=")[0]}=(global.AntigravityExports=global.AntigravityExports||{{}},{global_target}={val})'
        content = content.replace(full_match, replacement)
        
    return content

# 1. Patch the Client Class
content = replace_assignment(r't\.LanguageServerClient', 'global.AntigravityExports.ClientClass', content)
# 2. Patch the Metadata Provider
content = replace_assignment(r't\.MetadataProvider', 'global.AntigravityExports.MetadataProvider', content)

# 3. Patch the Request Module
# We hook StartCascadeRequest to capture the module 't' as 'ProtoRequests'
req_regex = re.compile(r'([a-zA-Z0-9_]+)\.StartCascadeRequest=([a-zA-Z0-9_]+)')
matches_req = list(req_regex.finditer(content))
for m in matches_req:
    module_var = m.group(1)
    class_var = m.group(2)
    full_match = m.group(0)
    
    if class_var in ['void', 'null', 'undefined']:
        continue
        
    print(f'Replacing {full_match} to export module {module_var}...')
    replacement = f'{module_var}.StartCascadeRequest=(global.AntigravityExports=global.AntigravityExports||{{}},global.AntigravityExports.ProtoRequests={module_var},{class_var})'
    content = content.replace(full_match, replacement)

# 4. Append the Bridge Server
injection_code = r'''
// FINAL INJECTION START
(function() {
    const fs = require('fs');
    const http = require('http');
    const port = 5555;
    const logFile = '/tmp/antigravity_bridge.log';
    
    try { fs.writeFileSync(logFile, ''); } catch(e){}
    
    function log(msg) {
        try { fs.appendFileSync(logFile, msg + '\n'); } catch(e){}
    }
    
    log('Final Injection started at ' + new Date().toISOString());

    const waitForClient = setInterval(() => {
        try {
            if (global.AntigravityExports && global.AntigravityExports.ClientClass) {
                // Try to get instance. This throws if not initialized.
                let clientInstance;
                try {
                    clientInstance = global.AntigravityExports.ClientClass.getInstance();
                } catch (e) {
                    log('ClientClass found but getInstance() threw: ' + e.message);
                    return; // Retry next loop
                }

                if (clientInstance && clientInstance.client) {
                    clearInterval(waitForClient);
                    log('Client instance and RPC client successfully acquired!');
                    startServer(clientInstance.client, global.AntigravityExports.ProtoRequests, global.AntigravityExports.MetadataProvider);
                }
            }
        } catch (e) {
             log('Error in loop: ' + e.toString());
        }
    }, 1000);

    function startServer(rpcClient, protos, metadataProvider) {
        log('Attempting to start server...');
        try {
            const server = http.createServer((req, res) => {
                log('Request: ' + req.method + ' ' + req.url);

                if (req.method === 'POST' && req.url === '/rpc') {
                    let body = '';
                    req.on('data', chunk => {
                        body += chunk.toString();
                    });
                    req.on('end', () => {
                         try {
                             const data = JSON.parse(body);
                             const methodName = data.method;
                             const requestClassName = data.requestClass;
                             const payload = data.payload;
                             
                             log('RPC Call: ' + methodName + ' with ' + requestClassName);
                             
                             if (!protos[requestClassName]) {
                                 res.writeHead(400);
                                 res.end('Unknown Request Class: ' + requestClassName);
                                 return;
                             }
                             
                             if (!rpcClient[methodName]) {
                                 res.writeHead(400);
                                 res.end('Unknown Client Method: ' + methodName);
                                 return;
                             }
                             
                             const meta = metadataProvider ? metadataProvider.getInstance().getMetadata() : null;
                             // Merge metadata into payload if not present, or create new object
                             const requestData = Object.assign({ metadata: meta }, payload);
                             
                             const reqObj = new protos[requestClassName](requestData);
                             
                             rpcClient[methodName](reqObj).then(response => {
                                 res.writeHead(200, {'Content-Type': 'application/json'});
                                 res.end(JSON.stringify(response));
                             }).catch(err => {
                                 log('RPC Error: ' + err.toString());
                                 res.writeHead(500);
                                 res.end(err.toString());
                             });
                         } catch (e) {
                             log('RPC Exception: ' + e.toString());
                             res.writeHead(500);
                             res.end(e.toString());
                         }
                    });
                } else {
                    res.writeHead(404);
                    res.end('Endpoint not found. Use POST /rpc with { method, requestClass, payload }');
                }
            });
            
            server.listen(port, '0.0.0.0', () => {
                 log('Server successfully LISTENING on ' + port);
            });
        } catch(e) {
             log('Server start EXCEPTION: ' + e.toString());
        }
    }
})();
// FINAL INJECTION END
'''

with open(original_path, 'w') as f:
    f.write(content + injection_code)
print("Final patch complete.")
