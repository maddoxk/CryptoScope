"""Non-blocking terminal input handling that cooperates with Rich Live."""

from __future__ import annotations

import asyncio
import os
import select
import sys
import termios
import tty
from typing import AsyncIterator


class TerminalInput:
    """Async key reader that doesn't corrupt terminal state for Rich.

    Instead of toggling raw mode per-read (which races with Rich's rendering),
    we set raw mode once at start and restore it once at exit, letting Rich
    handle its own alternate screen.
    """

    def __init__(self) -> None:
        self._fd = sys.stdin.fileno()
        self._old_settings: list | None = None

    def start(self) -> None:
        """Save terminal settings and switch to cbreak mode.

        cbreak (not raw) lets Rich's escape sequences pass through while
        still delivering individual keypresses without waiting for Enter.
        """
        self._old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)

    def stop(self) -> None:
        """Restore original terminal settings."""
        if self._old_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
            self._old_settings = None

    async def read_key(self) -> str:
        """Read a single key or escape sequence asynchronously.

        Returns the character for normal keys, or a descriptive string for
        special keys:
            'UP', 'DOWN', 'LEFT', 'RIGHT', 'ENTER', 'BACKSPACE', 'ESCAPE',
            'F1', 'F2', 'F3', 'F4', or the raw character.
        """
        loop = asyncio.get_event_loop()
        char = await loop.run_in_executor(None, self._blocking_read)

        if char == "\x1b":
            # Could be an escape sequence or just the Escape key
            seq = await loop.run_in_executor(None, self._read_escape_tail)
            return self._decode_escape(seq)
        elif char == "\r" or char == "\n":
            return "ENTER"
        elif char == "\x7f" or char == "\x08":
            return "BACKSPACE"
        else:
            return char

    def _blocking_read(self) -> str:
        """Read one byte from stdin (blocks until available)."""
        return os.read(self._fd, 1).decode("utf-8", errors="replace")

    def _read_escape_tail(self) -> str:
        """Read the tail of an escape sequence with a short timeout.

        Handles two sequence families:
        - CSI sequences: ESC [ ... letter  (arrows, Fn via xterm/VT220)
        - SS3 sequences: ESC O letter      (F1-F4 in VT100/many terminals)
        """
        buf = ""
        while select.select([self._fd], [], [], 0.03)[0]:
            byte = os.read(self._fd, 1).decode("utf-8", errors="replace")
            buf += byte
            if byte.isalpha() or byte == "~":
                # SS3 prefix: ESC O — need one more byte for the actual key
                if buf == "O":
                    continue
                break
        return buf

    @staticmethod
    def _decode_escape(seq: str) -> str:
        """Map escape sequence tail to a key name."""
        mapping = {
            "[A": "UP",
            "[B": "DOWN",
            "[C": "RIGHT",
            "[D": "LEFT",
            "OP": "F1",
            "OQ": "F2",
            "OR": "F3",
            "OS": "F4",
            "[11~": "F1",
            "[12~": "F2",
            "[13~": "F3",
            "[14~": "F4",
            "[15~": "F5",
            "[17~": "F6",
            "[18~": "F7",
        }
        return mapping.get(seq, "ESCAPE")
