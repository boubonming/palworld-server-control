import unittest
from unittest.mock import Mock, patch

from core import server_readiness
from core.docker_proxy_client import DockerProxyClient, DockerProxyError
from core.server_backends.socket_proxy import SocketProxyBackend
from shared.status import ServerState, ServerStatus
from web.app import create_web_app


class DockerProxyClientTests(unittest.TestCase):
    def test_inspect_container_requests_container_details(self):
        client = DockerProxyClient("http://socket-proxy:2375")

        with patch.object(client, "_request", return_value={"State": {}}) as request:
            result = client.inspect_container("container/id")

        self.assertEqual(result, {"State": {}})
        request.assert_called_once_with("containers/container%2Fid/json")

    def test_stop_request_outlives_docker_grace_period(self):
        client = DockerProxyClient("http://socket-proxy:2375")

        with patch.object(client, "_request") as request:
            client.stop_container("container-id", timeout=60)

        request.assert_called_once_with(
            "containers/container-id/stop?t=60",
            method="POST",
            timeout=75,
        )


class SocketProxyBackendTests(unittest.TestCase):
    def test_health_status_comes_from_container_inspection(self):
        backend = SocketProxyBackend(
            {
                "docker_proxy_url": "http://socket-proxy:2375",
                "docker_container_name": "palworld-server",
            }
        )
        client = Mock()
        client.find_container.return_value = {
            "Id": "container-id",
            "State": "running",
        }
        client.inspect_container.return_value = {
            "State": {"Health": {"Status": "healthy"}}
        }

        with patch.object(backend, "client", return_value=client):
            self.assertEqual(backend.health_status(), "healthy")

        client.inspect_container.assert_called_once_with("container-id")

    def test_timed_out_stop_succeeds_when_container_is_offline(self):
        backend = SocketProxyBackend(
            {
                "docker_proxy_url": "http://socket-proxy:2375",
                "docker_container_name": "palworld-server",
            }
        )
        client = Mock()
        client.find_container.side_effect = [
            {"Id": "container-id", "State": "running"},
            {"Id": "container-id", "State": "exited"},
        ]
        client.stop_container.side_effect = DockerProxyError("timed out")

        with patch.object(backend, "client", return_value=client):
            self.assertTrue(backend.stop())


class ServerReadinessTests(unittest.TestCase):
    def test_running_container_with_starting_health_is_not_ready(self):
        backend = Mock()
        backend.is_running.return_value = True
        backend.health_status.return_value = "starting"

        with patch.object(
            server_readiness.config_manager,
            "get_server_backend",
            return_value=backend,
        ):
            status = server_readiness.get_status()

        self.assertEqual(status.state, ServerState.STARTING)

    def test_healthy_container_is_ready_without_player_api_probe(self):
        backend = Mock()
        backend.is_running.return_value = True
        backend.health_status.return_value = "healthy"

        with (
            patch.object(
                server_readiness.config_manager,
                "get_server_backend",
                return_value=backend,
            ),
            patch("core.api_client.call_palworld_api") as api_request,
        ):
            status = server_readiness.get_status()

        self.assertEqual(status.state, ServerState.RUNNING)
        api_request.assert_not_called()

    def test_missing_healthcheck_uses_fast_api_probe(self):
        backend = Mock()
        backend.is_running.return_value = True
        backend.health_status.return_value = None

        with (
            patch.object(
                server_readiness.config_manager,
                "get_server_backend",
                return_value=backend,
            ),
            patch(
                "core.api_client.call_palworld_api",
                return_value={"players": []},
            ) as api_request,
        ):
            status = server_readiness.get_status()

        self.assertEqual(status.state, ServerState.RUNNING)
        api_request.assert_called_once_with("players", method="GET", timeout=2)

    def test_wait_for_ready_polls_until_running(self):
        statuses = iter(
            [
                ServerStatus(ServerState.STARTING),
                ServerStatus(ServerState.RUNNING),
            ]
        )
        observed = []

        result = server_readiness.wait_until_ready(
            timeout=1,
            poll_interval=0,
            status_getter=lambda: next(statuses),
            on_status=observed.append,
        )

        self.assertEqual(result.state, ServerState.RUNNING)
        self.assertEqual(
            [status.state for status in observed],
            [ServerState.STARTING, ServerState.RUNNING],
        )


class HealthEndpointTests(unittest.TestCase):
    def test_health_endpoint_does_not_require_authentication(self):
        runtime = Mock()

        with patch("web.app.config_manager.CONFIG", {"web_secret_key": "test-secret"}):
            app = create_web_app(runtime)
            response = app.test_client().get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
