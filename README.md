# Palworld Server Control

Palworld Server Control is a lightweight manager for a Palworld dedicated server. It supports the existing native Windows desktop workflow and a Linux headless controller for `thijsvanloef/palworld-server-docker`.

- Palworld server folder and `PalWorldSettings.ini` management
- Server status monitoring and settings editing
- Save, shutdown, and idle auto-stop controls through the local REST API
- Optional Discord bot controls for `!start`, `!stop`, and `!settings`
- System-tray and Windows-startup behavior

## Requirements

- Windows for the native desktop workflow, or Linux for Docker/web mode
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

## Linux controller, Socket Proxy, and web interface

Linux mode runs this controller and LinuxServer Socket Proxy as a small stack. The controller keeps the Discord bot and idle-shutdown monitor on the server and exposes a password-protected web interface to your private network. Only Socket Proxy mounts the Docker socket; the controller receives narrowly filtered container status, start, and stop access.

Prerequisites:

- An existing `thijsvanloef/palworld-server-docker` container named `palworld-server`
- A shared external Docker network, such as `palworld-control`, attached to both the controller and Palworld services
- Palworld REST API enabled and reachable from the controller network
- `DISABLE_GENERATE_SETTINGS=true` on the Palworld container
- The host directory containing `PalWorldSettings.ini`

The GitHub Actions workflow in `.github/workflows/controller-image.yml` publishes `ghcr.io/boubonming/palworld-server-control:latest` after changes reach `main`. Make that GHCR package public, or add its credentials to Portainer's registry configuration. Create the external `palworld-control` network and attach the Palworld service to it. Then deploy [`deploy/controller-stack.yaml`](deploy/controller-stack.yaml) through Portainer or Docker Compose with these stack variables:

- `PALWORLD_CONTROL_WEB_PASSWORD`: web password of at least ten characters
- `PALWORLD_CONFIG_DIR`: host path ending in `Pal/Saved/Config/LinuxServer`

The stack automatically pulls and creates `lscr.io/linuxserver/socket-proxy`. Its port is not published, its filesystem is read-only, and its network is internal to the controller. General Docker POST access remains disabled; only container start and stop exceptions are enabled.

Open `http://<linux-server-private-ip>:8080` from your personal PC. Keep this port restricted to a trusted LAN or private VPN; it is not intended for direct public-internet exposure.

In **Docker setup**, verify:

- Socket Proxy URL, normally `http://socket-proxy:2375`
- Palworld container name, normally `palworld-server`
- Mounted INI path, normally `/palworld-config/PalWorldSettings.ini`
- Palworld REST hostname on the shared Docker network

Server settings are written directly to the mounted INI while Palworld is stopped. A stop first calls Palworld's REST save endpoint and proceeds only when that succeeds. It then asks Socket Proxy to stop the container with a 60-second timeout, allowing the image's normal `SIGTERM` shutdown handling to run. Docker's `unless-stopped` policy respects this intentional stop.

Application configuration is stored in `/data/config.json` in the controller container. The Windows desktop behavior and native server backend remain unchanged.

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

Idle shutdown is enabled by default and can be toggled in **App Settings → Idle shutdown**. Its duration defaults to 5 minutes, and values from 1 to 1,440 minutes are accepted.

## Discord integration

Configure the Discord bot token and one or more control channel IDs in the Discord page. The bot only accepts server-control commands from configured channels.

Available commands:

- `!start` — starts the server using the saved idle-shutdown setting
- `!start <minutes>` — starts the server with idle shutdown enabled at that duration for this session only
- `!start off` — starts the server without idle shutdown for this session only
- `!stop` — saves and requests a graceful shutdown
- `!settings` — displays server settings
- `!help` — displays the available Discord commands

The Discord bot can be started manually from the UI or automatically with the application.

## Packaging

For a Windows executable, package `src/main.py` with PyInstaller and include the `assets/` directory. Example:

```powershell
pyinstaller --onefile --noconsole --add-data "metadata.json;." --add-data "assets;assets" --name PalworldServerControl src/main.py
```

or

```powershell
pyinstaller --clean PalworldServerControl.spec
```

Keep the generated `config.json` beside the executable. Test the packaged build on the host machine before enabling Windows startup.
