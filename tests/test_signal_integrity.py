"""
test_signal_integrity.py
Validates that gesture-to-coordinate mapping accurately reflects
normalised hand positions across screen resolutions.
"""

import pytest
from tests.conftest import (
    make_hand, default_mapper,
    INDEX_TIP, INDEX_PIP, INDEX_MCP,
    MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP,
    RING_TIP, RING_PIP, RING_MCP,
    PINKY_TIP, PINKY_PIP, PINKY_MCP,
    THUMB_TIP, THUMB_IP, WRIST,
)
from src.vision.gesture_mapper import GestureMapper, PINCH_CLOSE_THRESHOLD, CONFIRM_FRAMES


# ─────────────────────────────────────────────────────────────────────────────
# 1. Coordinate mapping
# ─────────────────────────────────────────────────────────────────────────────

class TestCoordinateMapping:
    """Mouse-move commands must faithfully reflect normalised hand position."""

    @pytest.mark.parametrize("nx,ny,sw,sh", [
        (0.5, 0.5, 1920, 1080),   # centre of 1080p
        (0.0, 0.0, 1920, 1080),   # top-left
        (1.0, 1.0, 1920, 1080),   # bottom-right
        (0.5, 0.5, 2560, 1440),   # centre of 1440p
        (0.5, 0.5,  800,  600),   # small screen
        (0.25, 0.75, 3840, 2160), # 4K off-centre
    ])
    def test_move_maps_to_correct_pixels(self, nx, ny, sw, sh):
        """
        After enough frames the smoothed position should be within
        ±5 pixels of the expected coordinate.
        """
        mapper = GestureMapper(screen_w=sw, screen_h=sh)

        # Only index finger extended → pointer mode
        # MCP must be below PIP, PIP below TIP for the two-joint check
        hand = make_hand({
            INDEX_TIP: (nx, ny, 0.0),
            INDEX_PIP: (nx, ny + 0.05, 0.0),
            INDEX_MCP: (nx, ny + 0.10, 0.0),
            # Thumb, middle, ring, pinky curled (tip below pip)
            THUMB_TIP: (0.5, 0.5, 0.0),
            MIDDLE_TIP: (0.5, 0.6, 0.0), MIDDLE_MCP: (0.5, 0.55, 0.0),
            RING_TIP:   (0.5, 0.6, 0.0), RING_MCP:   (0.5, 0.55, 0.0),
            PINKY_TIP:  (0.5, 0.6, 0.0), PINKY_MCP:  (0.5, 0.55, 0.0),
        })

        # Run several frames to let the smoother converge
        for _ in range(30):
            cmds = mapper.map(hand)

        move_cmds = [c for c in cmds if c.startswith("MOUSE_MOVE")]
        assert move_cmds, "Expected at least one MOUSE_MOVE command"

        last_cmd = move_cmds[-1]
        _, px_s, py_s = last_cmd.split()
        px, py = int(px_s), int(py_s)

        expected_x = round(nx * sw)
        expected_y = round(ny * sh)
        assert abs(px - expected_x) <= 5, (
            f"x mismatch at ({nx},{ny}) on {sw}x{sh}: got {px}, expected ~{expected_x}"
        )
        assert abs(py - expected_y) <= 5, (
            f"y mismatch at ({nx},{ny}) on {sw}x{sh}: got {py}, expected ~{expected_y}"
        )

    def test_coordinates_stay_within_screen_bounds(self):
        """Coordinates must never exceed screen dimensions."""
        mapper = GestureMapper(screen_w=1920, screen_h=1080)
        for nx in [0.0, 0.5, 1.0, 1.5, -0.1]:  # include out-of-range inputs
            hand = make_hand({
                INDEX_TIP: (nx, 0.5, 0.0),
                INDEX_PIP: (nx, 0.55, 0.0),
                INDEX_MCP: (nx, 0.60, 0.0),
            })
            for _ in range(10):
                cmds = mapper.map(hand)
            for cmd in cmds:
                if cmd.startswith("MOUSE_MOVE"):
                    _, px_s, py_s = cmd.split()
                    px, py = int(px_s), int(py_s)
                    assert 0 <= px < 1920, f"x={px} out of bounds"
                    assert 0 <= py < 1080, f"y={py} out of bounds"

    def test_resolution_independence(self):
        """Same normalised input must produce proportionally scaled outputs."""
        nx, ny = 0.5, 0.5
        resolutions = [(1280, 720), (1920, 1080), (3840, 2160)]
        results = []

        for sw, sh in resolutions:
            mapper = GestureMapper(screen_w=sw, screen_h=sh)
            hand = make_hand({
                INDEX_TIP: (nx, ny, 0.0),
                INDEX_PIP: (nx, ny + 0.05, 0.0),
                INDEX_MCP: (nx, ny + 0.10, 0.0),
            })
            for _ in range(30):
                cmds = mapper.map(hand)
            move_cmds = [c for c in cmds if c.startswith("MOUSE_MOVE")]
            assert move_cmds
            _, px_s, py_s = move_cmds[-1].split()
            results.append((int(px_s), int(py_s), sw, sh))

        for px, py, sw, sh in results:
            # Centre of screen → within 5px of sw/2 and sh/2 (after smoothing)
            assert abs(px - sw // 2) <= 5, f"Centre-x mismatch at {sw}x{sh}: {px}"
            assert abs(py - sh // 2) <= 5, f"Centre-y mismatch at {sw}x{sh}: {py}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Click signal integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestClickSignalIntegrity:

    def test_pinch_triggers_left_click(self, default_mapper):
        """A tight pinch must produce exactly one MOUSE_LEFT command."""
        hand = make_hand({
            THUMB_TIP:  (0.5, 0.5, 0.0),
            INDEX_TIP:  (0.50 + PINCH_CLOSE_THRESHOLD * 0.5, 0.5, 0.0),
            INDEX_PIP:  (0.50, 0.55, 0.0),
            INDEX_MCP:  (0.50, 0.60, 0.0),
        })
        all_cmds = []
        for _ in range(CONFIRM_FRAMES + 2):
            all_cmds.extend(default_mapper.map(hand))
        clicks = [c for c in all_cmds if c == "MOUSE_LEFT"]
        assert len(clicks) == 1, f"Expected 1 click, got {len(clicks)}"

    def test_no_click_when_not_pinching(self, default_mapper):
        """Wide separation between thumb and index must produce no click."""
        hand = make_hand({
            THUMB_TIP: (0.2, 0.5, 0.0),
            INDEX_TIP: (0.8, 0.5, 0.0),
        })
        all_cmds = []
        for _ in range(10):
            all_cmds.extend(default_mapper.map(hand))
        assert "MOUSE_LEFT" not in all_cmds

    def test_v_sign_triggers_right_click(self):
        """Index + middle only should trigger a right click."""
        mapper = GestureMapper()
        hand = make_hand({
            # Index extended (tip above pip above mcp)
            INDEX_TIP:  (0.5, 0.3, 0.0),
            INDEX_PIP:  (0.5, 0.5, 0.0),
            INDEX_MCP:  (0.5, 0.6, 0.0),
            # Middle extended
            MIDDLE_TIP: (0.5, 0.3, 0.0),
            MIDDLE_PIP: (0.5, 0.5, 0.0),
            MIDDLE_MCP: (0.5, 0.6, 0.0),
            # Ring and pinky curled (tip below pip)
            RING_TIP:   (0.5, 0.6, 0.0),
            RING_PIP:   (0.5, 0.55, 0.0),
            RING_MCP:   (0.5, 0.50, 0.0),
            PINKY_TIP:  (0.5, 0.6, 0.0),
            PINKY_PIP:  (0.5, 0.55, 0.0),
            PINKY_MCP:  (0.5, 0.50, 0.0),
            # Thumb curled
            THUMB_TIP:  (0.5, 0.5, 0.0),
            THUMB_IP:   (0.5, 0.45, 0.0),
            WRIST:      (0.5, 0.8, 0.0),
        })
        all_cmds = []
        for _ in range(CONFIRM_FRAMES + 2):
            all_cmds.extend(mapper.map(hand))
        assert "MOUSE_RIGHT" in all_cmds


# ─────────────────────────────────────────────────────────────────────────────
# 3. Gamepad signal integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestGamepadSignalIntegrity:

    def test_fist_presses_and_releases_A(self, default_mapper):
        """Fist → press A; open hand → release A."""
        # Fist: all fingers curled (tip y > pip y > mcp y for each)
        fist = make_hand({
            THUMB_TIP:  (0.5, 0.6, 0.0), THUMB_IP:   (0.5, 0.55, 0.0),
            INDEX_TIP:  (0.5, 0.7, 0.0), INDEX_PIP:  (0.5, 0.6, 0.0),  INDEX_MCP:  (0.5, 0.55, 0.0),
            MIDDLE_TIP: (0.5, 0.7, 0.0), MIDDLE_PIP: (0.5, 0.6, 0.0),  MIDDLE_MCP: (0.5, 0.55, 0.0),
            RING_TIP:   (0.5, 0.7, 0.0), RING_PIP:   (0.5, 0.6, 0.0),  RING_MCP:   (0.5, 0.55, 0.0),
            PINKY_TIP:  (0.5, 0.7, 0.0), PINKY_PIP:  (0.5, 0.6, 0.0),  PINKY_MCP:  (0.5, 0.55, 0.0),
            WRIST:      (0.5, 0.8, 0.0),
        })
        # Must send CONFIRM_FRAMES frames for gesture to activate
        all_cmds = []
        for _ in range(CONFIRM_FRAMES + 1):
            all_cmds.extend(default_mapper.map(fist))
        assert "GAMEPAD_BTN A 1" in all_cmds

        # Open hand: index extended
        open_hand = make_hand({
            INDEX_TIP: (0.5, 0.2, 0.0),
            INDEX_PIP: (0.5, 0.4, 0.0),
            INDEX_MCP: (0.5, 0.5, 0.0),
        })
        cmds2 = []
        for _ in range(CONFIRM_FRAMES + 1):
            cmds2.extend(default_mapper.map(open_hand))
        assert "GAMEPAD_BTN A 0" in cmds2

    def test_stick_range_is_valid(self, default_mapper):
        """Stick values must stay within [-32767, 32767]."""
        for nx in [0.0, 0.25, 0.5, 0.75, 1.0]:
            hand = make_hand({
                INDEX_TIP:  (nx, 0.5, 0.0),
                INDEX_PIP:  (nx, 0.55, 0.0),
                INDEX_MCP:  (nx, 0.60, 0.0),
                MIDDLE_TIP: (nx, 0.3, 0.0),
                MIDDLE_PIP: (nx, 0.45, 0.0),
                MIDDLE_MCP: (nx, 0.50, 0.0),
                RING_TIP:   (nx, 0.3, 0.0),
                RING_PIP:   (nx, 0.45, 0.0),
                RING_MCP:   (nx, 0.50, 0.0),
                THUMB_TIP:  (0.4, 0.6, 0.0),
                THUMB_IP:   (0.45, 0.55, 0.0),
                WRIST:      (0.5, 0.8, 0.0),
            })
            # Need CONFIRM_FRAMES to activate the gesture
            for _ in range(CONFIRM_FRAMES + 1):
                cmds = default_mapper.map(hand)
            for cmd in cmds:
                if cmd.startswith("GAMEPAD_STICK"):
                    _, sx_s, sy_s = cmd.split()
                    sx, sy = int(sx_s), int(sy_s)
                    assert -32767 <= sx <= 32767, f"Stick X={sx} out of range"
                    assert -32767 <= sy <= 32767, f"Stick Y={sy} out of range"
