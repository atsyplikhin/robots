# Reachy Mini — Device Connect Guide

Connect a Reachy Mini Lite over USB, register it to a NATS-backed Device Connect tenant, and control it from a keyboard-driven controller device.

## Prerequisites

- Reachy Mini Lite plugged in via USB
- Python 3.12+, `uv` installed

## 1. Start the Reachy Daemon

The daemon bridges USB serial to a local REST/WebSocket API on port 9002.

```bash
# From the repo root (uses uv inline script, auto-installs reachy-mini)
python start_reachy_daemon.py
```

Expected output:

```
Starting reachy-mini-daemon on /dev/cu.usbmodemXXXX (API port 9002)
```

Leave this running in a separate terminal.

## 2. Clone and Set Up the Strands Robots SDK

```bash
git clone --branch feat/device-connect-integration-draft \
  https://github.com/atsyplikhin/robots.git
cd robots
./strands_robots/device_connect/setup.sh
source .venv/bin/activate
uv pip install websockets  # required dependency not yet in setup
```

## 3. Register the Reachy Mini to NATS

On the Reachy device, activate the repo environment and set the NATS + device credential variables:

```bash
cd /path/to/robots
source .venv/bin/activate

export MESSAGING_BACKEND=nats
export NATS_URL='nats://<nats-host>:4222'
export MESSAGING_URLS="$NATS_URL"
export TENANT='<tenant>'
export DEVICE_ID='<reachy-device-id>'
export NATS_CREDENTIALS_FILE='/path/to/<reachy-device-id>.creds.json'
export DEVICE_CONNECT_ALLOW_INSECURE=true

export REACHY_HOST='127.0.0.1'
export REACHY_PORT='8000'
export REACHY_TRANSPORT_MODE='websocket'
```

Start the Device Connect runtime:

```bash
python -c "
import asyncio, os
from strands_robots.device_connect import ReachyMiniDriver
from device_connect_sdk import DeviceRuntime

driver = ReachyMiniDriver(
    host=os.environ['REACHY_HOST'],
    api_port=int(os.environ['REACHY_PORT']),
    transport_mode=os.environ['REACHY_TRANSPORT_MODE'],
)
runtime = DeviceRuntime(
    driver=driver,
    device_id=os.environ['DEVICE_ID'],
    tenant=os.environ['TENANT'],
    messaging_urls=[os.environ['NATS_URL']],
    messaging_backend='nats',
    nats_credentials_file=os.environ['NATS_CREDENTIALS_FILE'],
    allow_insecure=True,
)
asyncio.run(runtime.run())
"
```

Expected output:

```
INFO - Using NATS messaging backend
INFO - Connected to NATS broker: ['nats://<nats-host>:4222']
INFO - Driver connected: reachy_mini
INFO - Device registered: registration_id=...
INFO - Subscribed to commands on device-connect.<tenant>.<reachy-device-id>.cmd
```

Leave this running. The Reachy is now registered as `<reachy-device-id>`.

## 4. Run the Keyboard Controller Device

On the Jetson controller machine, use a separate controller credential:

```bash
cd /path/to/robots
source .venv/bin/activate

export NATS_URL='nats://<nats-host>:4222'
export NATS_CREDENTIALS_FILE='/path/to/<controller-device-id>.creds.json'
export DEVICE_CONNECT_ALLOW_INSECURE=true

python strands_robots/device_connect/reachy_keyboard_controller.py \
  --device-id <controller-device-id> \
  --tenant <tenant> \
  --target-device-id <reachy-device-id>
```

This controller registers as its own device and uses `invoke_remote(...)` to call the Reachy RPCs.

### Keyboard controls

```text
w / s              look up / down
a / d              yaw left / right
z / x              roll left / right
j / l              move antennas
0                  reset antennas
c                  center head pose + antennas
nod                yes gesture
shake              no gesture
happy              antenna wiggle
look P Y [R]       absolute head pose
antennas L R       absolute antenna angles
quit               exit controller
```

## Reachy RPCs

| RPC | Parameters | Description |
|-----|-----------|-------------|
| `look` | `pitch`, `roll`, `yaw`, `x`, `y`, `z` | Set head pose (degrees / mm) |
| `antennas` | `left`, `right` | Set antenna angles (degrees) |
| `body` | `yaw` | Set body yaw (degrees) |
| `nod` | — | Yes gesture |
| `shake` | — | No gesture |
| `happy` | — | Antenna wiggle |
| `getJoints` | — | Current joint positions |
| `getImu` | — | IMU sensor data |
| `enableMotors` | `motor_ids` (optional) | Torque on |
| `disableMotors` | `motor_ids` (optional) | Torque off |
| `wakeUp` | — | Enable motors + wake animation |
| `sleep` | — | Sleep animation + disable motors |
| `stopMotion` | — | Stop all motion |
| `getDaemonStatus` | — | Daemon status and motor state |
| `playMove` | `move_name`, `library` | Play recorded move (`emotions` or `dance`) |
| `listMoves` | `library` | List available moves |

## Process Summary

You need **three terminals**:

| Terminal | Command | Purpose |
|----------|---------|---------|
| 1 | `python start_reachy_daemon.py` | USB serial daemon (port 9002) |
| 2 | Reachy runtime (step 3) | Registers the Reachy device to NATS |
| 3 | Keyboard controller (step 4) | Sends `look` / `antennas` / expression commands |

## Troubleshooting

- **`No USB serial device found`** — Check that Reachy is plugged in (`ls /dev/cu.usbmodem*`)
- **`ModuleNotFoundError: websockets`** — Run `uv pip install websockets`
- **`ModuleNotFoundError: device_connect_edge`** — Install a recent Device Connect build that includes `device_connect_edge`
- **`nats: no responders available for request`** — The Reachy runtime is not running, or `--target-device-id` does not match the registered Reachy device ID
- **`nats: permissions violation`** — The `tenant`, `device_id`, or NATS credential file does not match the commissioned device
- **Connection refused on port 9002** — Daemon not running; start it first (step 1)
