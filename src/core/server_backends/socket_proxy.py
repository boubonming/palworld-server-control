import os

from core.docker_proxy_client import DockerProxyClient


class SocketProxyBackend:
    """Controls one container through a restricted Docker Socket Proxy."""

    def __init__(self, config):
        self.config = config

    def client(self):
        return DockerProxyClient(
            self.config.get("docker_proxy_url", "http://socket-proxy:2375")
        )

    @property
    def container_name(self):
        return self.config.get("docker_container_name", "palworld-server")

    def validate(self):
        self.client().ping()
        if not os.path.isfile(self.config.get("palworld_ini_path", "")):
            raise FileNotFoundError(
                "PalWorldSettings.ini was not found in the mounted configuration directory."
            )
        if not self.client().find_container(self.container_name):
            raise RuntimeError(
                f"Container '{self.container_name}' was not found through Docker Socket Proxy."
            )
        return True

    def _container(self):
        return self.client().find_container(self.container_name)

    def instance_id(self):
        container = self._container()
        if not container or container.get("State") != "running":
            return None
        return container.get("Id")

    def processes(self):
        return []

    def is_running(self):
        try:
            return self.instance_id() is not None
        except (OSError, RuntimeError):
            return False

    def start(self):
        container = self._container()
        if not container:
            raise RuntimeError(f"Palworld container '{self.container_name}' was not found.")
        if container.get("State") == "running":
            return False
        self.client().start_container(container["Id"])
        return True

    def stop(self):
        container = self._container()
        if not container or container.get("State") != "running":
            return False
        self.client().stop_container(container["Id"], timeout=60)
        return True
