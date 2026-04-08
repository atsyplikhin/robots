#!/usr/bin/env python3
"""Keyboard-driven Reachy Mini controller device.

Runs as its own Device Connect device and invokes RPCs on a registered Reachy
Mini target. This follows the greenhouse-demo pattern: the controller is a
device runtime with its own credentials, and it uses ``invoke_remote(...)``
for control instead of the older agent-tools step-4 flow.

Expected environment for NATS JWT auth:

    export NATS_URL='nats://<nats-host>:4222'
    export NATS_CREDENTIALS_FILE='/path/to/<controller-device-id>.creds.json'
    export DEVICE_CONNECT_ALLOW_INSECURE=true

Example:

    python strands_robots/device_connect/reachy_keyboard_controller.py \
      --device-id <controller-device-id> \
      --tenant <tenant> \
      --target-device-id <reachy-device-id>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from typing import Optional

try:
    from device_connect_edge import DeviceRuntime
    from device_connect_edge.drivers import DeviceDriver, emit, rpc
    from device_connect_edge.types import DeviceIdentity, DeviceStatus
except ImportError as exc:  # pragma: no cover - runtime guidance only
    raise SystemExit(
        "device_connect_edge is required for this controller.\n"
        "Install a recent Device Connect build that includes "
        "`device_connect_edge` and NATS_CREDENTIALS_FILE support."
    ) from exc


class ReachyKeyboardController(DeviceDriver):
    """Controller device that invokes Reachy Mini RPCs on a remote target."""

    device_type = "reachy_keyboard_controller"

    def __init__(
        self,
        target_device_id: str,
        pitch_step: int = 5,
        yaw_step: int = 5,
        roll_step: int = 5,
        antenna_step: int = 10,
    ) -> None:
        super().__init__()
        self._target = target_device_id
        self._pitch = 0
        self._yaw = 0
        self._roll = 0
        self._left_antenna = 0
        self._right_antenna = 0
        self._pitch_step = pitch_step
        self._yaw_step = yaw_step
        self._roll_step = roll_step
        self._antenna_step = antenna_step

    @property
    def identity(self) -> DeviceIdentity:
        return DeviceIdentity(
            device_type=self.device_type,
            manufacturer="Strands",
            model="ReachyKeyboardController",
            firmware_version="1.0.0",
            description="Keyboard controller for a remote Reachy Mini device",
        )

    @property
    def status(self) -> DeviceStatus:
        return DeviceStatus(location="jetson-terminal", availability="available")

    async def connect(self) -> None:
        print(f"Controller online. Target device: {self._target}", flush=True)

    async def disconnect(self) -> None:
        print("Controller offline.", flush=True)

    async def _invoke(self, fn: str, **params):
        await self.commandIssued(target=self._target, command=fn, params=params)
        result = await self.invoke_remote(self._target, fn, **params)
        await self.commandResult(target=self._target, command=fn, result=result)
        return result

    @emit()
    async def commandIssued(self, target: str, command: str, params: dict):
        """Emitted when the controller sends a command to Reachy."""
        pass

    @emit()
    async def commandResult(self, target: str, command: str, result: dict):
        """Emitted when the controller receives a result from Reachy."""
        pass

    async def _send_look(self):
        return await self._invoke(
            "look",
            pitch=self._pitch,
            yaw=self._yaw,
            roll=self._roll,
        )

    async def _send_antennas(self):
        return await self._invoke(
            "antennas",
            left=self._left_antenna,
            right=self._right_antenna,
        )

    @rpc()
    async def look(self, pitch: int = 0, yaw: int = 0, roll: int = 0) -> dict:
        self._pitch = pitch
        self._yaw = yaw
        self._roll = roll
        result = await self._send_look()
        return {
            "target": self._target,
            "pose": {"pitch": self._pitch, "yaw": self._yaw, "roll": self._roll},
            "result": result,
        }

    @rpc()
    async def antennas(self, left: int = 0, right: int = 0) -> dict:
        self._left_antenna = left
        self._right_antenna = right
        result = await self._send_antennas()
        return {
            "target": self._target,
            "antennas": {"left": self._left_antenna, "right": self._right_antenna},
            "result": result,
        }

    @rpc()
    async def center(self) -> dict:
        self._pitch = 0
        self._yaw = 0
        self._roll = 0
        self._left_antenna = 0
        self._right_antenna = 0
        look_result = await self._send_look()
        antenna_result = await self._send_antennas()
        return {
            "target": self._target,
            "look_result": look_result,
            "antenna_result": antenna_result,
        }

    @rpc()
    async def nod(self) -> dict:
        return await self._invoke("nod")

    @rpc()
    async def shake(self) -> dict:
        return await self._invoke("shake")

    @rpc()
    async def happy(self) -> dict:
        return await self._invoke("happy")

    @rpc()
    async def get_controller_state(self) -> dict:
        return {
            "target": self._target,
            "pose": {"pitch": self._pitch, "yaw": self._yaw, "roll": self._roll},
            "antennas": {"left": self._left_antenna, "right": self._right_antenna},
        }

    async def handle_command(self, raw: str) -> bool:
        cmd = raw.strip()
        if not cmd:
            return True

        if cmd in {"q", "quit", "exit"}:
            return False

        if cmd in {"h", "help", "?"}:
            print(_HELP_TEXT, flush=True)
            return True

        if cmd in {"state", "status"}:
            print(await self.get_controller_state(), flush=True)
            return True

        if cmd == "w":
            self._pitch -= self._pitch_step
            print(await self._send_look(), flush=True)
            return True
        if cmd == "s":
            self._pitch += self._pitch_step
            print(await self._send_look(), flush=True)
            return True
        if cmd == "a":
            self._yaw -= self._yaw_step
            print(await self._send_look(), flush=True)
            return True
        if cmd == "d":
            self._yaw += self._yaw_step
            print(await self._send_look(), flush=True)
            return True
        if cmd == "z":
            self._roll -= self._roll_step
            print(await self._send_look(), flush=True)
            return True
        if cmd == "x":
            self._roll += self._roll_step
            print(await self._send_look(), flush=True)
            return True
        if cmd == "c":
            print(await self.center(), flush=True)
            return True
        if cmd == "j":
            self._left_antenna -= self._antenna_step
            self._right_antenna += self._antenna_step
            print(await self._send_antennas(), flush=True)
            return True
        if cmd == "l":
            self._left_antenna += self._antenna_step
            self._right_antenna -= self._antenna_step
            print(await self._send_antennas(), flush=True)
            return True
        if cmd == "0":
            self._left_antenna = 0
            self._right_antenna = 0
            print(await self._send_antennas(), flush=True)
            return True
        if cmd == "nod":
            print(await self.nod(), flush=True)
            return True
        if cmd == "shake":
            print(await self.shake(), flush=True)
            return True
        if cmd == "happy":
            print(await self.happy(), flush=True)
            return True

        parts = cmd.split()
        if parts[0] == "look" and len(parts) in {3, 4}:
            pitch = int(parts[1])
            yaw = int(parts[2])
            roll = int(parts[3]) if len(parts) == 4 else 0
            print(await self.look(pitch=pitch, yaw=yaw, roll=roll), flush=True)
            return True

        if parts[0] == "antennas" and len(parts) == 3:
            left = int(parts[1])
            right = int(parts[2])
            print(await self.antennas(left=left, right=right), flush=True)
            return True

        print(f"Unknown command: {cmd}", flush=True)
        print("Type `help` to see available commands.", flush=True)
        return True


_HELP_TEXT = """
Commands:
  w / s              look up / down (pitch step)
  a / d              yaw left / right (yaw step)
  z / x              roll left / right (roll step)
  j / l              antennas preset adjust
  0                  reset antennas to 0,0
  c                  center head pose and antennas
  nod                yes gesture
  shake              no gesture
  happy              antenna wiggle
  state              print local controller state
  look P Y [R]       set absolute pose
  antennas L R       set absolute antenna angles
  help               print this help
  quit               exit controller
""".strip()


async def _keyboard_loop(driver: ReachyKeyboardController, stop_event: asyncio.Event) -> None:
    print(_HELP_TEXT, flush=True)
    while not stop_event.is_set():
        try:
            raw = await asyncio.to_thread(input, "reachy> ")
        except EOFError:
            stop_event.set()
            break
        except KeyboardInterrupt:
            stop_event.set()
            break

        try:
            keep_running = await driver.handle_command(raw)
        except Exception as exc:  # pragma: no cover - runtime behavior only
            print(f"Command failed: {exc}", flush=True)
            continue

        if not keep_running:
            stop_event.set()
            break


def _build_runtime(driver: ReachyKeyboardController, args: argparse.Namespace) -> DeviceRuntime:
    kwargs = {
        "driver": driver,
        "device_id": args.device_id,
        "tenant": args.tenant,
        "messaging_urls": [args.nats_url],
        "messaging_backend": "nats",
        "allow_insecure": True,
    }

    creds_file = args.nats_credentials_file or os.getenv("NATS_CREDENTIALS_FILE")
    if creds_file:
        kwargs["nats_credentials_file"] = creds_file

    return DeviceRuntime(**kwargs)


async def _run(args: argparse.Namespace) -> None:
    driver = ReachyKeyboardController(
        target_device_id=args.target_device_id,
        pitch_step=args.pitch_step,
        yaw_step=args.yaw_step,
        roll_step=args.roll_step,
        antenna_step=args.antenna_step,
    )
    runtime = _build_runtime(driver, args)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover - non-posix
            pass

    runtime_task = asyncio.create_task(runtime.run())
    keyboard_task = asyncio.create_task(_keyboard_loop(driver, stop_event))

    done, pending = await asyncio.wait(
        {runtime_task, keyboard_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    stop_event.set()

    if not runtime_task.done():
        await runtime.stop()

    for task in pending:
        task.cancel()
    for task in done | pending:
        if task is runtime_task:
            try:
                await task
            except asyncio.CancelledError:
                pass
        else:
            try:
                await task
            except asyncio.CancelledError:
                pass


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device-id",
        required=True,
        help="Controller device ID. Use a controller credential that matches this ID.",
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="Tenant namespace, for example '<tenant>'.",
    )
    parser.add_argument(
        "--target-device-id",
        required=True,
        help="Reachy device ID to control, for example '<reachy-device-id>'.",
    )
    parser.add_argument(
        "--nats-url",
        default=os.getenv("NATS_URL", "nats://localhost:4222"),
        help="NATS broker URL.",
    )
    parser.add_argument(
        "--nats-credentials-file",
        default=os.getenv("NATS_CREDENTIALS_FILE"),
        help="Path to the controller .creds.json or .creds file.",
    )
    parser.add_argument("--pitch-step", type=int, default=5)
    parser.add_argument("--yaw-step", type=int, default=5)
    parser.add_argument("--roll-step", type=int, default=5)
    parser.add_argument("--antenna-step", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
