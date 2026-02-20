"""
test_stress.py
Stress tests: flood the mapper with rapid-fire inputs to verify
there are no crashes, memory leaks, or unexpected output.
"""

import time
import random
import pytest

from tests.conftest import (
    make_hand,
    INDEX_TIP, INDEX_PIP, INDEX_MCP,
    MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP,
    RING_TIP, RING_PIP, RING_MCP,
    PINKY_TIP, PINKY_PIP, PINKY_MCP,
    THUMB_TIP, THUMB_IP,
    WRIST,
)
from src.vision.gesture_mapper import GestureMapper


def _random_hand():
    """Generate a HandResult with random landmark positions."""
    positions = {}
    for tip, pip_, mcp in [
        (INDEX_TIP, INDEX_PIP, INDEX_MCP),
        (MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP),
        (RING_TIP, RING_PIP, RING_MCP),
        (PINKY_TIP, PINKY_PIP, PINKY_MCP),
    ]:
        x = random.random()
        y = random.random()
        positions[tip]  = (x, y, 0.0)
        positions[pip_] = (x, y + random.choice([-0.1, 0.1]), 0.0)
        positions[mcp]  = (x, y + random.choice([-0.15, 0.15]), 0.0)

    positions[THUMB_TIP] = (random.random(), random.random(), 0.0)
    positions[THUMB_IP]  = (random.random(), random.random(), 0.0)
    positions[WRIST]     = (0.5, 0.8, 0.0)
    return make_hand(positions)


class TestMapperStress:

    def test_rapid_fire_does_not_crash(self):
        """
        Send 10,000 random HandResult objects through the mapper.
        We only verify no exception is raised and output is well-formed.
        """
        mapper = GestureMapper(screen_w=1920, screen_h=1080)
        for _ in range(10_000):
            hand  = _random_hand()
            cmds  = mapper.map(hand)
            for c in cmds:
                assert isinstance(c, str)
                assert len(c) > 0

    def test_all_commands_are_valid_protocol_strings(self):
        """
        Every emitted command must start with a known verb
        and have the correct number of tokens.
        """
        VALID_VERBS = {
            "MOUSE_MOVE":    3,
            "MOUSE_LEFT":    1,
            "MOUSE_RIGHT":   1,
            "MOUSE_SCROLL":  2,
            "GAMEPAD_BTN":   3,
            "GAMEPAD_STICK": 3,
        }
        mapper = GestureMapper()
        for _ in range(5_000):
            cmds = mapper.map(_random_hand())
            for cmd in cmds:
                parts = cmd.split()
                verb  = parts[0]
                assert verb in VALID_VERBS, f"Unknown verb: {verb!r} in {cmd!r}"
                assert len(parts) == VALID_VERBS[verb], (
                    f"Token count mismatch for {cmd!r}: "
                    f"expected {VALID_VERBS[verb]}, got {len(parts)}"
                )

    def test_throughput_above_500_gestures_per_second(self):
        """
        The Python mapper alone must handle at least 500 gesture
        mappings per second (no camera I/O).
        """
        mapper  = GestureMapper()
        hands   = [_random_hand() for _ in range(1000)]
        count   = 0
        t0      = time.perf_counter()

        for hand in hands:
            mapper.map(hand)
            count += 1

        elapsed = time.perf_counter() - t0
        rate    = count / elapsed
        assert rate >= 500, (
            f"Mapper throughput too low: {rate:.0f} gestures/s (min 500)"
        )

    def test_state_resets_between_mapper_instances(self):
        """
        Two independent GestureMapper instances must not share state.
        """
        m1 = GestureMapper()
        m2 = GestureMapper()

        # Drive m1 into fist-held state
        fist = make_hand({
            THUMB_TIP:  (0.5, 0.6, 0.0), THUMB_IP:   (0.5, 0.55, 0.0),
            INDEX_TIP:  (0.5, 0.7, 0.0), INDEX_PIP:  (0.5, 0.6, 0.0),  INDEX_MCP:  (0.5, 0.55, 0.0),
            MIDDLE_TIP: (0.5, 0.7, 0.0), MIDDLE_PIP: (0.5, 0.6, 0.0),  MIDDLE_MCP: (0.5, 0.55, 0.0),
            RING_TIP:   (0.5, 0.7, 0.0), RING_PIP:   (0.5, 0.6, 0.0),  RING_MCP:   (0.5, 0.55, 0.0),
            PINKY_TIP:  (0.5, 0.7, 0.0), PINKY_PIP:  (0.5, 0.6, 0.0),  PINKY_MCP:  (0.5, 0.55, 0.0),
            WRIST:      (0.5, 0.8, 0.0),
        })
        for _ in range(5):
            m1.map(fist)

        # m2 has never seen a fist; its internal state must be clean
        assert not m2._state.fist_held, "m2 should not share state with m1"

    def test_no_negative_coordinates_from_random_input(self):
        """
        Random inputs must never produce negative pixel coordinates.
        """
        mapper = GestureMapper(screen_w=1920, screen_h=1080)
        for _ in range(2000):
            cmds = mapper.map(_random_hand())
            for cmd in cmds:
                if cmd.startswith("MOUSE_MOVE"):
                    _, px_s, py_s = cmd.split()
                    assert int(px_s) >= 0, f"Negative x in: {cmd}"
                    assert int(py_s) >= 0, f"Negative y in: {cmd}"

    def test_rapid_gesture_transitions(self):
        """
        Alternate between different gestures 1,000 times without errors.
        """
        mapper = GestureMapper()
        gestures = [
            # Pointer only
            make_hand({INDEX_TIP: (0.5, 0.3, 0.0), INDEX_PIP: (0.5, 0.5, 0.0), INDEX_MCP: (0.5, 0.6, 0.0)}),
            # Fist
            make_hand({
                THUMB_TIP:  (0.5, 0.6, 0.0), THUMB_IP:   (0.5, 0.55, 0.0),
                INDEX_TIP:  (0.5, 0.7, 0.0), INDEX_PIP:  (0.5, 0.6, 0.0),  INDEX_MCP:  (0.5, 0.55, 0.0),
                MIDDLE_TIP: (0.5, 0.7, 0.0), MIDDLE_PIP: (0.5, 0.6, 0.0),  MIDDLE_MCP: (0.5, 0.55, 0.0),
                RING_TIP:   (0.5, 0.7, 0.0), RING_PIP:   (0.5, 0.6, 0.0),  RING_MCP:   (0.5, 0.55, 0.0),
                PINKY_TIP:  (0.5, 0.7, 0.0), PINKY_PIP:  (0.5, 0.6, 0.0),  PINKY_MCP:  (0.5, 0.55, 0.0),
                WRIST:      (0.5, 0.8, 0.0),
            }),
            _random_hand(),
        ]
        for i in range(1000):
            cmds = mapper.map(gestures[i % len(gestures)])
            assert isinstance(cmds, list)
