#!/usr/bin/env bash
# setup.sh – Bootstrap GestureLink on Fedora Linux (primary target)
#            Also supports Debian/Ubuntu and generic systemd Linux.
# Usage: bash setup.sh
set -euo pipefail

echo "=== GestureLink Setup ==="

# Detect distro
DISTRO=""
if [ -f /etc/os-release ]; then
    # shellcheck source=/dev/null
    source /etc/os-release
    DISTRO="${ID:-}"
fi

# ---- 1. System dependencies --------------------------------------------------
echo "[1/6] Installing system packages (requires sudo)..."

if [[ "$DISTRO" == "fedora" ]] || command -v dnf &>/dev/null; then
    FEDORA_VER=$(rpm -E %fedora 2>/dev/null || echo "unknown")
    echo "  Detected Fedora ${FEDORA_VER}"

    # Core build tools
    sudo dnf install -y \
        gcc-c++ \
        make \
        kernel-devel-"$(uname -r)" \
        kernel-headers-"$(uname -r)" \
        python3-pip \
        python3-devel \
        python3-virtualenv

    # Libraries required by OpenCV / MediaPipe at runtime
    sudo dnf install -y \
        libGL \
        libGLU \
        mesa-libGL \
        mesa-libEGL \
        libXext \
        libXrender \
        libSM \
        glib2

    # Camera / V4L support
    sudo dnf install -y v4l-utils

    # Optional: RPM Fusion (needed for some GStreamer / codec codecs with OpenCV)
    if ! dnf repolist enabled | grep -q rpmfusion; then
        echo "  NOTE: RPM Fusion repos not enabled."
        echo "  For full GStreamer/codec support run:"
        echo "    sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-\$(rpm -E %fedora).noarch.rpm"
    fi

elif command -v apt-get &>/dev/null; then
    echo "  Detected Debian/Ubuntu"
    sudo apt-get update -q
    sudo apt-get install -y \
        g++ \
        make \
        "linux-headers-$(uname -r)" \
        python3-pip \
        python3-dev \
        python3-venv \
        libgl1 \
        libglib2.0-0 \
        v4l-utils

else
    echo "  WARNING: Unknown distro '${DISTRO}'. Ensure g++, make, kernel-devel,"
    echo "           python3-pip, libGL, and libglib2.0 are installed manually."
fi

# ---- 2. uinput kernel module --------------------------------------------------
echo "[2/6] Loading uinput kernel module..."
if ! lsmod | grep -q uinput; then
    sudo modprobe uinput
fi

# Persist across reboots
UINPUT_CONF=/etc/modules-load.d/uinput.conf
if [ ! -f "$UINPUT_CONF" ]; then
    echo "uinput" | sudo tee "$UINPUT_CONF" > /dev/null
    echo "  Created $UINPUT_CONF for persistence."
fi

# Set permissions so the current user can access /dev/uinput
UDEV_RULE=/etc/udev/rules.d/99-uinput.rules
if [ ! -f "$UDEV_RULE" ]; then
    echo 'KERNEL=="uinput", MODE="0660", GROUP="input"' | sudo tee "$UDEV_RULE" > /dev/null
    sudo udevadm control --reload-rules && sudo udevadm trigger
    echo "  Created udev rule: $UDEV_RULE"
fi

# Add current user to the 'input' group (takes effect on next login)
if ! groups "$USER" | grep -q '\binput\b'; then
    sudo usermod -aG input "$USER"
    echo "  Added $USER to 'input' group (re-login required for this to take effect)."
fi

# ---- 3. Download ML model + Build C++ driver ----------------------------------
echo "[3/6] Downloading model & building hid_driver..."

MODEL_DIR="models"
MODEL_FILE="$MODEL_DIR/hand_landmarker.task"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

mkdir -p "$MODEL_DIR"
if [ ! -f "$MODEL_FILE" ]; then
    echo "  Downloading MediaPipe hand_landmarker model..."
    if command -v wget &>/dev/null; then
        wget -q --show-progress -O "$MODEL_FILE" "$MODEL_URL"
    elif command -v curl &>/dev/null; then
        curl -fSL -o "$MODEL_FILE" "$MODEL_URL"
    else
        echo "  ERROR: Neither wget nor curl found. Install one and re-run."
        exit 1
    fi
    echo "  Model saved to $MODEL_FILE"
else
    echo "  Model already exists at $MODEL_FILE"
fi

cd src/driver
make clean && make
cd ../..
echo "  Driver built: src/driver/hid_driver"

# ---- 4. Python dependencies ---------------------------------------------------
echo "[4/6] Installing Python dependencies..."

# Fedora 38+ and many modern distros enforce PEP 668 (no system-wide pip installs).
# Use a virtualenv so pip always works regardless of distro policy.
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating virtualenv at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

# Activate and install
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt
echo "  Python packages installed into $VENV_DIR"
echo "  Activate manually with:  source $VENV_DIR/bin/activate"

# ---- 5. Smoke test ------------------------------------------------------------
echo "[5/6] Running test suite..."
echo "  (no camera or /dev/uinput access required)"
"$VENV_DIR/bin/python" -m pytest tests/ -v --timeout=30

# ---- 6. Summary ---------------------------------------------------------------
echo ""
echo "[6/6] Verifying installation..."
echo "  ✓ C++ driver:  $(file src/driver/hid_driver | cut -d: -f2)"
echo "  ✓ ML model:    $(du -sh models/hand_landmarker.task | cut -f1)"
echo "  ✓ Python venv: $VENV_DIR"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Usage:"
echo "  source $VENV_DIR/bin/activate"
echo "  python3 main.py --preview          # Camera + annotated preview"
echo "  python3 main.py --no-driver        # Dry-run (print HID commands to stdout)"
echo ""
echo "Tests:"
echo "  source $VENV_DIR/bin/activate"
echo "  python3 -m pytest tests/ -v"
