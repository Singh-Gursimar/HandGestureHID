Gesture-Link: Virtual HID Linux Application
A low-latency, kernel-level interface that translates real-time hand gestures into system-wide Human Interface Device (HID) commands. Designed for Fedora Linux, this project replaces traditional controllers with AI-driven vision for emulators and accessibility applications.

## Core Features
Real-Time Gesture Processing: Leverages a C++ backend and OpenCV to process hand landmarks with sub-15ms latency.
Virtual Input Mapping: Uses uinput to create a virtual mouse and gamepad at the kernel level, ensuring compatibility with any Linux application.
Performance Optimization: Tailored for Intel processors to minimize CPU overhead during continuous video stream analysis.
Automated Validation: Includes a Python-based test suite that simulates gesture inputs to validate driver stability and coordinate precision.

## Tech Stack
Systems: C++, Linux Kernel (uinput), Bash.
AI/Vision: Python, OpenCV, MediaPipe.
Environment: Fedora Linux, Intel Core Architecture.
Automation: Pytest for regression and signal integrity testing.

## Architecture & Engineering
### 1. Low-Latency Data Pipeline
To meet RTOS-style performance constraints, the system utilizes a multi-threaded architecture. The vision thread handles frame capture, while a high-priority C++ thread handles the virtual device interrupts.

### 2. Automated Testing & Triage
The project features a dedicated tests/ directory containing:
Stress Tests: Python scripts that flood the driver with rapid-fire inputs to check for memory leaks or buffer overflows.
Signal Integrity: Validates that the coordinate mapping accurately reflects normalized hand positions across different screen resolutions.

### 3. Static & Dynamic Analysis
The codebase was refined using linters and memory profiling tools to ensure safety-critical stability, preventing system-wide hangs or kernel panics during input redirection.

## Getting Started

### Prerequisites
- **Fedora Linux** (primary target) or Debian/Ubuntu
- GCC / G++ with C++17 support
- Python 3.10+
- A webcam
- `/dev/uinput` access (the setup script handles this)

### Quick Start
```bash
# Clone the repository
git clone https://github.com/Singh-Gursimar/HandGestureHID
cd HandGestureHID

# One-command setup (installs deps, downloads model, builds driver, runs tests)
bash setup.sh

# Activate the virtualenv and run
source .venv/bin/activate
python3 main.py --preview
```

### Manual Build
```bash
# Build the C++ HID driver
cd src/driver && make

# Download the MediaPipe hand-landmarker model
mkdir -p models
wget -O models/hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task

# Install Python dependencies
python3 -m venv .venv && source .venv/bin/activateGesture-Link: Virtual HID Linux Driver
A low-latency, kernel-level interface that translates real-time hand gestures into system-wide Human Interface Device (HID) commands. Designed for Fedora Linux, this project replaces traditional controllers with AI-driven vision for emulators and accessibility applications.

## Core Features
Real-Time Gesture Processing: Leverages a C++ backend and OpenCV to process hand landmarks with sub-15ms latency.

Virtual Input Mapping: Uses uinput to create a virtual mouse and gamepad at the kernel level, ensuring compatibility with any Linux application.

Performance Optimization: Tailored for Intel processors to minimize CPU overhead during continuous video stream analysis.

Automated Validation: Includes a Python-based test suite that simulates gesture inputs to validate driver stability and coordinate precision.

## Tech Stack
Systems: C++, Linux Kernel (uinput), Bash.

AI/Vision: Python, OpenCV, MediaPipe.

Environment: Fedora Linux, Intel Core Architecture.


Automation: Pytest for regression and signal integrity testing.

## Architecture & Engineering
### 1. Low-Latency Data Pipeline
To meet RTOS-style performance constraints, the system utilizes a multi-threaded architecture. The vision thread handles frame capture, while a high-priority C++ thread handles the virtual device interrupts.

### 2. Automated Testing & Triage
The project features a dedicated tests/ directory containing:

Stress Tests: Python scripts that flood the driver with rapid-fire inputs to check for memory leaks or buffer overflows.

Signal Integrity: Validates that the coordinate mapping accurately reflects normalized hand positions across different screen resolutions.

### 3. Static & Dynamic Analysis
The codebase was refined using linters and memory profiling tools to ensure safety-critical stability, preventing system-wide hangs or kernel panics during input redirection.

## Getting Started
Bash
# Clone the repository
git clone https://github.com/gursimar-kalsi/gesture-link

# Build the C++ HID Interface
cd src/driver && make

# Launch the gesture mapping engine
python3 main.py --device /dev/uinput
Would you like me to add a "Testing" section to this README that explains how you used Pytest to triage bugs in the driver's signal processing?
pip install -r requirements.txt

# Launch the gesture mapping engine
python3 main.py --device /dev/uinput --preview

# Or dry-run without uinput access (prints HID commands to stdout)
python3 main.py --no-driver
```

### Running Tests
```bash
source .venv/bin/activate
python3 -m pytest tests/ -v
```

## Project Structure
```
HandGestureHID/
├── main.py                          # Entry point – orchestrates pipeline
├── requirements.txt                 # Python dependencies
├── setup.sh                         # One-command bootstrap (Fedora / Debian)
├── models/
│   └── hand_landmarker.task         # MediaPipe model (downloaded by setup.sh)
├── src/
│   ├── driver/
│   │   ├── Makefile                 # Build rules for the C++ driver
│   │   ├── virtual_hid.h / .cpp    # uinput virtual mouse + gamepad
│   │   └── hid_driver.cpp          # stdin command protocol dispatcher
│   └── vision/
│       ├── gesture_detector.py      # MediaPipe HandLandmarker (threaded)
│       └── gesture_mapper.py        # Gesture → HID command mapping
└── tests/
    ├── conftest.py                  # Shared fixtures & synthetic hand builder
    ├── test_signal_integrity.py     # Coordinate / click / gamepad tests
    └── test_stress.py               # Throughput & rapid-fire tests
```

## Gesture Mapping

| Gesture | HID Action |
|---|---|
| Index finger point | Mouse cursor (absolute) |
| Pinch (thumb + index) | Left click |
| V-sign (index + middle) | Right click |
| Thumb up / down | Scroll wheel |
| Fist (hold) | Gamepad A button |
| Open palm (5 fingers) | Gamepad START |
| Three middle fingers | Gamepad left stick |
