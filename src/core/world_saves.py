"""Discovery and selection of Palworld dedicated-server world saves."""

from datetime import datetime
import os
import re
import shutil
import tempfile

from core import config_manager
from core.auto_backup import get_save_games_path


DEDICATED_SERVER_NAME = re.compile(
    r"(?m)^(?P<prefix>\s*DedicatedServerName\s*=\s*)(?P<value>[^\r\n]*)(?P<ending>\r?\n|$)"
)


def get_game_user_settings_path():
    """Return the GameUserSettings.ini beside the accessible SaveGames folder."""
    save_games_path = get_save_games_path()
    if not save_games_path:
        return ""

    config_root = os.path.join(os.path.dirname(save_games_path), "Config")
    ini_path = config_manager.CONFIG.get("palworld_ini_path", "")
    preferred = (
        "WindowsServer"
        if "windowsserver" in ini_path.replace("\\", "/").lower()
        else "LinuxServer"
    )
    candidates = [
        os.path.join(config_root, preferred, "GameUserSettings.ini"),
        os.path.join(config_root, "WindowsServer", "GameUserSettings.ini"),
        os.path.join(config_root, "LinuxServer", "GameUserSettings.ini"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    return os.path.abspath(candidates[0])


def get_active_world_id():
    path = get_game_user_settings_path()
    if not path or not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8-sig") as settings_file:
        match = DEDICATED_SERVER_NAME.search(settings_file.read())
    return match.group("value").strip() if match else ""


def list_world_saves():
    """List valid world folders and mark the configured active world."""
    save_root = os.path.join(get_save_games_path(), "0")
    if not os.path.isdir(save_root):
        return []

    active_world_id = get_active_world_id()
    worlds = []
    for world_id in sorted(os.listdir(save_root), key=str.casefold):
        path = os.path.join(save_root, world_id)
        level_path = os.path.join(path, "Level.sav")
        if not os.path.isdir(path) or not os.path.isfile(level_path):
            continue
        statistics = os.stat(level_path)
        worlds.append(
            {
                "id": world_id,
                "active": world_id == active_world_id,
                "modified_at": datetime.fromtimestamp(
                    statistics.st_mtime
                ).astimezone(),
                "path": path,
            }
        )
    worlds.sort(key=lambda world: world["modified_at"], reverse=True)
    return worlds


def select_world_save(world_id):
    """Select an existing world by updating DedicatedServerName atomically."""
    if config_manager.is_server_process_running():
        raise RuntimeError("Stop the server before changing the active world save.")
    if not world_id or world_id != os.path.basename(world_id):
        raise ValueError("Select a valid world save.")

    save_root = os.path.abspath(os.path.join(get_save_games_path(), "0"))
    world_path = os.path.abspath(os.path.join(save_root, world_id))
    if os.path.commonpath([save_root, world_path]) != save_root:
        raise ValueError("Select a valid world save.")
    if not os.path.isfile(os.path.join(world_path, "Level.sav")):
        raise FileNotFoundError("The selected world does not contain Level.sav.")

    settings_path = get_game_user_settings_path()
    if not settings_path or not os.path.isfile(settings_path):
        raise FileNotFoundError(
            "GameUserSettings.ini was not found. Start the server once to create it."
        )
    with open(settings_path, "r", encoding="utf-8-sig", newline="") as settings_file:
        contents = settings_file.read()
    if not DEDICATED_SERVER_NAME.search(contents):
        raise ValueError("GameUserSettings.ini has no DedicatedServerName entry.")

    updated = DEDICATED_SERVER_NAME.sub(
        lambda match: (
            f"{match.group('prefix')}{world_id}{match.group('ending')}"
        ),
        contents,
        count=1,
    )
    if updated == contents:
        return False

    original_stat = os.stat(settings_path)
    shutil.copy2(settings_path, settings_path + ".backup")
    descriptor, temporary_path = tempfile.mkstemp(
        prefix="GameUserSettings.", suffix=".tmp", dir=os.path.dirname(settings_path)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as settings_file:
            settings_file.write(updated)
        os.chmod(temporary_path, original_stat.st_mode)
        if hasattr(os, "chown"):
            os.chown(temporary_path, original_stat.st_uid, original_stat.st_gid)
        os.replace(temporary_path, settings_path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
    return True
