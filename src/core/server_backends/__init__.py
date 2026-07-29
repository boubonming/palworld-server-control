"""Platform-specific Palworld server lifecycle backends."""


def create_backend(config):
    backend_name = config.get("server_backend", "windows_native")
    if backend_name == "docker_compose":
        from core.server_backends.docker_compose import DockerComposeBackend

        return DockerComposeBackend(config)
    if backend_name == "socket_proxy":
        from core.server_backends.socket_proxy import SocketProxyBackend

        return SocketProxyBackend(config)
    from core.server_backends.windows_native import WindowsNativeBackend

    return WindowsNativeBackend(config)


__all__ = ["create_backend"]
