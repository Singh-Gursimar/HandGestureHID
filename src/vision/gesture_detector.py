"""
gesture_detector.py
Real-time hand landmark detection using the MediaPipe Tasks HandLandmarker API
(mediapipe >= 0.10).  Runs in a dedicated thread, publishing results via a queue.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2

# ---------------------------------------------------------------------------
# MediaPipe landmark indices (fixed across all API versions)
# ---------------------------------------------------------------------------
class LM:  # noqa: N801
    WRIST               = 0
    THUMB_CMC           = 1
    THUMB_MCP           = 2
    THUMB_IP            = 3
    THUMB_TIP           = 4
    INDEX_FINGER_MCP    = 5
    INDEX_FINGER_PIP    = 6
    INDEX_FINGER_DIP    = 7
    INDEX_FINGER_TIP    = 8
    MIDDLE_FINGER_MCP   = 9
    MIDDLE_FINGER_PIP   = 10
    MIDDLE_FINGER_DIP   = 11
    MIDDLE_FINGER_TIP   = 12
    RING_FINGER_MCP     = 13
    RING_FINGER_PIP     = 14
    RING_FINGER_DIP     = 15
    RING_FINGER_TIP     = 16
    PINKY_MCP           = 17
    PINKY_PIP           = 18
    PINKY_DIP           = 19
    PINKY_TIP           = 20


@dataclass
class Landmark:
    x: float  # normalised [0, 1]
    y: float  # normalised [0, 1]
    z: float  # depth (relative to wrist)


@dataclass
class HandResult:
    """Processed result for a single detected hand."""
    landmarks: List[Landmark]
    handedness: str          # "Left" or "Right"
    timestamp_ms: float = field(default_factory=lambda: time.monotonic() * 1000)

    # ------------------------------------------------------------------ helpers

    def lm(self, idx: int) -> Landmark:
        """Return a single landmark by index."""
        return self.landmarks[idx]

    def fingertip(self, finger: int) -> Landmark:
        """
        Return the fingertip for a given finger (0=thumb, 1=index, …, 4=pinky).
        """
        tips = [LM.THUMB_TIP, LM.INDEX_FINGER_TIP, LM.MIDDLE_FINGER_TIP,
                LM.RING_FINGER_TIP, LM.PINKY_TIP]
        return self.lm(tips[finger])

    def finger_extended(self, finger: int) -> bool:
        """
        Return True if the given finger appears extended.

        For index–pinky the finger is extended when both:
          • tip is above the PIP joint, AND
          • tip is above the MCP joint.
        This two-joint check is far more robust than tip-vs-pip alone,
        reducing flicker when a finger is half-curled.

        For the thumb: compare how far the tip is from the wrist vs the
        IP joint (works for both left and right hands).
        """
        tips = [LM.THUMB_TIP, LM.INDEX_FINGER_TIP, LM.MIDDLE_FINGER_TIP,
                LM.RING_FINGER_TIP, LM.PINKY_TIP]
        pips = [LM.THUMB_IP,  LM.INDEX_FINGER_PIP, LM.MIDDLE_FINGER_PIP,
                LM.RING_FINGER_PIP, LM.PINKY_PIP]
        mcps = [LM.THUMB_MCP, LM.INDEX_FINGER_MCP, LM.MIDDLE_FINGER_MCP,
                LM.RING_FINGER_MCP, LM.PINKY_MCP]

        tip = self.lm(tips[finger])
        pip = self.lm(pips[finger])
        mcp = self.lm(mcps[finger])

        if finger == 0:          # thumb – compare x distance from wrist
            wrist = self.lm(LM.WRIST)
            return abs(tip.x - wrist.x) > abs(pip.x - wrist.x)
        # Two-joint check for index–pinky
        return tip.y < pip.y and tip.y < mcp.y

    def extended_count(self) -> int:
        return sum(self.finger_extended(i) for i in range(5))

    def pinch_distance(self) -> float:
        """Euclidean distance (normalised) between thumb tip and index tip."""
        t = self.fingertip(0)
        i = self.fingertip(1)
        return ((t.x - i.x) ** 2 + (t.y - i.y) ** 2) ** 0.5

    def index_tip_position(self) -> Tuple[float, float]:
        """Return (x, y) normalised position of the index fingertip."""
        lm = self.fingertip(1)
        return lm.x, lm.y


class GestureDetector:
    """
    Captures frames from a camera, detects hand landmarks,
    and puts HandResult objects into an output queue.
    """

    def __init__(
        self,
        camera_index: int = 0,
        max_hands: int = 1,
        detection_confidence: float = 0.7,
        tracking_confidence: float = 0.6,
        output_queue: Optional[queue.Queue] = None,
        frame_width: int = 640,
        frame_height: int = 480,
    ) -> None:
        self.camera_index = camera_index
        self.max_hands = max_hands
        self.det_conf = detection_confidence
        self.trk_conf = tracking_confidence
        self.out_q: queue.Queue = output_queue or queue.Queue(maxsize=4)
        self.frame_w = frame_width
        self.frame_h = frame_height

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Shared annotated frame for optional preview window
        self._latest_frame: Optional[cv2.typing.MatLike] = None
        self._frame_lock = threading.Lock()

    # ------------------------------------------------------------------ public

    def start(self) -> None:
        """Start the detector in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="GestureDetector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the detector to stop and join its thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    @property
    def queue(self) -> queue.Queue:
        return self.out_q

    def latest_frame(self) -> Optional[cv2.typing.MatLike]:
        """Return the most recently annotated frame (thread-safe, may be None)."""
        with self._frame_lock:
            return self._latest_frame

    # ----------------------------------------------------------------- private

    def _run(self) -> None:
        # Lazy imports – only needed at runtime, not during unit tests
        from mediapipe.tasks.python.core.base_options import BaseOptions
        from mediapipe.tasks.python.vision.hand_landmarker import (
            HandLandmarker, HandLandmarkerOptions,
        )
        from mediapipe.tasks.python.vision.core.vision_task_running_mode import (
            VisionTaskRunningMode,
        )
        from mediapipe.tasks.python.vision.core.image import Image as MpImage, ImageFormat

        # Resolve model path relative to this file (repo_root/models/)
        _repo_root = Path(__file__).parent.parent.parent
        _model_path = _repo_root / "models" / "hand_landmarker.task"
        if not _model_path.exists():
            raise FileNotFoundError(
                f"Hand landmarker model not found at {_model_path}.\n"
                f"Download it with:\n"
                f"  wget -O {_model_path} "
                "https://storage.googleapis.com/mediapipe-models/"
                "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
            )

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(_model_path)),
            running_mode=VisionTaskRunningMode.VIDEO,
            num_hands=self.max_hands,
            min_hand_detection_confidence=self.det_conf,
            min_hand_presence_confidence=self.det_conf,
            min_tracking_confidence=self.trk_conf,
        )

        # Use V4L2 directly – the GStreamer backend often fails after
        # an unclean shutdown or on Fedora with missing plugins.
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        if not cap.isOpened():
            # Fallback: let OpenCV auto-detect backend
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera index {self.camera_index}")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.frame_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_h)
        cap.set(cv2.CAP_PROP_FPS, 60)

        with HandLandmarker.create_from_options(options) as landmarker:
            frame_idx = 0
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    continue

                # Flip for mirror view
                frame = cv2.flip(frame, 1)
                rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Create MediaPipe image
                mp_image = MpImage(image_format=ImageFormat.SRGB, data=rgb)
                timestamp_ms = int(time.monotonic() * 1000) + frame_idx
                frame_idx += 1

                detection = landmarker.detect_for_video(mp_image, timestamp_ms)

                if detection.hand_landmarks:
                    for hand_lm_list, hand_info_list in zip(
                        detection.hand_landmarks,
                        detection.handedness,
                    ):
                        # Draw landmarks on the preview frame
                        h, w = frame.shape[:2]
                        for conn_start, conn_end in _HAND_CONNECTIONS:
                            s = hand_lm_list[conn_start]
                            e = hand_lm_list[conn_end]
                            cv2.line(frame,
                                     (int(s.x * w), int(s.y * h)),
                                     (int(e.x * w), int(e.y * h)),
                                     (0, 255, 0), 2)
                        for lm in hand_lm_list:
                            cv2.circle(frame,
                                       (int(lm.x * w), int(lm.y * h)),
                                       4, (0, 0, 255), -1)

                        lm_list = [
                            Landmark(lm.x, lm.y, lm.z)
                            for lm in hand_lm_list
                        ]
                        handedness = (
                            hand_info_list[0].category_name
                            if hand_info_list else "Right"
                        )
                        result = HandResult(
                            landmarks=lm_list,
                            handedness=handedness,
                        )

                        try:
                            self.out_q.put_nowait(result)
                        except queue.Full:
                            try:
                                self.out_q.get_nowait()
                            except queue.Empty:
                                pass
                            self.out_q.put_nowait(result)

                with self._frame_lock:
                    self._latest_frame = frame.copy()

        cap.release()


# Minimal hand connection pairs for drawing (subset of the 21-point skeleton)
_HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),           # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),            # index
    (5, 9), (9, 10), (10, 11), (11, 12),       # middle
    (9, 13), (13, 14), (14, 15), (15, 16),     # ring
    (13, 17), (17, 18), (18, 19), (19, 20),    # pinky
    (0, 17),                                   # palm base
]
