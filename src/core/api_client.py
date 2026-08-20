import base64
import json
import logging
import time
import urllib.error
import urllib.request

from core import config_manager

logger = logging.getLogger(__name__)


def call_palworld_api(endpoint, method="POST", payload=None, timeout=10):
    """
    Communicates with the Palworld REST API using credentials 
    stored dynamically in config_manager.CONFIG.
    """
    api_config = config_manager.get_palworld_api_config()
    api_host = api_config.get("host", "127.0.0.1")
    api_port = api_config["port"]
    admin_password = api_config["admin_password"]

    url = f"http://{api_host}:{api_port}/v1/api/{endpoint}"
    
    # Generate basic authentication token dynamically
    auth_str = f"admin:{admin_password}"
    auth_bytes = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers = {"Authorization": f"Basic {auth_bytes}"}
    
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started_at = time.monotonic()
    logger.info(
        "Palworld API request started: method=%s url=%s timeout=%ss",
        method,
        url,
        timeout,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.getcode()
            if method == "GET" and status_code == 200:
                result = json.loads(response.read().decode("utf-8"))
            else:
                result = status_code
    except urllib.error.HTTPError as exc:
        logger.error(
            "Palworld API request failed: method=%s url=%s status=%s reason=%s "
            "elapsed=%.3fs",
            method,
            url,
            exc.code,
            exc.reason,
            time.monotonic() - started_at,
            exc_info=True,
        )
        raise
    except Exception as exc:
        logger.error(
            "Palworld API request failed: method=%s url=%s error=%s: %s "
            "elapsed=%.3fs",
            method,
            url,
            type(exc).__name__,
            exc,
            time.monotonic() - started_at,
            exc_info=True,
        )
        raise

    logger.info(
        "Palworld API request completed: method=%s url=%s status=%s elapsed=%.3fs",
        method,
        url,
        status_code,
        time.monotonic() - started_at,
    )
    return result


def announce_message(message):
    return call_palworld_api("announce", payload={"message": message})
