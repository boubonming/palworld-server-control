"""Setup and environment-file support for palworld-server-docker."""

import os
import re
import secrets
import shutil
import subprocess


DEFAULT_COMPOSE = """services:
  palworld:
    image: thijsvanloef/palworld-server-docker:latest
    restart: unless-stopped
    container_name: palworld-server
    stop_grace_period: 60s
    ports:
      - "8211:8211/udp"
      - "27015:27015/udp"
      - "127.0.0.1:8212:8212/tcp"
    env_file:
      - .env
    volumes:
      - ./palworld:/palworld/
"""

DEFAULT_ENV = """PUID={puid}
PGID={pgid}
TZ=UTC
PORT=8211
QUERY_PORT=27015
PLAYERS=16
REST_API_ENABLED=true
REST_API_PORT=8212
ADMIN_PASSWORD={admin_password}
SERVER_NAME=Palworld Server
SERVER_DESCRIPTION=Managed by Palworld Server Control
BACKUP_ENABLED=true
UPDATE_ON_BOOT=true
"""

ENV_BACKUP_NAME = ".env.backup"
SPECIAL_SETTING_ENV_NAMES = {
    "ServerPlayerMaxNum": "PLAYERS",
    "DayTimeSpeedRate": "DAYTIME_SPEEDRATE",
    "NightTimeSpeedRate": "NIGHTTIME_SPEEDRATE",
    "PlayerStomachDecreaceRate": "PLAYER_STOMACH_DECREASE_RATE",
    "PlayerStaminaDecreaceRate": "PLAYER_STAMINA_DECREASE_RATE",
    "PlayerAutoHPRegeneRate": "PLAYER_AUTO_HP_REGEN_RATE",
    "PlayerAutoHpRegeneRateInSleep": "PLAYER_AUTO_HP_REGEN_RATE_IN_SLEEP",
    "PalStomachDecreaceRate": "PAL_STOMACH_DECREASE_RATE",
    "PalStaminaDecreaceRate": "PAL_STAMINA_DECREASE_RATE",
    "PalAutoHPRegeneRate": "PAL_AUTO_HP_REGEN_RATE",
    "PalAutoHpRegeneRateInSleep": "PAL_AUTO_HP_REGEN_RATE_IN_SLEEP",
    "bIsPvP": "IS_PVP",
    "bIsUseBackupSaveData": "USE_BACKUP_SAVE_DATA",
    "bUseAuth": "USEAUTH",
    "bEnableBuildingPlayerUIdDisplay": "ENABLE_BUILDING_PLAYER_UID_DISPLAY",
    "bDisplayPvPItemNumOnWorldMap_Player": "DISPLAY_PVP_ITEM_NUM_ON_WORLD_MAP_PLAYER",
    "bDisplayPvPItemNumOnWorldMap_BaseCamp": "DISPLAY_PVP_ITEM_NUM_ON_WORLD_MAP_BASE_CAMP",
    "AdditionalDropItemWhenPlayerKillingInPvPMode": (
        "ADDITIONAL_DROP_ITEM_WHEN_PLAYER_KILLING_IN_PVP_MODE"
    ),
    "AdditionalDropItemNumWhenPlayerKillingInPvPMode": (
        "ADDITIONAL_DROP_ITEM_NUM_WHEN_PLAYER_KILLING_IN_PVP_MODE"
    ),
    "bAdditionalDropItemWhenPlayerKillingInPvPMode": (
        "ADDITIONAL_DROP_ITEM_WHEN_PLAYER_KILLING_IN_PVP_MODE_ENABLED"
    ),
    "RESTAPIEnabled": "REST_API_ENABLED",
    "RESTAPIPort": "REST_API_PORT",
    "RCONEnabled": "RCON_ENABLED",
    "RCONPort": "RCON_PORT",
}


def create_deployment(directory):
    directory = os.path.abspath(os.path.expanduser(directory))
    os.makedirs(directory, exist_ok=True)
    compose_path = os.path.join(directory, "compose.yaml")
    env_path = os.path.join(directory, ".env")
    if os.path.exists(compose_path) or os.path.exists(env_path):
        raise FileExistsError(
            "compose.yaml or .env already exists. Use the existing-server setup instead."
        )
    with open(compose_path, "x", encoding="utf-8", newline="\n") as compose_file:
        compose_file.write(DEFAULT_COMPOSE)
    puid = os.getuid() if hasattr(os, "getuid") else 1000
    pgid = os.getgid() if hasattr(os, "getgid") else 1000
    initial_env = DEFAULT_ENV.format(
        puid=puid,
        pgid=pgid,
        admin_password=secrets.token_urlsafe(24),
    )
    with open(env_path, "x", encoding="utf-8", newline="\n") as env_file:
        env_file.write(initial_env)
    return compose_path


def validate_docker():
    subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )


def setting_to_env_name(setting):
    if setting in SPECIAL_SETTING_ENV_NAMES:
        return SPECIAL_SETTING_ENV_NAMES[setting]
    name = setting[1:] if len(setting) > 1 and setting[0] == "b" and setting[1].isupper() else setting
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.upper()


def read_env(path):
    values = {}
    if not path or not os.path.isfile(path):
        return values
    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[key.strip()] = value
    return values


def _serialize_env_value(value):
    value = str(value)
    if not value or any(character.isspace() for character in value) or "#" in value:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def update_env(path, updates, create_backup=True):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Docker environment file was not found: {path}")
    if create_backup:
        shutil.copy2(path, os.path.join(os.path.dirname(path), ENV_BACKUP_NAME))

    normalized = {str(key): _serialize_env_value(value) for key, value in updates.items()}
    output = []
    seen = set()
    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            stripped = raw_line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in normalized:
                    output.append(f"{key}={normalized[key]}\n")
                    seen.add(key)
                    continue
            output.append(raw_line if raw_line.endswith("\n") else raw_line + "\n")
    for key, value in normalized.items():
        if key not in seen:
            output.append(f"{key}={value}\n")
    with open(path, "w", encoding="utf-8", newline="\n") as env_file:
        env_file.writelines(output)


def backup_path(env_path):
    return os.path.join(os.path.dirname(env_path), ENV_BACKUP_NAME) if env_path else ""


def revert_env(env_path):
    saved_path = backup_path(env_path)
    if not os.path.isfile(saved_path):
        raise FileNotFoundError("No .env.backup file exists yet.")
    with open(env_path, "rb") as env_file:
        current = env_file.read()
    with open(saved_path, "rb") as backup_file:
        restored = backup_file.read()
    with open(saved_path, "wb") as backup_file:
        backup_file.write(current)
    with open(env_path, "wb") as env_file:
        env_file.write(restored)
