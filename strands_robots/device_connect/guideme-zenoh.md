# Connecting to the ECS Zenoh Cluster

Step-by-step guide to run a Strands Robot against the deployed Zenoh infrastructure.

## 1. Clone and install

```bash
git clone --branch feat/device-connect-integration-draft https://github.com/atsyplikhin/robots.git
cd robots
./strands_robots/device_connect/setup.sh
source .venv/bin/activate
```

## 2. Set environment variables

```bash
source strands_robots/device_connect/setup_zenoh.sh
```

This sets:

```
ZENOH_CONNECT=tcp/zenoh-nlb-2cb0b84309701828.elb.us-east-1.amazonaws.com:7447
ZENOH_MODE=client
DEVICE_CONNECT_ALLOW_INSECURE=true
```

> `ZENOH_MODE=client` is required when connecting to a remote router. Without it
> Zenoh defaults to peer mode, which causes the router to attempt direct P2P
> connections back to your machine (blocked by the VPC security group).

## 3. Start the robot

```bash
python -c "
from strands_robots import Robot
r = Robot('so100')
r.run()
"
```

Expected output:

```
device_connect_sdk.device.so100-<id> - INFO - Using ZENOH messaging backend
device_connect_sdk.device.so100-<id> - INFO - Connected to ZENOH broker: ['tcp/zenoh-nlb-2cb0b84309701828.elb.us-east-1.amazonaws.com:7447']
device_connect_sdk.device.so100-<id> - INFO - Device registered: registration_id=...
device_connect_sdk.device.so100-<id> - INFO - Subscribed to commands on device-connect.default.so100-<id>.cmd
```

Keep this terminal running. Open a new terminal for the next steps (activate the venv and source the setup script again).

## 4. Discover peers

```bash
python -c "
from strands_robots.tools.robot_mesh import robot_mesh
print(robot_mesh(action='peers'))
"
```

Expected output:

```
Discovered 1 device(s):
  [sim] so100-<id> — idle
    Functions: execute, getFeatures, getStatus, reset, step, stop
```

## 5. Send a command

Use the `so100-<id>` from the discover step:

```bash
python -c "
from strands_robots.tools.robot_mesh import robot_mesh
print(robot_mesh(action='tell', target='so100-<id>',
    instruction='pick up the cube', policy_provider='mock'))
"
```

Expected output:

```
-> so100-<id>: pick up the cube
  {"status": "success", "content": [{"text": "🚀 Policy started on 'so100' (async)"}]}
```

## 6. Emergency stop

```bash
python -c "
from strands_robots.tools.robot_mesh import robot_mesh
print(robot_mesh(action='emergency_stop'))
"
```
