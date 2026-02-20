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
Bash
# Clone the repository
git clone https://github.com/Singh-Gursimar/HandGestureHID

# Build the C++ HID Interface
cd src/driver && make

# Launch the gesture mapping engine
python3 main.py --device /dev/uinput
