import os
import json
import re
import psutil
import shutil
import sys
import subprocess
import threading

from core.palworld_ini import extract_option_settings, parse_option_settings

CONFIG = {}
SERVER_BINARY_NAMES = (
    "PalServer-Win64-Shipping-Cmd.exe",
    "PalServer-Win64-Test-Cmd.exe",
)
DEFAULT_GUI_CLOSE_BEHAVIOR = "exit"
VALID_GUI_CLOSE_BEHAVIORS = {"minimize", "exit"}
DEFAULT_AUTO_START = False
DEFAULT_DISCORD_BOT_AUTO_START = True
DEFAULT_SILENT_SERVER_LAUNCH = False
DEFAULT_AUTO_SHUTDOWN_ENABLED = True
DEFAULT_AUTO_SHUTDOWN_EMPTY_MINUTES = 5
MIN_AUTO_SHUTDOWN_EMPTY_MINUTES = 1
MAX_AUTO_SHUTDOWN_EMPTY_MINUTES = 1440
_server_launch_source = None
_server_idle_shutdown_override = None
_server_launch_source_lock = threading.Lock()
AUTO_START_VALUE_NAME = "PalworldServerControl"
PALWORLD_BACKUP_NAME = "PalWorldSettings.ini.backup"
STRING_SETTING_KEYS = {
    "RandomizerSeed", "ServerName", "ServerDescription", "AdminPassword", "ServerPassword",
    "PublicIP", "Region", "BanListURL", "DenyTechnologyList", "LogFormatType",
    "AdditionalDropItemWhenPlayerKillingInPvPMode",
}

def get_config_path():
    """Keeps configuration beside the executable instead of the launch directory."""
    if getattr(sys, "frozen", False):
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
    return merged

_parse_option_settings = parse_option_settings

def update_palworld_ini_settings(updates):
    """Updates selected OptionSettings values while preserving other INI values."""
    ini_path = CONFIG.get("palworld_ini_path", "")
    if not ini_path or not os.path.exists(ini_path):
        raise FileNotFoundError("PalWorldSettings.ini was not found. Select the Palworld server directory first.")
    with open(ini_path, "r", encoding="utf-8-sig") as f:
        contents = f.read()
    match = re.search(r"(?m)^OptionSettings=\((.*)\)\s*$", contents)
    if not match:
        raise ValueError("PalWorldSettings.ini does not contain an OptionSettings entry.")

    pairs = _parse_option_settings(match.group(1))
    values = dict(pairs)
    values.update({key: str(value) for key, value in updates.items()})
    serialized = ",".join(
        f'{key}="{value.replace(chr(34), chr(92) + chr(34))}"'
        if (dict(pairs).get(key, "").startswith('"') or key in STRING_SETTING_KEYS)
        else f"{key}={value}"
        for key, value in values.items()
    )
    contents = contents[:match.start(1)] + serialized + contents[match.end(1):]
    backup_palworld_ini()
    with open(ini_path, "w", encoding="utf-8") as f:
        f.write(contents)

def get_palworld_backup_path():
    ini_path = CONFIG.get("palworld_ini_path", "")
    return os.path.join(os.path.dirname(ini_path), PALWORLD_BACKUP_NAME) if ini_path else ""

def backup_palworld_ini():
    """Replaces the single rollback copy with the current settings file."""
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
    return {
        "enabled": settings.get("RESTAPIEnabled", "False").lower() == "true",
        "port": int(settings.get("RESTAPIPort", CONFIG.get("palworld_api_port", 8212))),
        "admin_password": settings.get("AdminPassword", CONFIG.get("palworld_admin_password", "")),
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

def get_server_process_id():
    """Returns the PID of the first detected Palworld server process."""
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name']
            if name and ("PalServer.exe" in name or "PalServer-Win64" in name):
                return proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def get_server_processes():
    """Returns all detected Palworld server processes."""
    processes = []
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name']
            if name and ("PalServer.exe" in name or "PalServer-Win64" in name):
                processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes


def is_server_process_running():
    """Scans the Windows process list natively without spawning cmd windows."""
    return get_server_process_id() is not None


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
    server_exe = CONFIG.get("palworld_exe_path")
    if not server_exe:
        raise FileNotFoundError("Server executable path is not configured.")

    if not get_silent_server_launch():
        return [server_exe, "-publiclobby"]

    server_dir = CONFIG.get("palworld_dir") or os.path.dirname(server_exe)
    binaries_dir = os.path.join(server_dir, "Pal", "Binaries", "Win64")
    for binary_name in SERVER_BINARY_NAMES:
        process_exe = os.path.join(binaries_dir, binary_name)
        if os.path.isfile(process_exe):
            # This matches the command created by PalServer.exe, but lets this
            # app apply CREATE_NO_WINDOW to the process that creates conhost.
            return [process_exe, "Pal", "-publiclobby", "-NOCONSOLE"]

    raise FileNotFoundError(
        "Silent launch is unavailable because the internal PalServer executable was not found. "
        "Disable silent launch in App Settings and try again."
    )


def start_server():
    """Starts the configured Palworld server without involving Discord."""
    if is_server_process_running():
        return False

    subprocess.Popen(
        get_server_launch_command(),
        cwd=CONFIG.get("palworld_dir") or None,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    set_server_launch_source("app")
    return True

def stop_server():
    """Saves and requests a graceful shutdown through the Palworld API."""
    if not is_server_process_running():
        return False

    from core import api_client

    api_client.call_palworld_api("save")
    status = api_client.call_palworld_api(
        "shutdown",
        payload={"waittime": 5, "message": "Server shutting down"},
    )
    if status not in (200, 202):
        raise RuntimeError(f"Server shutdown request returned HTTP {status}.")
    return True
