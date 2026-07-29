"""Platform-specific Palworld server lifecycle backends."""

from core.server_backends.docker_compose import DockerComposeBackend
from core.server_backends.socket_proxy import SocketProxyBackend
from core.server_backends.windows_native import WindowsNativeBackend


def create_backend(config):
    backend_name = config.get("server_backend", "windows_native")
    if backend_name == "docker_compose":
        return DockerComposeBackend(config)
    if backend_name == "socket_proxy":
        return SocketProxyBackend(config)
    return WindowsNativeBackend(config)


__all__ = [
    "DockerComposeBackend",
    "SocketProxyBackend",
    "WindowsNativeBackend",
    "create_backend",
]
