import base64
import json
import urllib.request
from core import config_manager

def call_palworld_api(endpoint, method="POST", payload=None):
    """
    Communicates with the Palworld REST API using credentials 
    stored dynamically in config_manager.CONFIG.
    """
    api_config = config_manager.get_palworld_api_config()
    api_port = api_config["port"]
    admin_password = api_config["admin_password"]

    url = f"http://127.0.0.1:{api_port}/v1/api/{endpoint}"
    
    # Generate basic authentication token dynamically
    auth_str = f"admin:{admin_password}"
    auth_bytes = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers = {"Authorization": f"Basic {auth_bytes}"}
    
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    # Execute the request context
    with urllib.request.urlopen(req, timeout=10) as response:
        status_code = response.getcode()
        if method == "GET" and status_code == 200:
            return json.loads(response.read().decode("utf-8"))
        return status_code


def announce_message(message):
    return call_palworld_api("announce", payload={"message": message})
