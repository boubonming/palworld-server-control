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

    def _request(self, path, method="GET", timeout=15, raw=False):
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}",
            headers={"Accept": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                contents = response.read()
                if not contents:
                    return b"" if raw else None
                if raw:
                    return contents
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

    def inspect_container(self, container_id):
        encoded = urllib.parse.quote(str(container_id), safe="")
        return self._request(f"containers/{encoded}/json") or {}

    def container_logs(self, container_id, tail=200):
        encoded = urllib.parse.quote(str(container_id), safe="")
        tail = min(max(int(tail), 20), 1000)
        contents = self._request(
            (
                f"containers/{encoded}/logs"
                f"?stdout=1&stderr=1&timestamps=1&tail={tail}"
            ),
            raw=True,
        )
        return self._decode_log_stream(contents)

    @staticmethod
    def _decode_log_stream(contents):
        """Decodes Docker's multiplexed stdout/stderr framing when present."""
        if not contents:
            return ""
        if (
            len(contents) < 8
            or contents[0] not in (0, 1, 2)
            or contents[1:4] != b"\0\0\0"
        ):
            return contents.decode("utf-8", errors="replace")

        messages = []
        offset = 0
        while offset + 8 <= len(contents):
            header = contents[offset:offset + 8]
            if header[0] not in (0, 1, 2) or header[1:4] != b"\0\0\0":
                return contents.decode("utf-8", errors="replace")
            length = int.from_bytes(header[4:8], "big")
            start = offset + 8
            end = start + length
            if end > len(contents):
                return contents.decode("utf-8", errors="replace")
            messages.append(contents[start:end])
            offset = end
        return b"".join(messages).decode("utf-8", errors="replace")

    def start_container(self, container_id):
        encoded = urllib.parse.quote(str(container_id), safe="")
        self._request(f"containers/{encoded}/start", method="POST")

    def stop_container(self, container_id, timeout=60):
        encoded = urllib.parse.quote(str(container_id), safe="")
        self._request(
            f"containers/{encoded}/stop?t={int(timeout)}",
            method="POST",
            timeout=int(timeout) + 15,
        )
