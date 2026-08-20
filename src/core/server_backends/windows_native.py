import os
import subprocess

import psutil


SERVER_BINARY_NAMES = (
    "PalServer-Win64-Shipping-Cmd.exe",
    "PalServer-Win64-Test-Cmd.exe",
)


class WindowsNativeBackend:
    """Preserves the existing native Windows PalServer lifecycle."""

    def __init__(self, config):
        self.config = config

    def instance_id(self):
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"]
                if name and ("PalServer.exe" in name or "PalServer-Win64" in name):
                    return proc.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def processes(self):
        processes = []
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"]
                if name and ("PalServer.exe" in name or "PalServer-Win64" in name):
                    processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return processes

    def is_running(self):
        return self.instance_id() is not None

    def launch_command(self):
        server_exe = self.config.get("palworld_exe_path")
        if not server_exe:
            raise FileNotFoundError("Server executable path is not configured.")

        if not self.config.get("silent_server_launch", False):
            return [server_exe, "-publiclobby"]

        server_dir = self.config.get("palworld_dir") or os.path.dirname(server_exe)
        binaries_dir = os.path.join(server_dir, "Pal", "Binaries", "Win64")
        for binary_name in SERVER_BINARY_NAMES:
            process_exe = os.path.join(binaries_dir, binary_name)
            if os.path.isfile(process_exe):
                return [process_exe, "Pal", "-publiclobby", "-NOCONSOLE"]

        raise FileNotFoundError(
            "Silent launch is unavailable because the internal PalServer executable "
            "was not found. Disable silent launch in App Settings and try again."
        )

    def start(self):
        if self.is_running():
            return False
        subprocess.Popen(
            self.launch_command(),
            cwd=self.config.get("palworld_dir") or None,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True

