"""
hud_overlay.py  –  Real-time on-screen display for GestureLink.

Draws a translucent panel on the camera frame showing:
  • Detected gesture name
  • Active HID commands being sent
  • Per-finger extension state (visual indicators)
  • Frames-per-second counter
"""

from __future__ import annotations

import collections
import time
from typing import List, Optional

import cv2
import numpy as np

from .gesture_detector import HandResult


# ── Colour palette (BGR) ─────────────────────────────────────────────────────
_WHITE   = (255, 255, 255)
_GREEN   = (0, 220, 80)
_RED     = (60, 60, 255)
_YELLOW  = (0, 220, 255)
_CYAN    = (255, 220, 0)
_GREY    = (180, 180, 180)
_BG      = (30, 30, 30)

_FONT       = cv2.FONT_HERSHEY_SIMPLEX
_FONT_BOLD  = cv2.FONT_HERSHEY_DUPLEX

_FINGER_LABELS = ["Thumb", "Index", "Middle", "Ring", "Pinky"]


def classify_gesture(hand: Optional[HandResult], cmds: List[str]) -> str:
    """Return a human-friendly gesture name based on hand state & commands."""
    if hand is None:
        return "No Hand"

    # Derive label from the commands that actually fired this frame
    for c in cmds:
        if c == "MOUSE_LEFT":
            return "Pinch  (Left Click)"
        if c == "MOUSE_RIGHT":
            return "V-Sign  (Right Click)"
        if c.startswith("MOUSE_SCROLL"):
            val = c.split()[-1]
            return "Scroll Up" if int(val) > 0 else "Scroll Down"
        if c.startswith("GAMEPAD_STICK"):
            return "Three Fingers  (Stick)"
        if "GAMEPAD_BTN START 1" in c:
            return "Open Palm  (Start)"
        if "GAMEPAD_BTN A 1" in c:
            return "Fist  (Btn A Press)"
        if "GAMEPAD_BTN A 0" in c:
            return "Fist Released"

    # No special command → infer from finger state
    ext = [hand.finger_extended(i) for i in range(5)]
    n = sum(ext)

    if hand.pinch_distance() < 0.05:
        return "Pinch  (Hold)"
    if n == 0:
        return "Fist  (Btn A Hold)"
    if n == 5:
        return "Open Palm"
    if ext[1] and ext[2] and not ext[0] and not ext[3] and not ext[4]:
        return "V-Sign"
    if ext[1] and ext[2] and ext[3] and not ext[0] and not ext[4]:
        return "Three Fingers"
    if ext[0] and ext[1] and n == 2:
        return "Thumb+Index  (Scroll)"
    if ext[1] and n == 1:
        return "Point  (Mouse Move)"
    # Check for MOUSE_MOVE in cmds (pointer active but with other fingers)
    if any(c.startswith("MOUSE_MOVE") for c in cmds):
        return "Point  (Mouse Move)"
    return f"{n} Finger{'s' if n != 1 else ''}"


class HudOverlay:
    """Manages and renders an on-screen HUD onto OpenCV frames."""

    # How many recent commands to show in the log
    CMD_LOG_SIZE = 6

    def __init__(self) -> None:
        self._cmd_log: collections.deque[tuple[float, str]] = collections.deque(
            maxlen=self.CMD_LOG_SIZE
        )
        self._fps_ts: collections.deque[float] = collections.deque(maxlen=60)
        self._gesture_name: str = "Waiting…"
        self._finger_state: list[bool] = [False] * 5

    # ── Public API ───────────────────────────────────────────────────────────

    def update(
        self,
        hand: Optional[HandResult],
        cmds: List[str],
    ) -> None:
        """Feed new frame data (call once per loop iteration)."""
        now = time.monotonic()
        self._fps_ts.append(now)

        # Gesture label
        self._gesture_name = classify_gesture(hand, cmds)

        # Finger state
        if hand is not None:
            self._finger_state = [hand.finger_extended(i) for i in range(5)]
        else:
            self._finger_state = [False] * 5

        # Append non-trivial commands to the scrolling log
        for c in cmds:
            if not c.startswith("MOUSE_MOVE"):  # moves are too spammy
                self._cmd_log.append((now, c))

    def draw(self, frame: np.ndarray) -> np.ndarray:
        """Draw the HUD onto *frame* (mutates in place and returns it)."""
        h, w = frame.shape[:2]

        # ── Left panel (gesture + fingers) ───────────────────────────────
        panel_w, panel_h = 280, 170
        self._draw_panel(frame, 10, 10, panel_w, panel_h, alpha=0.65)

        y0 = 35
        # Gesture name
        cv2.putText(frame, "GESTURE", (20, y0), _FONT, 0.45, _GREY, 1, cv2.LINE_AA)
        cv2.putText(frame, self._gesture_name, (20, y0 + 26), _FONT_BOLD, 0.6,
                    _GREEN, 1, cv2.LINE_AA)

        # Finger indicators
        cv2.putText(frame, "FINGERS", (20, y0 + 66), _FONT, 0.45, _GREY, 1, cv2.LINE_AA)
        for i, (label, on) in enumerate(zip(_FINGER_LABELS, self._finger_state)):
            cx = 30 + i * 52
            cy = y0 + 92
            colour = _GREEN if on else _RED
            cv2.circle(frame, (cx, cy), 10, colour, -1, cv2.LINE_AA)
            cv2.putText(frame, label[0], (cx - 5, cy + 5), _FONT, 0.4, _WHITE, 1, cv2.LINE_AA)
            cv2.putText(frame, label, (cx - 15, cy + 26), _FONT, 0.3,
                        colour, 1, cv2.LINE_AA)

        # ── Right panel (command log) ────────────────────────────────────
        log_w, log_h = 300, 20 + self.CMD_LOG_SIZE * 22
        lx = w - log_w - 10
        self._draw_panel(frame, lx, 10, log_w, log_h, alpha=0.65)

        cv2.putText(frame, "HID COMMANDS", (lx + 10, 32), _FONT, 0.45, _GREY, 1, cv2.LINE_AA)
        now = time.monotonic()
        for idx, (ts, cmd) in enumerate(reversed(list(self._cmd_log))):
            age = now - ts
            alpha_txt = max(0.3, 1.0 - age / 4.0)
            # Fade colour from yellow → grey
            col = tuple(int(c * alpha_txt + g * (1 - alpha_txt))
                        for c, g in zip(_YELLOW, (100, 100, 100)))
            ty = 54 + idx * 22
            cv2.putText(frame, cmd, (lx + 10, ty), _FONT, 0.42, col, 1, cv2.LINE_AA)

        # ── FPS badge (bottom-left) ──────────────────────────────────────
        fps_val = self._calc_fps()
        fps_text = f"FPS: {fps_val:.0f}"
        cv2.putText(frame, fps_text, (15, h - 15), _FONT, 0.55, _CYAN, 1, cv2.LINE_AA)

        return frame

    # ── Internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _draw_panel(
        frame: np.ndarray, x: int, y: int, w: int, h: int, alpha: float = 0.6
    ) -> None:
        """Draw a semi-transparent dark rectangle."""
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + w, y + h), _BG, -1)
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    def _calc_fps(self) -> float:
        ts = self._fps_ts
        if len(ts) < 2:
            return 0.0
        span = ts[-1] - ts[0]
        if span <= 0:
            return 0.0
        return (len(ts) - 1) / span
