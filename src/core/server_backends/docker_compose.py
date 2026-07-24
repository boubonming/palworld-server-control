import os
import subprocess


class DockerComposeBackend:
    """Controls one Palworld service in an existing Docker Compose project."""

    def __init__(self, config):
        self.config = config

    @property
    def compose_dir(self):
        configured = self.config.get("docker_compose_dir", "")
        return os.path.abspath(configured) if configured else ""

    @property
    def compose_file(self):
        configured = self.config.get("docker_compose_file", "compose.yaml")
        return configured if os.path.isabs(configured) else os.path.join(self.compose_dir, configured)

    @property
    def service(self):
        return self.config.get("docker_service_name", "palworld")

    def _base_command(self):
        if not self.compose_dir:
            raise FileNotFoundError("Docker Compose directory is not configured.")
        if not os.path.isfile(self.compose_file):
            raise FileNotFoundError(f"Docker Compose file was not found: {self.compose_file}")
        return [
            "docker",
            "compose",
            "--project-directory",
            self.compose_dir,
            "-f",
            self.compose_file,
        ]

    def _run(self, *arguments, timeout=120, check=True):
        return subprocess.run(
            [*self._base_command(), *arguments],
            cwd=self.compose_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )

    def validate(self):
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        services = self._run("config", "--services", timeout=30).stdout.splitlines()
        if self.service not in services:
            raise RuntimeError(
                f"Compose service '{self.service}' was not found. "
                f"Available services: {', '.join(services) or 'none'}"
            )
        return True

    def instance_id(self):
        result = self._run(
            "ps", "--status", "running", "--quiet", self.service,
            timeout=20,
        )
        return result.stdout.strip() or None

    def processes(self):
        return []

    def is_running(self):
        try:
            return self.instance_id() is not None
        except (FileNotFoundError, subprocess.SubprocessError):
            return False

    def start(self):
        if self.is_running():
            return False
        self._run("up", "-d", self.service, timeout=600)
        return True

    def pull(self):
        self._run("pull", self.service, timeout=1200)
        return True

    def stop(self):
        if not self.is_running():
            return False
        self._run("stop", self.service, timeout=120)
        if self.is_running():
            raise RuntimeError("Docker reported success, but the Palworld container is still running.")
        return True
