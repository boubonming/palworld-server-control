# Palworld Server Control

Palworld Server Control is a lightweight manager for a Palworld dedicated server. The desktop app supports a native Windows server or a local Docker Compose server on Windows and Linux. A headless controller is also available for `thijsvanloef/palworld-server-docker`.

- Palworld server folder and `PalWorldSettings.ini` management
- Server status monitoring and settings editing
- Save, shutdown, and idle auto-stop controls through the local REST API
- Optional Discord bot controls for `!start`, `!stop`, and `!settings`
- System-tray and Windows-startup behavior

## Requirements

- Windows for the native desktop workflow, or Windows/Linux for Docker mode
- Python 3.10+
- A Palworld dedicated server installation
- Python packages listed in `requirements.txt` for desktop mode

Install dependencies with:

```powershell
pip install -r requirements.txt
```

Linux controller dependencies are kept separate and do not include PySide6:

```bash
pip install -r requirements-controller.txt
```

## Running from source

Run the desktop app from the repository root:

```powershell
python src/main.py
```

On first launch, choose a native Windows server or Docker Compose. Native mode derives the settings path from:

```text
<Palworld folder>\Pal\Saved\Config\WindowsServer\PalWorldSettings.ini
```

## Docker controller, Socket Proxy, and web interface

The recommended deployment uses two independent stacks: your Palworld server stack, plus a control stack containing Palworld Server Control and a restricted Docker Socket Proxy. This lets Palworld and the controller be updated or recreated independently. An optional all-in-one stack is also provided for new installations.

The control stack expects:

- An existing `thijsvanloef/palworld-server-docker` container named `palworld-server`
- A shared external Docker network named `palworld-control`
- The Palworld configuration directory mounted into the controller
- Palworld REST API enabled and reachable as `palworld-server`
- `DISABLE_GENERATE_SETTINGS=true` on the Palworld container

The GitHub Actions workflow in `.github/workflows/controller-image.yml` publishes `ghcr.io/boubonming/palworld-server-control:latest` from `main`, plus version and commit tags. Make that GHCR package public, or add its credentials to Portainer's registry configuration.

Create the shared network and attach the existing Palworld service to it. Copy [`deploy/controller-stack.env.example`](deploy/controller-stack.env.example) to `.env`, set the web password and existing Palworld configuration directory, then deploy the control stack:

```bash
docker network create palworld-control
docker compose --env-file .env -f deploy/controller-stack.yaml up -d
```

If the existing Palworld Compose file does not already use `palworld-control`, add it as an external network to that service and redeploy the Palworld stack.

### Optional all-in-one stack

For a new installation, [`deploy/all-in-one-stack.yaml`](deploy/all-in-one-stack.yaml) creates Palworld, the controller, and Socket Proxy together. Copy [`deploy/all-in-one-stack.env.example`](deploy/all-in-one-stack.env.example) to `.env`, configure it, and deploy:

```bash
docker compose --env-file .env -f deploy/all-in-one-stack.yaml up -d
```

On its first deployment, leave `PALWORLD_DISABLE_GENERATE_SETTINGS=false` so the Palworld image creates `PalWorldSettings.ini`. After Palworld starts successfully, change it to `true` and redeploy once before changing settings through the controller. In **Docker setup**, use `/palworld-data/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini` as the mounted INI path.

The stack automatically pulls and creates `lscr.io/linuxserver/socket-proxy`. Its port is not published, its filesystem is read-only, and its network is internal to the controller. General Docker POST access remains disabled; only container start and stop exceptions are enabled.

Open `http://<linux-server-private-ip>:8080` from your personal PC, or use the port selected by `CONTROLLER_WEB_PORT`. Keep this port restricted to a trusted LAN or private VPN; it is not intended for direct public-internet exposure. The Palworld REST API remains available only on the private Compose network and is not published to the host.

In **Docker setup**, verify:

- Socket Proxy URL, normally `http://socket-proxy:2375`
- Palworld container name, normally `palworld-server`
- Mounted INI path, normally `/palworld-config/PalWorldSettings.ini` for the recommended two-stack deployment
- Palworld REST hostname, normally `palworld-server`

Server settings are written directly to the mounted INI while Palworld is stopped. A stop first calls Palworld's REST save endpoint and proceeds only when that succeeds. It then asks Socket Proxy to stop the container with a 60-second timeout, allowing the image's normal `SIGTERM` shutdown handling to run. Docker's `unless-stopped` policy respects this intentional stop.

Application configuration is stored in `/data/config.json` in the controller container. The Windows desktop behavior and native server backend remain unchanged.

## Project structure

```text
src/
  main.py                 Desktop compatibility entry point
  server_main.py          Controller compatibility entry point
  desktop/                PySide6 app, pages, and desktop lifecycle
  controller/             Headless runtime and web interface
  core/                   Configuration, API, INI, and Palworld domain logic
  integrations/           Discord bot lifecycle and commands
  shared/                 Toolkit-neutral events and cross-cutting helpers
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
