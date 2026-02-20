"""
conftest.py
Shared pytest fixtures for the GestureLink test suite.
"""

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so src packages are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.vision.gesture_detector import HandResult, Landmark
from src.vision.gesture_mapper import GestureMapper


# ---------------------------------------------------------------------------
# Helpers to build synthetic HandResult objects
# ---------------------------------------------------------------------------

def _make_landmarks(positions: dict) -> list:
    """
    Build a 21-landmark list.
    positions: dict of {index: (x, y, z)} for landmarks you want to set.
    Everything else defaults to (0.5, 0.5, 0.0).
    """
    lms = [Landmark(0.5, 0.5, 0.0) for _ in range(21)]
    for idx, (x, y, z) in positions.items():
        lms[idx] = Landmark(x, y, z)
    return lms


def make_hand(positions: dict, handedness: str = "Right") -> HandResult:
    return HandResult(landmarks=_make_landmarks(positions), handedness=handedness)


# MediaPipe landmark indices used in tests
WRIST          = 0
THUMB_TIP      = 4
THUMB_IP       = 3
INDEX_MCP      = 5
INDEX_TIP      = 8
INDEX_PIP      = 6
MIDDLE_MCP     = 9
MIDDLE_TIP     = 12
MIDDLE_PIP     = 10
RING_MCP       = 13
RING_TIP       = 16
RING_PIP       = 14
PINKY_MCP      = 17
PINKY_TIP      = 20
PINKY_PIP      = 18


@pytest.fixture()
def default_mapper() -> GestureMapper:
    return GestureMapper(screen_w=1920, screen_h=1080)
