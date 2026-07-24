"""Restricted Docker Engine API client for LinuxServer Socket Proxy."""

import json
import urllib.error
import urllib.parse
import urllib.request


class DockerProxyError(RuntimeError):
    pass


class DockerProxyClient:
    def __init__(self, base_url):
        self.base_url = str(base_url).strip().rstrip("/")
        if not self.base_url:
            raise DockerProxyError("Docker Socket Proxy URL is not configured.")

    def _request(self, path, method="GET"):
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}",
            headers={"Accept": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                contents = response.read()
                if not contents:
                    return None
                text = contents.decode("utf-8")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise DockerProxyError(
                    "Docker Socket Proxy denied this operation. Check its endpoint permissions."
                ) from exc
            raise DockerProxyError(f"Docker Socket Proxy returned HTTP {exc.code}.") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise DockerProxyError(f"Could not connect to Docker Socket Proxy: {exc}") from exc

    def ping(self):
        return self._request("_ping") in (None, "OK")

    def containers(self):
        return self._request("containers/json?all=true") or []

    def find_container(self, container_name):
        desired = str(container_name).strip().lstrip("/")
        for container in self.containers():
            if desired in [name.lstrip("/") for name in container.get("Names", [])]:
                return container
        return None

    def start_container(self, container_id):
        encoded = urllib.parse.quote(str(container_id), safe="")
        self._request(f"containers/{encoded}/start", method="POST")

    def stop_container(self, container_id, timeout=60):
        encoded = urllib.parse.quote(str(container_id), safe="")
        self._request(f"containers/{encoded}/stop?t={int(timeout)}", method="POST")
