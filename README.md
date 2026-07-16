# Palworld Server Control

Palworld Server Control is a lightweight Windows desktop manager for a local Palworld dedicated server. It provides:

- Palworld server folder and `PalWorldSettings.ini` management
- Server status monitoring and settings editing
- Save, shutdown, and idle auto-stop controls through the local REST API
- Optional Discord bot controls for `!start`, `!stop`, and `!settings`
- System-tray and Windows-startup behavior

## Requirements

- Windows
- Python 3.10+
- A Palworld dedicated server installation
- Python packages listed in `requirements.txt`

Install dependencies with:

```powershell
pip install -r requirements.txt
```

## Running from source

Run the desktop app from the repository root:

```powershell
python src/main.py
```

On first launch, select the folder containing `PalServer.exe`. The manager derives the settings path from:

```text
<Palworld folder>\Pal\Saved\Config\WindowsServer\PalWorldSettings.ini
```

Application configuration is stored in `config.json` beside the executable when packaged, or in the repository root during development. Do not commit that file because it may contain the Discord token and server credentials.

## Project structure

```text
src/
  main.py                 Application entry point
  app.py                  Main window and lifecycle orchestration
  core/                   Configuration, API, INI, and Palworld domain logic
  integrations/           Discord bot lifecycle and commands
  ui/                     PySide6 pages and reusable widgets
  shared/                 Small cross-cutting helpers
```

## Network & Port Forwarding Setup

The ports below should be forwarded to the host running the Palworld server. Use a static LAN address for that host.

| Protocol | Default port | Purpose | Internet exposure |
| --- | ---: | --- | --- |
| UDP | `8211` | Palworld gameplay/listen port | Required for players |
| UDP | `27015` | Steam query/listing port commonly used for community-server discovery | Required for Steam/community listing |
| TCP | `8212` | Palworld REST API used by this manager | Keep local; do not forward publicly |

Port `27015` is the common Steam query port for community-server scanning, but the effective query port can depend on the server/launcher configuration. If you change it, forward the configured value instead. The official Palworld guide documents `-publiclobby`, `-publicip`, and `-publicport` for community servers, and notes that `-publicport` controls the advertised public port rather than the local listen port: [Palworld server configuration](https://docs.palworldgame.com/settings-and-operation/arguments/).

Only expose the gameplay and, when needed, Steam query ports. Keep the REST API bound to `127.0.0.1` or otherwise protected by a trusted firewall rule because it provides administrative server controls.

## Palworld server configuration

The manager expects the REST API to be enabled in `PalWorldSettings.ini`:

```ini
[/Script/Pal.PalGameSetting]
OptionSettings=(RESTAPIEnabled=True,RESTAPIPort=8212,AdminPassword="your_secure_admin_password_here")
```

For a community server, start PalServer with `-publiclobby`. Set `ServerName`, `PublicIP`, and `PublicPort` in the Palworld settings as appropriate for your network. The official community-server setup is documented [here](https://docs.palworldgame.com/getting-started/deploy-community-server/).

## Auto-stop behavior

The application-owned monitor checks player count once per minute while the server is running. If no players are detected for the configured duration, it saves the world and requests a graceful shutdown through the REST API. This works even when the Discord bot is disabled. If Discord is running, it additionally broadcasts the shutdown notice to configured control channels.

The duration defaults to 5 minutes to preserve the existing behavior and can be changed in **App Settings → Auto-stop after empty**. Values from 1 to 1,440 minutes are accepted.

## Discord integration

Configure the Discord bot token and one or more control channel IDs in the Discord page. The bot only accepts server-control commands from configured channels.

Available commands:

- `!start` — starts the configured Palworld server
- `!stop` — saves and requests a graceful shutdown
- `!settings` — displays selected server settings

The Discord bot can be started manually from the UI or automatically with the application.

## Packaging

For a Windows executable, package `src/main.py` with PyInstaller and include the `assets/` directory. Example:

```powershell
pyinstaller --onefile --noconsole --add-data "metadata.json;." --add-data "assets;assets" --name PalworldServerControl src/main.py
```

Keep the generated `config.json` beside the executable. Test the packaged build on the host machine before enabling Windows startup.
