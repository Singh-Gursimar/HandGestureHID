"""
gesture_mapper.py
Maps HandResult objects to HID command strings understood by hid_driver.

Architecture
------------
Each frame is classified into exactly ONE gesture via a priority ladder.
A gesture only *activates* after it has been the winner for
``CONFIRM_FRAMES`` consecutive frames, eliminating flicker from transient
hand poses during transitions.

Supported Gestures  (highest → lowest priority)
------------------------------------------------
  Pinch            – thumb+index tips close  → left click
  Fist             – 0 fingers extended      → GAMEPAD_BTN A (hold)
  V-sign           – index+middle only       → right click
  Three fingers    – index+middle+ring only  → GAMEPAD_STICK
  Open palm        – all 5 extended          → GAMEPAD_BTN START (one-shot)
  Thumb scroll     – thumb+index extended    → scroll up/down
  Pointer          – index extended           → mouse move
  Idle             – anything else            → (no output)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .gesture_detector import HandResult, LM


# ---- Tunable thresholds -------------------------------------------------------

PINCH_CLOSE_THRESHOLD  = 0.050   # normalised distance → pinch active
PINCH_OPEN_THRESHOLD   = 0.080   # hysteresis → pinch clears above this
CLICK_COOLDOWN_S       = 0.30    # min seconds between consecutive clicks
SCROLL_COOLDOWN_S      = 0.12    # min seconds between scroll ticks
SCREEN_SMOOTHING       = 0.40    # EWM alpha  (higher = more responsive, more jitter)
STICK_SMOOTHING        = 0.35    # EWM alpha for gamepad stick
STICK_DEADZONE         = 0.08    # normalised dead-zone radius around centre
CONFIRM_FRAMES         = 3       # consecutive frames before a gesture activates


# ---- Gesture identifiers (used for frame-count confirmation) ------------------

_G_IDLE          = "idle"
_G_POINTER       = "pointer"
_G_PINCH         = "pinch"
_G_V_SIGN        = "v_sign"
_G_FIST          = "fist"
_G_OPEN_PALM     = "open_palm"
_G_SCROLL_UP     = "scroll_up"
_G_SCROLL_DOWN   = "scroll_down"
_G_THREE_STICK   = "three_stick"


@dataclass
class _MappingState:
    """Persistent state across frames for hysteresis and cooldowns."""
    # Smoothed cursor position
    prev_x: float = 0.5
    prev_y: float = 0.5
    # Smoothed stick position
    stick_x: float = 0.0
    stick_y: float = 0.0
    # Pinch hysteresis
    pinching: bool = False
    # Gamepad hold states
    fist_held: bool = False
    # Gesture confirmation counter
    pending_gesture: str = _G_IDLE
    pending_count: int = 0
    active_gesture: str  = _G_IDLE
    # Cooldown timestamps (far in the past so first event fires immediately)
    last_click_t: float  = field(default_factory=lambda: time.monotonic() - 10.0)
    last_rclick_t: float = field(default_factory=lambda: time.monotonic() - 10.0)
    last_scroll_t: float = field(default_factory=lambda: time.monotonic() - 10.0)
    last_start_t: float  = field(default_factory=lambda: time.monotonic() - 10.0)


def _classify(hand: HandResult) -> str:
    """Classify a single frame into one gesture label (priority ladder)."""
    ext = [hand.finger_extended(i) for i in range(5)]
    n   = sum(ext)

    # --- Pinch (thumb + index tips close) – highest priority ----------------
    if hand.pinch_distance() < PINCH_CLOSE_THRESHOLD:
        return _G_PINCH

    # --- Fist (no fingers extended) -----------------------------------------
    if n == 0:
        return _G_FIST

    # --- V-sign (index + middle only) ---------------------------------------
    if ext[1] and ext[2] and not ext[0] and not ext[3] and not ext[4]:
        return _G_V_SIGN

    # --- Three-finger stick (index + middle + ring, no thumb/pinky) ---------
    if ext[1] and ext[2] and ext[3] and not ext[0] and not ext[4]:
        return _G_THREE_STICK

    # --- Open palm (all 5) --------------------------------------------------
    if n == 5:
        return _G_OPEN_PALM

    # --- Thumb + index = scroll (direction determined later) ----------------
    if ext[0] and ext[1] and n == 2:
        thumb = hand.fingertip(0)
        wrist = hand.lm(LM.WRIST)
        if thumb.y < wrist.y - 0.04:
            return _G_SCROLL_UP
        elif thumb.y > wrist.y + 0.04:
            return _G_SCROLL_DOWN
        # Ambiguous direction → treat as pointer
        return _G_POINTER

    # --- Pointer (index extended, regardless of other fingers) ---------------
    if ext[1]:
        return _G_POINTER

    return _G_IDLE


class GestureMapper:
    """
    Consumes HandResult objects and emits HID command strings.

    Gestures are mutually exclusive per frame—only the highest-priority
    detected gesture runs.  A gesture must win ``CONFIRM_FRAMES``
    consecutive classification rounds before its action fires, preventing
    spurious triggers during hand transitions.
    """

    def __init__(self, screen_w: int = 1920, screen_h: int = 1080) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._state = _MappingState()

    def map(self, hand: HandResult) -> List[str]:
        """
        Convert a single HandResult into a (possibly empty) list of
        driver command strings.
        """
        commands: List[str] = []
        now = time.monotonic()
        s   = self._state

        # ── 1. Classify this frame ───────────────────────────────────────
        gesture = _classify(hand)

        # ── 2. Confirm: require N consecutive frames of the same gesture ─
        if gesture == s.pending_gesture:
            s.pending_count += 1
        else:
            s.pending_gesture = gesture
            s.pending_count   = 1

        confirmed = s.pending_count >= CONFIRM_FRAMES
        if confirmed:
            s.active_gesture = gesture

        active = s.active_gesture

        # ── 3. Release held state when gesture changes ───────────────────
        if active != _G_FIST and s.fist_held:
            commands.append("GAMEPAD_BTN A 0")
            s.fist_held = False

        if active != _G_PINCH and s.pinching:
            s.pinching = False

        # ── 4. Execute the active gesture ────────────────────────────────

        # --- Pointer (mouse move) ----------------------------------------
        if active == _G_POINTER:
            commands.extend(self._do_pointer(hand))

        # --- Pinch (left click) ------------------------------------------
        elif active == _G_PINCH:
            commands.extend(self._do_pointer(hand))   # keep cursor tracking
            if not s.pinching:
                s.pinching = True
                if (now - s.last_click_t) > CLICK_COOLDOWN_S:
                    commands.append("MOUSE_LEFT")
                    s.last_click_t = now

        # --- Fist (gamepad A hold) ---------------------------------------
        elif active == _G_FIST:
            if not s.fist_held:
                commands.append("GAMEPAD_BTN A 1")
                s.fist_held = True

        # --- V-sign (right click, one-shot per cooldown) -----------------
        elif active == _G_V_SIGN:
            commands.extend(self._do_pointer(hand))   # cursor tracks index
            if (now - s.last_rclick_t) > CLICK_COOLDOWN_S:
                commands.append("MOUSE_RIGHT")
                s.last_rclick_t = now

        # --- Three-finger stick ------------------------------------------
        elif active == _G_THREE_STICK:
            commands.extend(self._do_stick(hand))

        # --- Open palm → START (one-shot) --------------------------------
        elif active == _G_OPEN_PALM:
            if (now - s.last_start_t) > 1.0:
                commands.append("GAMEPAD_BTN START 1")
                commands.append("GAMEPAD_BTN START 0")
                s.last_start_t = now

        # --- Scroll (thumb + index) --------------------------------------
        elif active in (_G_SCROLL_UP, _G_SCROLL_DOWN):
            delta = 3 if active == _G_SCROLL_UP else -3
            if (now - s.last_scroll_t) > SCROLL_COOLDOWN_S:
                commands.append(f"MOUSE_SCROLL {delta}")
                s.last_scroll_t = now

        return commands

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _do_pointer(self, hand: HandResult) -> List[str]:
        """Smoothed cursor movement from index fingertip."""
        s = self._state
        ix, iy = hand.index_tip_position()

        sx = s.prev_x * (1 - SCREEN_SMOOTHING) + ix * SCREEN_SMOOTHING
        sy = s.prev_y * (1 - SCREEN_SMOOTHING) + iy * SCREEN_SMOOTHING
        s.prev_x, s.prev_y = sx, sy

        px = max(0, min(round(sx * self.screen_w), self.screen_w - 1))
        py = max(0, min(round(sy * self.screen_h), self.screen_h - 1))
        return [f"MOUSE_MOVE {px} {py}"]

    def _do_stick(self, hand: HandResult) -> List[str]:
        """Smoothed analogue stick from index fingertip with dead-zone."""
        s = self._state
        ix, iy = hand.index_tip_position()

        # Raw normalised offset from centre (−0.5 … +0.5)
        raw_x = ix - 0.5
        raw_y = iy - 0.5

        # Apply dead-zone
        mag = math.hypot(raw_x, raw_y)
        if mag < STICK_DEADZONE:
            raw_x, raw_y = 0.0, 0.0
        else:
            # Re-scale so edge of dead-zone maps to 0
            scale = (mag - STICK_DEADZONE) / (0.5 - STICK_DEADZONE) / mag
            raw_x *= scale
            raw_y *= scale

        # Smooth
        s.stick_x = s.stick_x * (1 - STICK_SMOOTHING) + raw_x * STICK_SMOOTHING
        s.stick_y = s.stick_y * (1 - STICK_SMOOTHING) + raw_y * STICK_SMOOTHING

        # Map to int16 range
        sx = max(-32767, min(32767, round(s.stick_x * 2 * 32767)))
        sy = max(-32767, min(32767, round(s.stick_y * 2 * 32767)))
        return [f"GAMEPAD_STICK {sx} {sy}"]
