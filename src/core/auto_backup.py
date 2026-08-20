"""Changed-only, rotating backups for Palworld world save data."""

from datetime import datetime
import hashlib
import json
import logging
import os
import threading
import time
import zipfile

from core import config_manager


logger = logging.getLogger(__name__)
BACKUP_FOLDER_NAME = "PalworldServerControl"
STATE_FILE_NAME = "backup-state.json"
ARCHIVE_PREFIX = "palworld-save-"


def get_save_games_path():
    """Returns the accessible SaveGames directory for the selected backend."""
    candidates = []
    if config_manager.is_socket_proxy_backend():
        candidates.append(os.path.join(os.sep, "palworld-saved", "SaveGames"))

    ini_path = config_manager.CONFIG.get("palworld_ini_path", "")
    if ini_path:
        saved_dir = os.path.dirname(os.path.dirname(os.path.dirname(ini_path)))
        candidates.append(os.path.join(saved_dir, "SaveGames"))

    palworld_dir = config_manager.CONFIG.get("palworld_dir", "")
    if palworld_dir:
        candidates.append(os.path.join(palworld_dir, "Pal", "Saved", "SaveGames"))

    for path in candidates:
        if os.path.isdir(path):
            return os.path.abspath(path)
    return os.path.abspath(candidates[0]) if candidates else ""


def get_backup_directory(save_games_path=None):
    configured = config_manager.get_auto_backup_directory()
    if configured:
        return configured
    save_games_path = save_games_path or get_save_games_path()
    if not save_games_path:
        return ""
    return os.path.join(
        os.path.dirname(save_games_path),
        "Backups",
        BACKUP_FOLDER_NAME,
    )


def _iter_save_files(save_games_path):
    for root, directories, filenames in os.walk(save_games_path):
        directories.sort()
        for filename in sorted(filenames):
            path = os.path.join(root, filename)
            if os.path.isfile(path):
                yield path, os.path.relpath(path, save_games_path)


def _content_hash(save_games_path):
    digest = hashlib.sha256()
    found_file = False
    for path, relative_path in _iter_save_files(save_games_path):
        found_file = True
        digest.update(relative_path.replace(os.sep, "/").encode("utf-8"))
        digest.update(b"\0")
        with open(path, "rb") as save_file:
            for chunk in iter(lambda: save_file.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest() if found_file else None


def _read_previous_hash(backup_directory):
    state_path = os.path.join(backup_directory, STATE_FILE_NAME)
    try:
        with open(state_path, "r", encoding="utf-8") as state_file:
            return json.load(state_file).get("content_hash")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_state(backup_directory, content_hash, archive_name):
    state_path = os.path.join(backup_directory, STATE_FILE_NAME)
    temporary_path = state_path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as state_file:
        json.dump(
            {
                "content_hash": content_hash,
                "archive": archive_name,
                "created_at": datetime.now().astimezone().isoformat(),
            },
            state_file,
            indent=2,
        )
    os.replace(temporary_path, state_path)


def _prune_archives(backup_directory, retention_count):
    archives = sorted(
        (
            filename
            for filename in os.listdir(backup_directory)
            if filename.startswith(ARCHIVE_PREFIX) and filename.endswith(".zip")
        ),
        reverse=True,
    )
    for filename in archives[retention_count:]:
        os.remove(os.path.join(backup_directory, filename))


def list_backups(backup_directory=None):
    """Returns existing backup archives, newest first."""
    backup_directory = backup_directory or get_backup_directory()
    if not backup_directory or not os.path.isdir(backup_directory):
        return []

    backups = []
    for filename in os.listdir(backup_directory):
        if not filename.startswith(ARCHIVE_PREFIX) or not filename.endswith(".zip"):
            continue
        path = os.path.join(backup_directory, filename)
        try:
            statistics = os.stat(path)
        except OSError:
            continue
        backups.append(
            {
                "name": filename,
                "size": statistics.st_size,
                "modified_at": datetime.fromtimestamp(statistics.st_mtime).astimezone(),
            }
        )
    return sorted(backups, key=lambda backup: backup["name"], reverse=True)


class AutoBackupService:
    """Creates atomic ZIP backups and skips save data already archived."""

    def __init__(self):
        self._lock = threading.Lock()

    def create_backup(self, request_save=True):
        with self._lock:
            save_games_path = get_save_games_path()
            if not save_games_path or not os.path.isdir(save_games_path):
                raise FileNotFoundError(
                    "Palworld SaveGames is unavailable. For a controller-only Docker "
                    "deployment, mount the Pal/Saved directory at /palworld-saved."
                )

            if request_save:
                from core import api_client

                status = api_client.call_palworld_api("save")
                if status not in (200, 202):
                    raise RuntimeError(
                        f"Server save request returned HTTP {status}."
                    )
                time.sleep(2)

            backup_directory = get_backup_directory(save_games_path)
            os.makedirs(backup_directory, exist_ok=True)
            content_hash = _content_hash(save_games_path)
            if content_hash is None:
                raise FileNotFoundError("Palworld SaveGames contains no save files.")
            if content_hash == _read_previous_hash(backup_directory):
                _prune_archives(
                    backup_directory,
                    config_manager.get_auto_backup_retention_count(),
                )
                logger.info("Automatic backup skipped because save data is unchanged")
                return None

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            archive_name = f"{ARCHIVE_PREFIX}{timestamp}.zip"
            archive_path = os.path.join(backup_directory, archive_name)
            temporary_path = archive_path + ".tmp"
            try:
                with zipfile.ZipFile(
                    temporary_path,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                ) as archive:
                    for path, relative_path in _iter_save_files(save_games_path):
                        archive.write(
                            path,
                            os.path.join("SaveGames", relative_path),
                        )

                with zipfile.ZipFile(temporary_path, "r") as archive:
                    if archive.testzip() is not None:
                        raise RuntimeError("The automatic backup ZIP failed verification.")

                if content_hash != _content_hash(save_games_path):
                    raise RuntimeError(
                        "Save data changed while the automatic backup archive "
                        "was being created."
                    )

                os.replace(temporary_path, archive_path)
                _write_state(backup_directory, content_hash, archive_name)
                _prune_archives(
                    backup_directory,
                    config_manager.get_auto_backup_retention_count(),
                )
                logger.info("Automatic backup created: %s", archive_path)
                return archive_path
            finally:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)


class AutoBackupMonitor:
    """Runs changed-only backups at the configured interval."""

    def __init__(self, service=None, poll_seconds=30):
        self.service = service or backup_service
        self.poll_seconds = poll_seconds
        self._last_attempt = 0.0
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="palworld-auto-backup",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self):
        thread = self._thread
        if thread is None:
            return False
        self._stop_event.set()
        if thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None
        return True

    def _run(self):
        while not self._stop_event.wait(self.poll_seconds):
            self.check_once()

    def check_once(self):
        if not config_manager.get_auto_backup_enabled():
            self._last_attempt = 0.0
            return None
        if not config_manager.is_server_process_running():
            self._last_attempt = 0.0
            return None

        now = time.monotonic()
        interval_seconds = config_manager.get_auto_backup_interval_minutes() * 60
        if self._last_attempt and now - self._last_attempt < interval_seconds:
            return None
        try:
            result = self.service.create_backup()
            self._last_attempt = now
            return result
        except Exception:
            logger.exception("Automatic Palworld backup failed")
            return None


backup_service = AutoBackupService()
