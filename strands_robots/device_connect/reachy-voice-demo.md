# Reachy Mini Voice Demo

This demo extends the Reachy controller branch with a voice-driven control path.
The preferred demo flow keeps speech-to-text local on the Jetson and sends
Reachy RPCs directly over Device Connect. An optional Device Connect
`ReachyVoiceController` is also included for event-driven topologies.

## Demo Modes

### 1. Local voice pipeline (recommended for the demo)

- `reachy_voice_local.py` runs on the Jetson Orin Nano
- `arecord` captures audio from the USB microphone
- Vosk turns audio into text locally
- `ReachyVoiceCommandCore` parses phrases such as `look left` and
  `he looked left by seven degrees`
- Device Connect agent tools invoke Reachy RPCs on the registered robot device

### 2. Voice controller device (optional)

- `reachy_voice_controller.py` runs as its own Device Connect device
- It listens for `voiceCommandCaptured` events from an external voice capture
  service
- It uses the same shared parser/execution core as the local pipeline

## Components

| Component | File | Role |
|---|---|---|
| Shared command interpreter | `reachy_voice_core.py` | Normalizes transcripts, maintains pose state, maps voice phrases to Reachy RPCs |
| Device Connect voice controller | `reachy_voice_controller.py` | Optional event-driven controller device that forwards parsed commands to Reachy |
| Local voice runner | `reachy_voice_local.py` | Mic -> Vosk -> transcript log -> direct Reachy control |
| Reachy robot device | `reachy_mini_driver.py` | Exposes `look`, `antennas`, `nod`, `shake`, and related RPCs |
| Reachy Pi sidecar | `run_reachy_nats.py` in `reachy_device_connect/` | Bridges the local Reachy daemon into Device Connect over NATS |
| Reachy daemon | `reachy-mini-daemon` | Owns `/api/daemon/status` and `/ws/sdk` on the Reachy host |

## Architecture

```mermaid
graph LR
    subgraph Jetson["Jetson Orin Nano"]
        MIC["USB Microphone"]
        ARECORD["arecord"]
        VOSK["Vosk STT"]
        LOCAL["reachy_voice_local.py"]
        CORE["ReachyVoiceCommandCore"]
        AGENT["device_connect_agent_tools"]
        MIC --> ARECORD --> VOSK --> LOCAL --> CORE --> AGENT
    end

    subgraph Broker["NATS / Device Connect"]
        NATS["device-connect.<tenant>.*"]
    end

    subgraph Pi["Raspberry Pi / Reachy host"]
        SIDECAR["run_reachy_nats.py"]
        DRIVER["ReachyMiniDriver"]
        DAEMON["reachy-mini-daemon :8000"]
        REACHY["Reachy Mini"]
        SIDECAR --> DRIVER --> DAEMON --> REACHY
    end

    AGENT --> NATS --> SIDECAR
```

## End-to-End Demo Flow

1. Start the Reachy daemon on the Raspberry Pi or confirm the browser-control
   stack already owns `127.0.0.1:8000`.
2. Start the Reachy Device Connect sidecar on the Raspberry Pi with the
   commissioned Reachy device credentials.
3. Start the local voice runner on the Jetson with the controller credentials
   and a Vosk model path.
4. Speak commands such as `look left`, `look right`, or `look left by seven degrees`.
5. Watch the Jetson print `[final] ...` and `[command] ...` lines as the robot
   moves.

## Jetson Command

```bash
cd ~/workplace/robots

export MESSAGING_BACKEND=nats
export NATS_URL='nats://137.184.86.16:4222'
export NATS_CREDENTIALS_FILE='/home/sourav/workplace/robots/souravpati-controller-001.creds.json'
export DEVICE_CONNECT_ALLOW_INSECURE=true
export TENANT='souravpati'

./.venv/bin/python strands_robots/device_connect/reachy_voice_local.py \
  --model-path ~/workplace/robots/models/vosk-model-small-en-us-0.15 \
  --alsa-device plughw:0,0 \
  --target-device-id souravpati-reachy-mini-1 \
  --log-partials
```

## Raspberry Pi Sidecar Command

```bash
cd /home/pi/aifabric/reachy_device_connect
source .venv/bin/activate

export MESSAGING_BACKEND=nats
export NATS_URL='nats://137.184.86.16:4222'
export TENANT='souravpati'
export DEVICE_ID='souravpati-reachy-mini-1'
export NATS_CREDENTIALS_FILE='/home/pi/aifabric/reachy_device_connect/souravpati-reachy-mini-1.creds.json'
export DEVICE_CONNECT_ALLOW_INSECURE=true
export REACHY_HOST='127.0.0.1'
export REACHY_PORT='8000'
export REACHY_TRANSPORT_MODE='websocket'

./.venv/bin/python run_reachy_nats.py
```

## Recognized Phrases

- `look left`
- `look right`
- `look up`
- `look down`
- `yaw left`
- `yaw right`
- `pitch up`
- `pitch down`
- `roll left`
- `roll right`
- `look left by seven degrees`
- `yaw left by ten degrees`
- `center`
- `nod`
- `shake`
- `happy`

## Notes

- Vosk was chosen for the demo because it is light enough to run on the Jetson
  Orin Nano without the Whisper/CUDA setup overhead.
- The parser intentionally accepts observed Vosk transcript quirks such as
  `he looked left by seven degrees`.
- The local runner is not a Device Connect device; it only needs agent-side
  credentials and a reachable NATS broker.
