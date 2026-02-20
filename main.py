#!/usr/bin/env python3
"""
main.py Virtual HID Linux Application
=====================================================
Launches the gesture detection pipeline and pipes HID commands
to the compiled C++ hid_driver binary via subprocess.

Usage
-----
    python3 main.py [OPTIONS]

Options
-------
    --device PATH       Path to /dev/uinput  (default: /dev/uinput, passed to driver)
    --camera INT        Camera device index  (default: 0)
    --width  INT        Screen width  for coordinate mapping (default: 1920)
    --height INT        Screen height for coordinate mapping (default: 1080)
    --preview           Show a live annotated camera preview window
    --no-driver         Print commands to stdout instead of piping to hid_driver
                        (useful for testing without /dev/uinput access)
    --driver-bin PATH   Path to hid_driver binary (default: src/driver/hid_driver)
"""

from __future__ import annotations

import argparse
import os
import queue
import subprocess
import sys
import threading
import time
import signal
from pathlib import Path

# pip-installed OpenCV uses Qt for its GUI.  On Wayland + GNOME the Qt
# wayland plugin is missing, so force the XCB (X11) platform instead.
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

# Prefer V4L2 over GStreamer for camera capture (avoids pipeline errors)
os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_GSTREAMER", "0")

import cv2

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent))

from src.vision.gesture_detector import GestureDetector
from src.vision.gesture_mapper import GestureMapper
from src.vision.hud_overlay import HudOverlay


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GestureLink – Hand Gesture Virtual HID")
    p.add_argument("--device",     default="/dev/uinput",
                   help="uinput device path (passed to driver)")
    p.add_argument("--camera",     type=int, default=0,
                   help="Camera device index")
    p.add_argument("--width",      type=int, default=1920,
                   help="Screen width  (pixels)")
    p.add_argument("--height",     type=int, default=1080,
                   help="Screen height (pixels)")
    p.add_argument("--preview",    action="store_true",
                   help="Show a live annotated preview window with HUD")
    p.add_argument("--no-preview", dest="preview", action="store_false",
                   help="Disable the live preview window")
    p.add_argument("--no-driver",  action="store_true",
                   help="Print commands to stdout instead of piping to hid_driver")
    p.add_argument("--driver-bin", default="src/driver/hid_driver",
                   help="Path to compiled hid_driver binary")
    return p.parse_args()


# --------------------------------------------------------------------------- #
#  Writer thread: consumes command strings and forwards to the driver          #
# --------------------------------------------------------------------------- #
class CommandWriter(threading.Thread):
    """Thread that drains a command queue and writes to the driver stdin."""

    def __init__(self, cmd_q: queue.Queue, dest, dry_run: bool = False) -> None:
        super().__init__(name="CommandWriter", daemon=True)
        self.cmd_q   = cmd_q
        self.dest    = dest      # subprocess.Popen or None (dry-run → stdout)
        self.dry_run = dry_run
        self._stop   = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                cmd: str = self.cmd_q.get(timeout=0.05)
            except queue.Empty:
                continue

            line = cmd + "\n"
            try:
                if self.dry_run or self.dest is None:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    self.dest.stdin.write(line.encode())
                    self.dest.stdin.flush()
            except (BrokenPipeError, OSError):
                break


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #
def main() -> None:
    args = parse_args()

    # ---- Start C++ driver subprocess ----------------------------------------
    driver_proc: subprocess.Popen | None = None
    if not args.no_driver:
        driver_bin = Path(args.driver_bin)
        if not driver_bin.exists():
            print(
                f"[main] Driver binary not found at '{driver_bin}'.\n"
                f"       Build it first:  cd src/driver && make\n"
                f"       Or use --no-driver to print commands instead.",
                file=sys.stderr,
            )
            sys.exit(1)

        driver_proc = subprocess.Popen(
            [str(driver_bin), str(args.width), str(args.height)],
            stdin=subprocess.PIPE,
            stderr=sys.stderr,
        )
        print(f"[main] Started hid_driver (PID {driver_proc.pid})", file=sys.stderr)
    else:
        print("[main] --no-driver: commands will be printed to stdout.", file=sys.stderr)

    # ---- Gesture detection pipeline -----------------------------------------
    result_q: queue.Queue = queue.Queue(maxsize=8)
    cmd_q:    queue.Queue = queue.Queue(maxsize=32)

    detector = GestureDetector(
        camera_index=args.camera,
        max_hands=1,
        output_queue=result_q,
        frame_width=640,
        frame_height=480,
    )
    mapper = GestureMapper(screen_w=args.width, screen_h=args.height)
    writer = CommandWriter(cmd_q, driver_proc, dry_run=args.no_driver)
    hud    = HudOverlay()

    # ---- Graceful shutdown ---------------------------------------------------
    shutdown = threading.Event()

    def _shutdown(*_) -> None:
        print("\n[main] Shutting down…", file=sys.stderr)
        shutdown.set()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ---- Start threads -------------------------------------------------------
    detector.start()
    writer.start()

    fps_t0    = time.monotonic()
    fps_count = 0

    preview_ok = args.preview  # may be disabled on first failure

    print("[main] Pipeline running. Press Ctrl+C to stop.", file=sys.stderr)
    if preview_ok:
        print("[main] Preview window enabled (press 'q' in the window to quit).",
              file=sys.stderr)

    try:
        while not shutdown.is_set():
            # Drain detector queue → mapper → command queue
            try:
                hand = result_q.get(timeout=0.05)
            except queue.Empty:
                # Even without a hand, keep the preview alive
                if preview_ok:
                    frame = detector.latest_frame()
                    if frame is not None:
                        hud.update(None, [])
                        hud.draw(frame)
                        try:
                            cv2.imshow("GestureLink Preview", frame)
                        except cv2.error:
                            preview_ok = False
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            shutdown.set()
                continue

            cmds = mapper.map(hand)
            for c in cmds:
                try:
                    cmd_q.put_nowait(c)
                except queue.Full:
                    pass  # Drop if writer can't keep up

            # Update the HUD with latest gesture & commands
            hud.update(hand, cmds)

            fps_count += 1
            elapsed = time.monotonic() - fps_t0
            if elapsed >= 5.0:
                print(f"[main] Throughput: {fps_count / elapsed:.1f} gestures/s",
                      file=sys.stderr)
                fps_t0, fps_count = time.monotonic(), 0

            # Preview window with HUD overlay
            if preview_ok:
                frame = detector.latest_frame()
                if frame is not None:
                    hud.draw(frame)
                    try:
                        cv2.imshow("GestureLink Preview", frame)
                    except cv2.error:
                        print("[main] Display unavailable – disabling preview.",
                              file=sys.stderr)
                        preview_ok = False
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        shutdown.set()

    finally:
        detector.stop()
        writer.stop()
        if preview_ok:
            cv2.destroyAllWindows()
        if driver_proc is not None:
            try:
                driver_proc.stdin.write(b"QUIT\n")
                driver_proc.stdin.flush()
                driver_proc.stdin.close()
            except OSError:
                pass
            driver_proc.wait(timeout=3)
        print("[main] Goodbye.", file=sys.stderr)


if __name__ == "__main__":
    main()
