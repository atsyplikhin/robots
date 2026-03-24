# Connecting to the ECS NATS Cluster

Step-by-step guide to run a Strands Robot against the deployed NATS infrastructure.

## 1. Clone and install

```bash
git clone --branch feat/device-connect-integration-draft https://github.com/atsyplikhin/robots.git
cd robots
./strands_robots/device_connect/setup.sh
source .venv/bin/activate
```

## 2. Set environment variables

```bash
source strands_robots/device_connect/setup_nats.sh
```

This sets:

```
MESSAGING_BACKEND=nats
NATS_URL=nats://nats-nlb-6b2176379647decc.elb.us-east-1.amazonaws.com:4222
DEVICE_CONNECT_ALLOW_INSECURE=true
```

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
device_connect_sdk.device.so100-<id> - INFO - Using NATS messaging backend
device_connect_sdk.device.so100-<id> - INFO - Connected to NATS broker: ['nats://nats-nlb-6b2176379647decc.elb.us-east-1.amazonaws.com:4222']
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
