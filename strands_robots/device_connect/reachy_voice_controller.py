#!/usr/bin/env python3
"""Voice-driven Reachy Mini controller device.

Runs as its own Device Connect device and invokes RPCs on a registered Reachy
Mini target. The controller subscribes to ``voiceCommandCaptured`` events from a
voice capture device and maps a small command grammar onto Reachy RPCs.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from typing import Optional

try:
    from device_connect_sdk import DeviceRuntime
    from device_connect_sdk.drivers import DeviceDriver, emit, on, rpc
    from device_connect_sdk.types import DeviceIdentity, DeviceStatus
except ImportError as exc:  # pragma: no cover - runtime guidance only
    raise SystemExit(
        "device_connect_sdk is required for this controller.\n"
        "Install a recent Device Connect build that includes "
        "`device_connect_sdk` and NATS_CREDENTIALS_FILE support."
    ) from exc

from strands_robots.device_connect.reachy_voice_core import ReachyVoiceCommandCore


class ReachyVoiceController(DeviceDriver):
    """Controller device that maps voice transcripts onto Reachy Mini RPCs."""

    device_type = "reachy_voice_controller"

    def __init__(
        self,
        target_device_id: str,
        source_device_id: Optional[str] = None,
        pitch_step: int = 5,
        yaw_step: int = 5,
        roll_step: int = 5,
        antenna_step: int = 10,
        min_confidence: float = 0.0,
    ) -> None:
        super().__init__()
        self._core = ReachyVoiceCommandCore(
            target_device_id=target_device_id,
            source_device_id=source_device_id,
            pitch_step=pitch_step,
            yaw_step=yaw_step,
            roll_step=roll_step,
            antenna_step=antenna_step,
            min_confidence=min_confidence,
            invoke_target=self._invoke_target,
            on_command_issued=self.commandIssued,
            on_command_result=self.commandResult,
        )

    @property
    def identity(self) -> DeviceIdentity:
        return DeviceIdentity(
            device_type=self.device_type,
            manufacturer="Strands",
            model="ReachyVoiceController",
            firmware_version="1.0.0",
            description="Voice-command controller for a remote Reachy Mini device",
        )

    @property
    def status(self) -> DeviceStatus:
        return DeviceStatus(location="voice-controller", availability="available")

    async def connect(self) -> None:
        source = self._core.source_device_id or "any voice capture device"
        print(
            f"Voice controller online. Target device: {self._core.target_device_id}. Source: {source}",
            flush=True,
        )

    async def disconnect(self) -> None:
        print("Voice controller offline.", flush=True)

    async def _invoke_target(self, target: str, fn: str, params: dict):
        return await self.invoke_remote(target, fn, **params)

    @emit()
    async def commandIssued(self, target: str, command: str, params: dict):
        """Emitted when the controller sends a command to Reachy."""
        pass

    @emit()
    async def commandResult(self, target: str, command: str, result: dict):
        """Emitted when the controller receives a result from Reachy."""
        pass

    @emit()
    async def voiceCommandProcessed(
        self,
        source: str,
        transcript: str,
        action: str,
        result: dict,
    ):
        """Emitted after a recognized voice command is forwarded to Reachy."""
        pass

    @emit()
    async def voiceCommandIgnored(
        self,
        source: str,
        transcript: str,
        reason: str,
    ):
        """Emitted when a transcript is rejected or does not map to a command."""
        pass

    @rpc()
    async def look(self, pitch: int = 0, yaw: int = 0, roll: int = 0) -> dict:
        return await self._core.look(pitch=pitch, yaw=yaw, roll=roll)

    @rpc()
    async def antennas(self, left: int = 0, right: int = 0) -> dict:
        return await self._core.antennas(left=left, right=right)

    @rpc()
    async def center(self) -> dict:
        return await self._core.center()

    @rpc()
    async def nod(self) -> dict:
        return await self._core.nod()

    @rpc()
    async def shake(self) -> dict:
        return await self._core.shake()

    @rpc()
    async def happy(self) -> dict:
        return await self._core.happy()

    @rpc()
    async def get_controller_state(self) -> dict:
        return self._core.get_controller_state()

    @rpc()
    async def handleVoiceCommand(
        self,
        transcript: str,
        confidence: float = 1.0,
        source_device_id: str = "",
    ) -> dict:
        payload = await self._core.handle_voice_command(
            transcript=transcript,
            confidence=confidence,
            source_device_id=source_device_id,
        )
        if payload["status"] == "success":
            await self.voiceCommandProcessed(
                source=payload["source"],
                transcript=payload["transcript"],
                action=payload["action"],
                result=payload["result"],
            )
        else:
            await self.voiceCommandIgnored(
                source=payload["source"],
                transcript=payload.get("transcript", transcript.strip()),
                reason=payload["reason"],
            )
        return payload

    @on(event_name="voiceCommandCaptured")
    async def onVoiceCommandCaptured(
        self,
        device_id: str,
        event_name: str,
        payload: dict,
    ):
        if not self._core.should_accept_source(device_id):
            await self.voiceCommandIgnored(
                source=device_id,
                transcript=str(payload.get("transcript", "")),
                reason="unexpected_source",
            )
            return

        transcript = str(payload.get("transcript", ""))
        confidence = float(payload.get("confidence", 1.0))
        await self.handleVoiceCommand(
            transcript=transcript,
            confidence=confidence,
            source_device_id=device_id,
        )


def _build_runtime(driver: ReachyVoiceController, args: argparse.Namespace) -> DeviceRuntime:
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
    driver = ReachyVoiceController(
        target_device_id=args.target_device_id,
        source_device_id=args.source_device_id,
        pitch_step=args.pitch_step,
        yaw_step=args.yaw_step,
        roll_step=args.roll_step,
        antenna_step=args.antenna_step,
        min_confidence=args.min_confidence,
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
    wait_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {runtime_task, wait_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    stop_event.set()
    if not runtime_task.done():
        await runtime.stop()

    for task in pending:
        task.cancel()
    for task in done | pending:
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
        "--source-device-id",
        help="Optional voice-capture device ID to trust. Defaults to any source.",
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
    parser.add_argument("--min-confidence", type=float, default=0.0)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
