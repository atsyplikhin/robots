#!/usr/bin/env python3
"""Local Reachy voice capture runner.

Mic -> speech-to-text -> optional direct Reachy control.

By default this script is just a local process: it captures audio from ALSA,
transcribes it with Vosk, logs the recognized text, and optionally sends parsed
commands directly to a remote Reachy Mini over Device Connect agent tools.

When ``--device-id`` and ``--tenant`` are provided, it also starts an embedded
``ReachyVoiceController`` Device Connect runtime so the Jetson voice process
appears in discovery while keeping the mic/STT pipeline local.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from strands_robots.device_connect.reachy_voice_core import ReachyVoiceCommandCore


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-path",
        default=os.getenv("VOSK_MODEL_PATH", ""),
        help="Path to an unpacked Vosk model directory.",
    )
    parser.add_argument(
        "--alsa-device",
        default=os.getenv("VOICE_ALSA_DEVICE", "plughw:0,0"),
        help="ALSA capture device for arecord.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=int(os.getenv("VOICE_SAMPLE_RATE", "16000")),
        help="Sample rate in Hz.",
    )
    parser.add_argument(
        "--chunk-bytes",
        type=int,
        default=int(os.getenv("VOICE_CHUNK_BYTES", "4000")),
        help="Bytes to read from arecord per loop iteration.",
    )
    parser.add_argument(
        "--log-partials",
        action="store_true",
        help="Print interim partial transcripts.",
    )
    parser.add_argument(
        "--target-device-id",
        help="Reachy device ID to control. If omitted, run in transcript log-only mode.",
    )
    parser.add_argument(
        "--device-id",
        default=os.getenv("DEVICE_ID"),
        help="Optional controller device ID. If set with --tenant, register this local runner as a Device Connect device.",
    )
    parser.add_argument(
        "--tenant",
        default=os.getenv("TENANT"),
        help="Tenant namespace for the optional registered controller mode.",
    )
    parser.add_argument(
        "--nats-url",
        default=os.getenv("NATS_URL", "nats://localhost:4222"),
        help="NATS broker URL for the optional registered controller mode.",
    )
    parser.add_argument(
        "--nats-credentials-file",
        default=os.getenv("NATS_CREDENTIALS_FILE"),
        help="Credential file for the optional registered controller mode.",
    )
    parser.add_argument(
        "--source-device-id",
        default="local-mic",
        help="Logical source label attached to handled commands.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum confidence threshold for parsed commands.",
    )
    parser.add_argument("--pitch-step", type=int, default=5)
    parser.add_argument("--yaw-step", type=int, default=5)
    parser.add_argument("--roll-step", type=int, default=5)
    parser.add_argument("--antenna-step", type=int, default=10)
    return parser.parse_args(argv)


def _load_vosk(model_path: str, sample_rate: int):
    try:
        import vosk
    except ImportError as exc:  # pragma: no cover - runtime guidance only
        raise SystemExit(
            "vosk is required for local voice capture.\n"
            "Install it in the repo environment with:\n"
            "  pip install -r strands_robots/device_connect/requirements_voice_local.txt"
        ) from exc

    if not model_path:
        raise SystemExit(
            "VOSK_MODEL_PATH is not set and --model-path was not provided.\n"
            "Download and unpack a Vosk model, then point this script at that directory."
        )

    resolved = Path(model_path).expanduser()
    if not resolved.exists():
        raise SystemExit(f"Vosk model path does not exist: {resolved}")

    model = vosk.Model(str(resolved))
    recognizer = vosk.KaldiRecognizer(model, sample_rate)
    recognizer.SetWords(True)
    return recognizer


def _open_arecord(alsa_device: str, sample_rate: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            "arecord",
            "-D",
            alsa_device,
            "-f",
            "S16_LE",
            "-r",
            str(sample_rate),
            "-c",
            "1",
            "-t",
            "raw",
            "-q",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


def _ensure_connected():
    os.environ.setdefault("MESSAGING_BACKEND", "zenoh")
    os.environ.setdefault("DEVICE_CONNECT_ALLOW_INSECURE", "true")
    from device_connect_agent_tools.connection import connect, disconnect, get_connection

    zone = os.getenv("TENANT", "default")
    nats_url = os.getenv("NATS_URL")

    try:
        conn = get_connection()
        if getattr(conn, "zone", None) == zone:
            return conn
        disconnect()
    except Exception:
        pass

    connect(nats_url=nats_url, zone=zone)
    return get_connection()


def _build_core(args: argparse.Namespace) -> ReachyVoiceCommandCore:
    if not args.target_device_id:
        raise ValueError("target-device-id is required to build control core")

    conn = _ensure_connected()

    async def _invoke_target(target: str, fn: str, params: dict) -> dict:
        result = await asyncio.to_thread(conn.invoke, target, fn, params, timeout=30.0)
        return result.get("result", result)

    return ReachyVoiceCommandCore(
        target_device_id=args.target_device_id,
        invoke_target=_invoke_target,
        source_device_id=None,
        pitch_step=args.pitch_step,
        yaw_step=args.yaw_step,
        roll_step=args.roll_step,
        antenna_step=args.antenna_step,
        min_confidence=args.min_confidence,
    )


def _build_registered_handler(args: argparse.Namespace) -> tuple[Callable[[str], dict], Callable[[], None]]:
    if not args.target_device_id:
        raise ValueError("--target-device-id is required when registering the local voice runner")
    if not args.device_id or not args.tenant:
        raise ValueError("--device-id and --tenant are required for registered controller mode")

    from device_connect_sdk import DeviceRuntime

    from strands_robots.device_connect.reachy_voice_controller import ReachyVoiceController

    driver = ReachyVoiceController(
        target_device_id=args.target_device_id,
        pitch_step=args.pitch_step,
        yaw_step=args.yaw_step,
        roll_step=args.roll_step,
        antenna_step=args.antenna_step,
        min_confidence=args.min_confidence,
    )
    runtime_kwargs = {
        "driver": driver,
        "device_id": args.device_id,
        "tenant": args.tenant,
        "messaging_urls": [args.nats_url],
        "messaging_backend": "nats",
        "allow_insecure": True,
    }
    if args.nats_credentials_file:
        runtime_kwargs["nats_credentials_file"] = args.nats_credentials_file

    runtime = DeviceRuntime(**runtime_kwargs)
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def _run():
        asyncio.set_event_loop(loop)

        async def _start():
            runtime._background_task = asyncio.create_task(runtime.run())
            ready.set()

        loop.run_until_complete(_start())
        loop.run_forever()

    thread = threading.Thread(target=_run, daemon=True, name="reachy-voice-local-runtime")
    thread.start()
    ready.wait(timeout=30.0)

    runtime._loop = loop
    runtime._thread = thread

    print(
        f"Registered local voice controller as {args.device_id} on tenant {args.tenant}",
        flush=True,
    )

    def _handle(transcript: str) -> dict:
        future = asyncio.run_coroutine_threadsafe(
            driver.handleVoiceCommand(
                transcript=transcript,
                source_device_id=args.source_device_id,
            ),
            loop,
        )
        return future.result()

    def _shutdown() -> None:
        try:
            future = asyncio.run_coroutine_threadsafe(runtime.stop(), loop)
            future.result(timeout=10.0)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5.0)

    return _handle, _shutdown


def _build_local_handler(args: argparse.Namespace) -> tuple[Optional[Callable[[str], dict]], Callable[[], None]]:
    core = _build_core(args) if args.target_device_id else None

    if core is None:
        return None, lambda: None

    def _handle(transcript: str) -> dict:
        return asyncio.run(
            core.handle_voice_command(
                transcript=transcript,
                source_device_id=args.source_device_id,
            )
        )

    return _handle, lambda: None


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    recognizer = _load_vosk(args.model_path, args.sample_rate)
    arecord = _open_arecord(args.alsa_device, args.sample_rate)
    handle_command, shutdown = (
        _build_registered_handler(args)
        if args.device_id and args.tenant
        else _build_local_handler(args)
    )

    last_partial = ""
    print(
        f"Listening on {args.alsa_device} at {args.sample_rate} Hz"
        + (
            f" -> target {args.target_device_id} as device {args.device_id}"
            if args.target_device_id and args.device_id and args.tenant
            else f" -> target {args.target_device_id}"
            if args.target_device_id
            else " (log-only)"
        ),
        flush=True,
    )

    def _stop(*_args):
        raise KeyboardInterrupt

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _stop)

    try:
        assert arecord.stdout is not None
        while True:
            data = arecord.stdout.read(args.chunk_bytes)
            if not data:
                break

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()
                if not text:
                    continue

                print(f"[final] {text}", flush=True)
                if handle_command is None:
                    continue

                payload = handle_command(text)
                if payload["status"] == "success":
                    print(f"[command] {payload['action']} -> {payload['result']}", flush=True)
                else:
                    print(f"[ignored] {payload['reason']} :: {text}", flush=True)
            elif args.log_partials:
                partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
                if partial and partial != last_partial:
                    last_partial = partial
                    print(f"[partial] {partial}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        if arecord.poll() is None:
            arecord.terminate()
            try:
                arecord.wait(timeout=2)
            except subprocess.TimeoutExpired:
                arecord.kill()
        shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
