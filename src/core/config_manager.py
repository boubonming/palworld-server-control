import os
import json
import re
import shutil
import sys
import threading
import time

from core import docker_deployment
from core.palworld_ini import extract_option_settings, parse_option_settings
from core.server_backends import create_backend

CONFIG = {}
DEFAULT_GUI_CLOSE_BEHAVIOR = "exit"
VALID_GUI_CLOSE_BEHAVIORS = {"minimize", "exit"}
DEFAULT_AUTO_START = False
DEFAULT_DISCORD_BOT_AUTO_START = True
DEFAULT_SILENT_SERVER_LAUNCH = False
DEFAULT_AUTO_SHUTDOWN_ENABLED = True
DEFAULT_AUTO_SHUTDOWN_EMPTY_MINUTES = 5
DEFAULT_SERVER_BACKEND = "windows_native"
MIN_AUTO_SHUTDOWN_EMPTY_MINUTES = 1
MAX_AUTO_SHUTDOWN_EMPTY_MINUTES = 1440
_server_launch_source = None
_server_idle_shutdown_override = None
_server_launch_source_lock = threading.Lock()
AUTO_START_VALUE_NAME = "PalworldServerControl"
PALWORLD_BACKUP_NAME = "PalWorldSettings.ini.backup"
STRING_SETTING_KEYS = {
    "RandomizerSeed", "ServerName", "ServerDescription", "AdminPassword", "ServerPassword",
    "PublicIP", "Region", "BanListURL", "LogFormatType",
    "AdditionalDropItemWhenPlayerKillingInPvPMode",
}

def get_config_path():
    """Keeps configuration beside the executable instead of the launch directory."""
    data_dir = os.environ.get("PALWORLD_CONTROL_DATA_DIR", "").strip()
    if data_dir:
        base_dir = os.path.abspath(os.path.expanduser(data_dir))
        os.makedirs(base_dir, exist_ok=True)
    elif getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "config.json")

def load_config():
    global CONFIG
    config_filename = get_config_path()
    if not os.path.exists(config_filename):
        CONFIG = {
            "discord_bot_token": "",
            "palworld_channel_ids": [],
            "palworld_dir": "",
            "palworld_exe_path": "",
            "palworld_ini_path": "",
            "server_backend": DEFAULT_SERVER_BACKEND,
            "docker_compose_dir": "",
            "docker_compose_file": "compose.yaml",
            "docker_service_name": "palworld",
            "docker_env_file": ".env",
            "palworld_api_host": "127.0.0.1",
            "docker_proxy_url": "http://socket-proxy:2375",
            "docker_container_name": "palworld-server",
            "socket_proxy_configured": False,
            "gui_close_behavior": DEFAULT_GUI_CLOSE_BEHAVIOR,
            "auto_start": DEFAULT_AUTO_START,
            "discord_bot_auto_start": DEFAULT_DISCORD_BOT_AUTO_START,
            "silent_server_launch": DEFAULT_SILENT_SERVER_LAUNCH,
            "auto_shutdown_enabled": DEFAULT_AUTO_SHUTDOWN_ENABLED,
            "auto_shutdown_empty_minutes": DEFAULT_AUTO_SHUTDOWN_EMPTY_MINUTES,
        }
        save_config()
    else:
        with open(config_filename, "r") as f:
            CONFIG = json.load(f)
    CONFIG.setdefault("gui_close_behavior", DEFAULT_GUI_CLOSE_BEHAVIOR)
    CONFIG.setdefault("auto_start", DEFAULT_AUTO_START)
    CONFIG.setdefault("discord_bot_auto_start", DEFAULT_DISCORD_BOT_AUTO_START)
    CONFIG.setdefault("silent_server_launch", DEFAULT_SILENT_SERVER_LAUNCH)
    CONFIG.setdefault("auto_shutdown_enabled", DEFAULT_AUTO_SHUTDOWN_ENABLED)
    CONFIG.setdefault("auto_shutdown_empty_minutes", DEFAULT_AUTO_SHUTDOWN_EMPTY_MINUTES)
    CONFIG.setdefault("palworld_channel_ids", [])
    CONFIG.setdefault("server_backend", DEFAULT_SERVER_BACKEND)
    CONFIG.setdefault("docker_compose_dir", "")
    CONFIG.setdefault("docker_compose_file", "compose.yaml")
    CONFIG.setdefault("docker_service_name", "palworld")
    CONFIG.setdefault("docker_env_file", ".env")
    CONFIG.setdefault("palworld_api_host", "127.0.0.1")
    CONFIG.setdefault("docker_proxy_url", "http://socket-proxy:2375")
    CONFIG.setdefault("docker_container_name", "palworld-server")
    CONFIG.setdefault("socket_proxy_configured", False)
    return CONFIG

def save_config():
    with open(get_config_path(), "w") as f:
        json.dump(CONFIG, f, indent=4)

def get_gui_close_behavior():
    """Returns the configured GUI close behavior, defaulting safely to minimize."""
    behavior = CONFIG.get("gui_close_behavior", DEFAULT_GUI_CLOSE_BEHAVIOR)
    return behavior if behavior in VALID_GUI_CLOSE_BEHAVIORS else DEFAULT_GUI_CLOSE_BEHAVIOR

def set_gui_close_behavior(behavior):
    """Persists a supported GUI close behavior and normalizes invalid values."""
    CONFIG["gui_close_behavior"] = (
        behavior if behavior in VALID_GUI_CLOSE_BEHAVIORS else DEFAULT_GUI_CLOSE_BEHAVIOR
    )
    save_config()

def get_auto_start():
    return bool(CONFIG.get("auto_start", DEFAULT_AUTO_START))

def set_auto_start(enabled):
    """Registers or removes this app from the current user's Windows startup."""
    enabled = bool(enabled)
    if sys.platform != "win32":
        CONFIG["auto_start"] = enabled
        save_config()
        return True

    import winreg

    command = f'"{sys.executable}"'
    if not getattr(sys, "frozen", False):
        command += f' "{os.path.abspath(sys.argv[0])}"'
    command += " --background"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(key, AUTO_START_VALUE_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, AUTO_START_VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        return False

    CONFIG["auto_start"] = enabled
    save_config()
    return True


def ensure_auto_start_registration():
    """Repairs the Windows startup entry when autostart is enabled.

    The Run entry can be removed independently of config.json (for example by
    an uninstall/reinstall or a cleanup tool). Re-register it during startup
    so the saved preference remains effective.
    """
    if not get_auto_start() or sys.platform != "win32":
        return True
    return set_auto_start(True)

def get_discord_bot_auto_start():
    return bool(CONFIG.get("discord_bot_auto_start", DEFAULT_DISCORD_BOT_AUTO_START))

def set_discord_bot_auto_start(enabled):
    CONFIG["discord_bot_auto_start"] = bool(enabled)
    save_config()

def get_silent_server_launch():
    return bool(CONFIG.get("silent_server_launch", DEFAULT_SILENT_SERVER_LAUNCH))

def set_silent_server_launch(enabled):
    CONFIG["silent_server_launch"] = bool(enabled)
    save_config()

def get_auto_shutdown_enabled():
    return bool(CONFIG.get("auto_shutdown_enabled", DEFAULT_AUTO_SHUTDOWN_ENABLED))

def set_auto_shutdown_enabled(enabled):
    CONFIG["auto_shutdown_enabled"] = bool(enabled)
    save_config()

def get_auto_shutdown_empty_minutes():
    """Returns the idle duration required before an automatic shutdown."""
    try:
        minutes = int(CONFIG.get("auto_shutdown_empty_minutes", DEFAULT_AUTO_SHUTDOWN_EMPTY_MINUTES))
    except (TypeError, ValueError):
        minutes = DEFAULT_AUTO_SHUTDOWN_EMPTY_MINUTES
    return max(MIN_AUTO_SHUTDOWN_EMPTY_MINUTES, min(minutes, MAX_AUTO_SHUTDOWN_EMPTY_MINUTES))

def set_auto_shutdown_empty_minutes(minutes):
    """Persists a bounded automatic shutdown idle duration."""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        minutes = DEFAULT_AUTO_SHUTDOWN_EMPTY_MINUTES
    CONFIG["auto_shutdown_empty_minutes"] = max(
        MIN_AUTO_SHUTDOWN_EMPTY_MINUTES,
        min(minutes, MAX_AUTO_SHUTDOWN_EMPTY_MINUTES),
    )
    save_config()

def get_palworld_ini_settings():
    """Reads the OptionSettings values from PalWorldSettings.ini."""
    ini_path = CONFIG.get("palworld_ini_path", "")
    if not ini_path or not os.path.exists(ini_path):
        return {}
    with open(ini_path, "r", encoding="utf-8-sig") as f:
        contents = f.read()
    return extract_option_settings(contents)

def _get_default_ini_path():
    ini_path = CONFIG.get("palworld_ini_path", "")
    if is_docker_backend() and CONFIG.get("palworld_dir"):
        return os.path.join(CONFIG["palworld_dir"], "DefaultPalWorldSettings.ini")
    return os.path.join(os.path.dirname(ini_path), "DefaultPalWorldSettings.ini") if ini_path else ""

def get_default_palworld_ini_settings():
    """Reads the default settings shipped with the Palworld server update."""
    default_path = _get_default_ini_path()
    if not default_path or not os.path.exists(default_path):
        return {}
    with open(default_path, "r", encoding="utf-8-sig") as f:
        contents = f.read()
    return extract_option_settings(contents)

def get_palworld_editor_settings():
    """Returns current settings plus new keys introduced by the default file."""
    current = get_palworld_ini_settings()
    merged = dict(current)
    for key, value in get_default_palworld_ini_settings().items():
        merged.setdefault(key, value)
    if is_docker_backend():
        from core.setting_categories import SETTING_CATEGORIES

        env = docker_deployment.read_env(get_docker_env_path())
        for key in set(merged) | set(SETTING_CATEGORIES):
            env_name = docker_deployment.setting_to_env_name(key)
            if env_name in env:
                merged[key] = env[env_name]
    return merged

_parse_option_settings = parse_option_settings

def update_palworld_ini_settings(updates):
    """Updates selected OptionSettings values while preserving other INI values."""
    if is_docker_backend():
        if is_server_process_running():
            raise RuntimeError("Stop the Docker server before changing its settings.")
        env_updates = {
            docker_deployment.setting_to_env_name(key): value
            for key, value in updates.items()
        }
        docker_deployment.update_env(get_docker_env_path(), env_updates)
        return
    if is_socket_proxy_backend() and is_server_process_running():
        raise RuntimeError("Stop the Palworld container before changing its settings.")
    ini_path = CONFIG.get("palworld_ini_path", "")
    if not ini_path or not os.path.exists(ini_path):
        raise FileNotFoundError("PalWorldSettings.ini was not found. Select the Palworld server directory first.")
    with open(ini_path, "r", encoding="utf-8-sig") as f:
        contents = f.read()
    match = re.search(r"(?m)^OptionSettings=\((.*)\)\s*$", contents)
    if not match:
        raise ValueError("PalWorldSettings.ini does not contain an OptionSettings entry.")

    pairs = _parse_option_settings(match.group(1))
    quoted_keys = {
        key
        for key, value in pairs
        if len(value) >= 2 and value[0] == value[-1] == '"'
    }
    values = {
        key: value[1:-1] if key in quoted_keys else value
        for key, value in pairs
    }
    values.update({key: str(value) for key, value in updates.items()})
    serialized = ",".join(
        f'{key}="{value.replace(chr(34), chr(92) + chr(34))}"'
        if (key in quoted_keys or key in STRING_SETTING_KEYS)
        else f"{key}={value}"
        for key, value in values.items()
    )
    contents = contents[:match.start(1)] + serialized + contents[match.end(1):]
    backup_palworld_ini()
    with open(ini_path, "w", encoding="utf-8") as f:
        f.write(contents)

def get_palworld_backup_path():
    if is_docker_backend():
        return docker_deployment.backup_path(get_docker_env_path())
    ini_path = CONFIG.get("palworld_ini_path", "")
    return os.path.join(os.path.dirname(ini_path), PALWORLD_BACKUP_NAME) if ini_path else ""

def backup_palworld_ini():
    """Replaces the single rollback copy with the current settings file."""
    if is_docker_backend():
        env_path = get_docker_env_path()
        if not os.path.isfile(env_path):
            raise FileNotFoundError("Docker .env file was not found.")
        shutil.copy2(env_path, docker_deployment.backup_path(env_path))
        return
    ini_path = CONFIG.get("palworld_ini_path", "")
    backup_path = get_palworld_backup_path()
    if not ini_path or not os.path.exists(ini_path):
        raise FileNotFoundError("PalWorldSettings.ini was not found.")
    shutil.copy2(ini_path, backup_path)

def reset_palworld_ini_settings():
    """Resets default-known values while preserving custom/current-only values."""
    defaults = get_default_palworld_ini_settings()
    if not defaults:
        raise FileNotFoundError("DefaultPalWorldSettings.ini was not found or has no OptionSettings entry.")
    update_palworld_ini_settings(defaults)

def get_palworld_backup_changes():
    """Returns settings whose values differ from the current file."""
    if is_docker_backend():
        env_path = get_docker_env_path()
        backup_path = docker_deployment.backup_path(env_path)
        if not os.path.isfile(env_path):
            raise FileNotFoundError("Docker .env file was not found.")
        if not os.path.isfile(backup_path):
            raise FileNotFoundError("No .env.backup file exists yet.")
        current = docker_deployment.read_env(env_path)
        backup = docker_deployment.read_env(backup_path)
        return [
            (key, current.get(key, ""), backup.get(key, ""))
            for key in sorted(set(current) | set(backup))
            if current.get(key) != backup.get(key)
        ]
    ini_path = CONFIG.get("palworld_ini_path", "")
    backup_path = get_palworld_backup_path()
    if not ini_path or not os.path.exists(ini_path):
        raise FileNotFoundError("PalWorldSettings.ini was not found.")
    if not backup_path or not os.path.exists(backup_path):
        raise FileNotFoundError("No PalWorldSettings.ini.backup file exists yet.")
    current = _read_option_settings_file(ini_path)
    backup = _read_option_settings_file(backup_path)
    return [
        (key, current.get(key, ""), backup.get(key, ""))
        for key in sorted(set(current) | set(backup))
        if current.get(key) != backup.get(key)
    ]

def _read_option_settings_file(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        contents = f.read()
    match = re.search(r"(?m)^OptionSettings=\((.*)\)\s*$", contents)
    if not match:
        return {}
    return {
        key: value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value
        for key, value in _parse_option_settings(match.group(1))
    }

def revert_to_palworld_backup():
    """Restores the backup and makes the pre-revert file the new backup."""
    if is_docker_backend():
        if is_server_process_running():
            raise RuntimeError("Stop the Docker server before reverting settings.")
        docker_deployment.revert_env(get_docker_env_path())
        return
    if is_socket_proxy_backend() and is_server_process_running():
        raise RuntimeError("Stop the Palworld container before reverting settings.")
    ini_path = CONFIG.get("palworld_ini_path", "")
    backup_path = get_palworld_backup_path()
    if not ini_path or not os.path.exists(ini_path):
        raise FileNotFoundError("PalWorldSettings.ini was not found.")
    if not backup_path or not os.path.exists(backup_path):
        raise FileNotFoundError("No PalWorldSettings.ini.backup file exists yet.")
    with open(backup_path, "rb") as f:
        backup_contents = f.read()
    backup_palworld_ini()
    with open(ini_path, "wb") as f:
        f.write(backup_contents)

def get_palworld_api_config():
    """Returns REST API settings from the INI, with compatibility for old configs."""
    settings = get_palworld_ini_settings()
    env = docker_deployment.read_env(get_docker_env_path()) if is_docker_backend() else {}
    return {
        "enabled": env.get(
            "REST_API_ENABLED", settings.get("RESTAPIEnabled", "False")
        ).lower() == "true",
        "host": CONFIG.get("palworld_api_host", "127.0.0.1"),
        "port": int(env.get(
            "REST_API_PORT",
            settings.get("RESTAPIPort", CONFIG.get("palworld_api_port", 8212)),
        )),
        "admin_password": env.get(
            "ADMIN_PASSWORD",
            settings.get("AdminPassword", CONFIG.get("palworld_admin_password", "")),
        ),
    }

def update_paths_from_dir(chosen_dir):
    """Calculates and updates both exe and ini paths based on the root folder."""
    global CONFIG
    CONFIG["palworld_dir"] = chosen_dir
    
    # 1. Resolve Executable Path
    CONFIG["palworld_exe_path"] = os.path.join(chosen_dir, "PalServer.exe")
    
    # 2. Resolve Predictable INI Path Structure
    CONFIG["palworld_ini_path"] = os.path.join(
        chosen_dir, "Pal", "Saved", "Config", "WindowsServer", "PalWorldSettings.ini"
    )
    
    save_config()


def is_docker_backend():
    return CONFIG.get("server_backend", DEFAULT_SERVER_BACKEND) == "docker_compose"


def is_socket_proxy_backend():
    return CONFIG.get("server_backend", DEFAULT_SERVER_BACKEND) == "socket_proxy"


def is_container_backend():
    return is_docker_backend() or is_socket_proxy_backend()


def get_docker_env_path():
    compose_dir = CONFIG.get("docker_compose_dir", "")
    env_file = CONFIG.get("docker_env_file", ".env")
    if not compose_dir:
        return ""
    return env_file if os.path.isabs(env_file) else os.path.join(compose_dir, env_file)


def configure_docker_backend(
    compose_dir,
    compose_file="compose.yaml",
    service_name="palworld",
    env_file=".env",
    palworld_data_dir=None,
):
    compose_dir = os.path.abspath(os.path.expanduser(compose_dir))
    data_dir = os.path.abspath(os.path.expanduser(
        palworld_data_dir or os.path.join(compose_dir, "palworld")
    ))
    candidate = dict(CONFIG)
    candidate.update({
        "server_backend": "docker_compose",
        "docker_compose_dir": compose_dir,
        "docker_compose_file": compose_file,
        "docker_service_name": service_name,
        "docker_env_file": env_file,
        "palworld_dir": data_dir,
        "palworld_exe_path": "",
        "palworld_ini_path": os.path.join(
            data_dir,
            "Pal",
            "Saved",
            "Config",
            "LinuxServer",
            "PalWorldSettings.ini",
        ),
        "palworld_api_host": "127.0.0.1",
    })
    create_backend(candidate).validate()
    CONFIG.update(candidate)
    save_config()


def configure_socket_proxy_backend(
    proxy_url="http://socket-proxy:2375",
    container_name="palworld-server",
    palworld_ini_path="/palworld-config/PalWorldSettings.ini",
    palworld_api_host="palworld-server",
):
    candidate = dict(CONFIG)
    candidate.update({
        "server_backend": "socket_proxy",
        "docker_proxy_url": str(proxy_url).strip().rstrip("/"),
        "docker_container_name": str(container_name).strip() or "palworld-server",
        "socket_proxy_configured": True,
        "palworld_ini_path": os.path.abspath(os.path.expanduser(palworld_ini_path)),
        "palworld_dir": "",
        "palworld_exe_path": "",
        "palworld_api_host": str(palworld_api_host).strip() or "palworld-server",
    })
    create_backend(candidate).validate()
    settings = _read_option_settings_file(candidate["palworld_ini_path"])
    if settings.get("RESTAPIEnabled", "False").lower() != "true":
        raise ValueError("Enable RESTAPIEnabled in PalWorldSettings.ini before connecting.")
    if not settings.get("AdminPassword"):
        raise ValueError("Set AdminPassword in PalWorldSettings.ini before connecting.")
    CONFIG.update(candidate)
    save_config()


def get_server_backend():
    return create_backend(CONFIG)


def get_server_process_id():
    """Returns the active native PID or Docker container ID."""
    return get_server_backend().instance_id()


def get_server_processes():
    """Returns detected native processes; Docker mode has no host processes."""
    return get_server_backend().processes()


def is_server_process_running():
    return get_server_backend().is_running()


def set_server_launch_source(source, idle_shutdown_override=None):
    """Records the launch source and optional session-only idle policy override."""
    global _server_launch_source, _server_idle_shutdown_override
    with _server_launch_source_lock:
        _server_launch_source = source
        _server_idle_shutdown_override = idle_shutdown_override


def get_server_launch_source():
    with _server_launch_source_lock:
        return _server_launch_source


def get_server_idle_shutdown_override():
    """Returns False, a minute count, or None to use the saved default."""
    with _server_launch_source_lock:
        return _server_idle_shutdown_override


def clear_server_launch_source():
    set_server_launch_source(None, None)


def get_server_launch_command():
    """Builds the configured supported or windowless server launch command."""
    backend = get_server_backend()
    if not hasattr(backend, "launch_command"):
        raise RuntimeError("The container backend does not launch a local executable.")
    return backend.launch_command()


def start_server():
    """Starts the configured Palworld server without involving Discord."""
    started = get_server_backend().start()
    if started:
        set_server_launch_source("app")
    return started

def stop_server():
    """Saves and gracefully stops the selected server backend."""
    if not is_server_process_running():
        return False

    from core import api_client

    shutdown_wait_seconds = 5
    save_status = api_client.call_palworld_api("save")
    if is_container_backend() and save_status not in (200, 202):
        raise RuntimeError(f"Server save request returned HTTP {save_status}.")

    status = api_client.call_palworld_api(
        "shutdown",
        payload={
            "waittime": shutdown_wait_seconds,
            "message": "Server shutting down",
        },
    )
    if status not in (200, 202):
        raise RuntimeError(f"Server shutdown request returned HTTP {status}.")

    if is_container_backend():
        # Let Palworld display and complete its shutdown countdown before
        # intentionally stopping the container so `unless-stopped` stays stopped.
        time.sleep(shutdown_wait_seconds + 1)
        backend = get_server_backend()
        if backend.is_running():
            return backend.stop()
        return True

    return True
