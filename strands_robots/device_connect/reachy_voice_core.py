"""Shared Reachy voice command parsing and execution."""

from __future__ import annotations

import re
from typing import Awaitable, Callable, Optional


_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

_IGNORED_AMOUNT_TOKENS = {"by", "degree", "degrees"}
_LEADING_FILLER_TOKENS = {"hey", "he"}
_TOKEN_ALIASES = {
    "looked": "look",
    "your": "yaw",
    "yeah": "yaw",
}

TargetInvoker = Callable[[str, str, dict], Awaitable[dict]]
CommandHook = Callable[[str, str, dict], Awaitable[None]]


class ReachyVoiceCommandCore:
    """Stateful voice-command interpreter for Reachy RPCs."""

    def __init__(
        self,
        target_device_id: str,
        invoke_target: TargetInvoker,
        source_device_id: Optional[str] = None,
        pitch_step: int = 5,
        yaw_step: int = 5,
        roll_step: int = 5,
        antenna_step: int = 10,
        min_confidence: float = 0.0,
        on_command_issued: Optional[CommandHook] = None,
        on_command_result: Optional[CommandHook] = None,
    ) -> None:
        self.target_device_id = target_device_id
        self.source_device_id = source_device_id
        self.min_confidence = min_confidence

        self._invoke_target = invoke_target
        self._on_command_issued = on_command_issued
        self._on_command_result = on_command_result

        self._pitch = 0
        self._yaw = 0
        self._roll = 0
        self._left_antenna = 0
        self._right_antenna = 0
        self._pitch_step = pitch_step
        self._yaw_step = yaw_step
        self._roll_step = roll_step
        self._antenna_step = antenna_step

    def should_accept_source(self, source_device_id: str) -> bool:
        return not self.source_device_id or source_device_id == self.source_device_id

    def get_controller_state(self) -> dict:
        return {
            "target": self.target_device_id,
            "source_device_id": self.source_device_id,
            "min_confidence": self.min_confidence,
            "pose": {"pitch": self._pitch, "yaw": self._yaw, "roll": self._roll},
            "antennas": {"left": self._left_antenna, "right": self._right_antenna},
        }

    async def handle_voice_command(
        self,
        transcript: str,
        confidence: float = 1.0,
        source_device_id: str = "",
    ) -> dict:
        source = source_device_id or "manual"
        text = transcript.strip()
        if not text:
            return {"status": "ignored", "reason": "empty", "source": source}

        if confidence < self.min_confidence:
            return {
                "status": "ignored",
                "reason": "low_confidence",
                "source": source,
                "confidence": confidence,
            }

        action = self.parse_voice_command(text)
        if action is None:
            return {
                "status": "ignored",
                "reason": "unrecognized_command",
                "source": source,
                "transcript": text,
            }

        result = await self._execute_action(action)
        return {
            "status": "success",
            "source": source,
            "transcript": text,
            "action": action["label"],
            "target": self.target_device_id,
            "result": result,
        }

    def parse_voice_command(self, transcript: str) -> Optional[dict]:
        normalized = self._normalize_text(transcript)
        if not normalized:
            return None

        tokens = self._canonicalize_tokens(normalized.split())
        if not tokens:
            return None
        normalized = " ".join(tokens)

        if normalized in {"center", "centre", "home", "reset", "center head", "centre head"}:
            return {"kind": "center", "label": "center"}
        if normalized in {"nod", "shake", "happy"}:
            return {"kind": normalized, "label": normalized}
        if normalized in {"antennas center", "center antennas", "reset antennas"}:
            return {
                "kind": "antennas_absolute",
                "left": 0,
                "right": 0,
                "label": "antennas_center",
            }

        if tokens[0] == "look" and len(tokens) in {3, 4}:
            values = [self._parse_number_token(token) for token in tokens[1:]]
            if any(value is None for value in values):
                return None
            while len(values) < 3:
                values.append(0)
            return {
                "kind": "look_absolute",
                "pitch": values[0],
                "yaw": values[1],
                "roll": values[2],
                "label": "look_absolute",
            }

        if tokens[0] == "antennas" and len(tokens) == 3:
            left = self._parse_number_token(tokens[1])
            right = self._parse_number_token(tokens[2])
            if left is None or right is None:
                return None
            return {
                "kind": "antennas_absolute",
                "left": left,
                "right": right,
                "label": "antennas_absolute",
            }

        return self._parse_incremental_command(tokens)

    async def look(self, pitch: int = 0, yaw: int = 0, roll: int = 0) -> dict:
        self._pitch = pitch
        self._yaw = yaw
        self._roll = roll
        result = await self._send_look()
        return {
            "target": self.target_device_id,
            "pose": {"pitch": self._pitch, "yaw": self._yaw, "roll": self._roll},
            "result": result,
        }

    async def antennas(self, left: int = 0, right: int = 0) -> dict:
        self._left_antenna = left
        self._right_antenna = right
        result = await self._send_antennas()
        return {
            "target": self.target_device_id,
            "antennas": {"left": self._left_antenna, "right": self._right_antenna},
            "result": result,
        }

    async def center(self) -> dict:
        self._pitch = 0
        self._yaw = 0
        self._roll = 0
        self._left_antenna = 0
        self._right_antenna = 0
        look_result = await self._send_look()
        antenna_result = await self._send_antennas()
        return {
            "target": self.target_device_id,
            "look_result": look_result,
            "antenna_result": antenna_result,
        }

    async def nod(self) -> dict:
        return await self._invoke("nod")

    async def shake(self) -> dict:
        return await self._invoke("shake")

    async def happy(self) -> dict:
        return await self._invoke("happy")

    async def _invoke(self, fn: str, **params) -> dict:
        if self._on_command_issued:
            await self._on_command_issued(self.target_device_id, fn, params)
        result = await self._invoke_target(self.target_device_id, fn, params)
        if self._on_command_result:
            await self._on_command_result(self.target_device_id, fn, result)
        return result

    async def _send_look(self) -> dict:
        return await self._invoke(
            "look",
            pitch=self._pitch,
            yaw=self._yaw,
            roll=self._roll,
        )

    async def _send_antennas(self) -> dict:
        return await self._invoke(
            "antennas",
            left=self._left_antenna,
            right=self._right_antenna,
        )

    async def _execute_action(self, action: dict) -> dict:
        kind = action["kind"]
        if kind == "center":
            return await self.center()
        if kind == "nod":
            return await self.nod()
        if kind == "shake":
            return await self.shake()
        if kind == "happy":
            return await self.happy()
        if kind == "look_absolute":
            return await self.look(
                pitch=action["pitch"],
                yaw=action["yaw"],
                roll=action["roll"],
            )
        if kind == "antennas_absolute":
            return await self.antennas(left=action["left"], right=action["right"])
        if kind == "look_delta":
            axis = action["axis"]
            setattr(self, f"_{axis}", getattr(self, f"_{axis}") + action["delta"])
            return await self._send_look()
        if kind == "antennas_delta":
            self._left_antenna += action["left_delta"]
            self._right_antenna += action["right_delta"]
            return await self._send_antennas()
        raise ValueError(f"Unsupported action: {kind}")

    def _parse_incremental_command(self, tokens: list[str]) -> Optional[dict]:
        axis_aliases = {
            "yaw": "yaw",
            "turn": "yaw",
            "pitch": "pitch",
            "roll": "roll",
        }
        direction_aliases = {
            "left": -1,
            "right": 1,
            "up": -1,
            "down": 1,
        }

        if len(tokens) >= 2 and tokens[0] in axis_aliases and tokens[1] in direction_aliases:
            axis = axis_aliases[tokens[0]]
            direction = tokens[1]
            amount = self._parse_amount(tokens[2:], axis)
            if amount is None:
                return None
            if axis == "yaw" and direction not in {"left", "right"}:
                return None
            if axis == "roll" and direction not in {"left", "right"}:
                return None
            if axis == "pitch" and direction not in {"up", "down"}:
                return None
            return {
                "kind": "look_delta",
                "axis": axis,
                "delta": direction_aliases[direction] * amount,
                "label": f"{axis}_{direction}",
            }

        if len(tokens) >= 2 and tokens[0] == "look" and tokens[1] in direction_aliases:
            direction = tokens[1]
            axis = "yaw" if direction in {"left", "right"} else "pitch"
            amount = self._parse_amount(tokens[2:], axis)
            if amount is None:
                return None
            return {
                "kind": "look_delta",
                "axis": axis,
                "delta": direction_aliases[direction] * amount,
                "label": f"look_{direction}",
            }

        if len(tokens) >= 2 and tokens[0] == "antennas" and tokens[1] in {"left", "right"}:
            amount = self._parse_amount(tokens[2:], "antennas")
            if amount is None:
                return None
            sign = -1 if tokens[1] == "left" else 1
            return {
                "kind": "antennas_delta",
                "left_delta": sign * amount,
                "right_delta": -sign * amount,
                "label": f"antennas_{tokens[1]}",
            }

        return None

    def _parse_amount(self, tokens: list[str], axis: str) -> Optional[int]:
        cleaned = [token for token in tokens if token not in _IGNORED_AMOUNT_TOKENS]
        if not cleaned:
            return self._default_step(axis)
        return self._parse_number_phrase(cleaned)

    def _default_step(self, axis: str) -> int:
        if axis == "pitch":
            return self._pitch_step
        if axis == "yaw":
            return self._yaw_step
        if axis == "roll":
            return self._roll_step
        if axis == "antennas":
            return self._antenna_step
        raise ValueError(f"Unsupported axis: {axis}")

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = re.sub(r"[^\w\s-]", " ", text.lower())
        return " ".join(text.split())

    @classmethod
    def _canonicalize_tokens(cls, tokens: list[str]) -> list[str]:
        canonical = [_TOKEN_ALIASES.get(token, token) for token in tokens]
        while len(canonical) > 1 and canonical[0] in _LEADING_FILLER_TOKENS:
            canonical = canonical[1:]
        return canonical

    @classmethod
    def _parse_number_token(cls, token: str) -> Optional[int]:
        return cls._parse_number_phrase([token])

    @classmethod
    def _parse_number_phrase(cls, tokens: list[str]) -> Optional[int]:
        if not tokens:
            return None

        joined = " ".join(tokens)
        if re.fullmatch(r"[+-]?\d+", joined):
            return int(joined)

        expanded = joined.replace("-", " ").split()
        sign = 1
        if expanded and expanded[0] in {"minus", "negative"}:
            sign = -1
            expanded = expanded[1:]
        if not expanded:
            return None

        current = 0
        for token in expanded:
            if token in _NUMBER_WORDS:
                current += _NUMBER_WORDS[token]
            elif token == "hundred":
                current = max(current, 1) * 100
            else:
                return None

        return sign * current
