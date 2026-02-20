/*
 * virtual_hid.cpp
 * Implementation of the kernel-level virtual HID interface via Linux uinput.
 *
 * Compile with:  g++ -O2 -Wall -Wextra -std=c++17 virtual_hid.cpp -o virtual_hid
 * Requires:      /dev/uinput write permission  (udev rule or run as root in dev)
 */

#include "virtual_hid.h"

#include <fcntl.h>
#include <unistd.h>
#include <cstring>
#include <stdexcept>
#include <iostream>

#include <linux/uinput.h>
#include <linux/input-event-codes.h>

namespace VirtualHID {

// ---- helpers ---------------------------------------------------------------

static void emit(int fd, uint16_t type, uint16_t code, int32_t value)
{
    struct input_event ev{};
    ev.type  = type;
    ev.code  = code;
    ev.value = value;
    if (write(fd, &ev, sizeof(ev)) < 0) {
        std::cerr << "[VirtualHID] emit failed: " << strerror(errno) << '\n';
    }
}

static void syn(int fd)
{
    emit(fd, EV_SYN, SYN_REPORT, 0);
}

static int open_uinput()
{
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) {
        // Fallback path used on some distros
        fd = open("/dev/input/uinput", O_WRONLY | O_NONBLOCK);
    }
    if (fd < 0) {
        throw std::runtime_error(
            std::string("[VirtualHID] Cannot open /dev/uinput: ") + strerror(errno) +
            ". Ensure the uinput kernel module is loaded (modprobe uinput) and "
            "that your user is in the 'input' group or run with appropriate permissions.");
    }
    return fd;
}

// ---- Mouse -----------------------------------------------------------------

bool mouse_open(MouseState& ms, int screen_w, int screen_h)
{
    ms.screen_w = screen_w;
    ms.screen_h = screen_h;

    try { ms.fd = open_uinput(); }
    catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return false;
    }

    // Enable event types
    ioctl(ms.fd, UI_SET_EVBIT,  EV_KEY);
    ioctl(ms.fd, UI_SET_EVBIT,  EV_ABS);
    ioctl(ms.fd, UI_SET_EVBIT,  EV_REL);

    // Mouse buttons
    ioctl(ms.fd, UI_SET_KEYBIT, BTN_LEFT);
    ioctl(ms.fd, UI_SET_KEYBIT, BTN_RIGHT);
    ioctl(ms.fd, UI_SET_KEYBIT, BTN_MIDDLE);

    // Absolute axes for cursor position
    ioctl(ms.fd, UI_SET_ABSBIT, ABS_X);
    ioctl(ms.fd, UI_SET_ABSBIT, ABS_Y);

    // Scroll wheel (relative)
    ioctl(ms.fd, UI_SET_RELBIT, REL_WHEEL);

    struct uinput_user_dev uidev{};
    snprintf(uidev.name, UINPUT_MAX_NAME_SIZE, "GestureLink Virtual Mouse");
    uidev.id.bustype = BUS_VIRTUAL;
    uidev.id.vendor  = 0x1357;
    uidev.id.product = 0x0001;
    uidev.id.version = 1;

    uidev.absmin[ABS_X]  = 0;
    uidev.absmax[ABS_X]  = screen_w - 1;
    uidev.absfuzz[ABS_X] = 0;
    uidev.absflat[ABS_X] = 0;

    uidev.absmin[ABS_Y]  = 0;
    uidev.absmax[ABS_Y]  = screen_h - 1;
    uidev.absfuzz[ABS_Y] = 0;
    uidev.absflat[ABS_Y] = 0;

    if (write(ms.fd, &uidev, sizeof(uidev)) < 0) {
        std::cerr << "[VirtualHID] mouse write uidev failed\n";
        close(ms.fd);
        ms.fd = -1;
        return false;
    }

    if (ioctl(ms.fd, UI_DEV_CREATE) < 0) {
        std::cerr << "[VirtualHID] UI_DEV_CREATE (mouse) failed: " << strerror(errno) << '\n';
        close(ms.fd);
        ms.fd = -1;
        return false;
    }

    std::cout << "[VirtualHID] Virtual mouse created ("
              << screen_w << 'x' << screen_h << ")\n";
    return true;
}

void mouse_move_abs(const MouseState& ms, int x, int y)
{
    if (ms.fd < 0) return;
    // Clamp to screen bounds
    x = std::max(0, std::min(x, ms.screen_w - 1));
    y = std::max(0, std::min(y, ms.screen_h - 1));

    emit(ms.fd, EV_ABS, ABS_X, x);
    emit(ms.fd, EV_ABS, ABS_Y, y);
    syn(ms.fd);
}

void mouse_click(const MouseState& ms, uint16_t button)
{
    if (ms.fd < 0) return;
    emit(ms.fd, EV_KEY, button, 1); // press
    syn(ms.fd);
    emit(ms.fd, EV_KEY, button, 0); // release
    syn(ms.fd);
}

void mouse_scroll(const MouseState& ms, int delta)
{
    if (ms.fd < 0) return;
    emit(ms.fd, EV_REL, REL_WHEEL, delta);
    syn(ms.fd);
}

void mouse_close(MouseState& ms)
{
    if (ms.fd < 0) return;
    ioctl(ms.fd, UI_DEV_DESTROY);
    close(ms.fd);
    ms.fd = -1;
    std::cout << "[VirtualHID] Virtual mouse destroyed\n";
}

// ---- Gamepad ---------------------------------------------------------------

bool gamepad_open(GamepadState& gs)
{
    try { gs.fd = open_uinput(); }
    catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return false;
    }

    ioctl(gs.fd, UI_SET_EVBIT,  EV_KEY);
    ioctl(gs.fd, UI_SET_EVBIT,  EV_ABS);

    // Face buttons + shoulder buttons + meta buttons
    for (uint16_t btn : {
            static_cast<uint16_t>(GamepadBtn::A),
            static_cast<uint16_t>(GamepadBtn::B),
            static_cast<uint16_t>(GamepadBtn::X),
            static_cast<uint16_t>(GamepadBtn::Y),
            static_cast<uint16_t>(GamepadBtn::LB),
            static_cast<uint16_t>(GamepadBtn::RB),
            static_cast<uint16_t>(GamepadBtn::SELECT),
            static_cast<uint16_t>(GamepadBtn::START)
        }) {
        ioctl(gs.fd, UI_SET_KEYBIT, btn);
    }

    // Left stick axes
    ioctl(gs.fd, UI_SET_ABSBIT, ABS_X);
    ioctl(gs.fd, UI_SET_ABSBIT, ABS_Y);

    struct uinput_user_dev uidev{};
    snprintf(uidev.name, UINPUT_MAX_NAME_SIZE, "GestureLink Virtual Gamepad");
    uidev.id.bustype = BUS_VIRTUAL;
    uidev.id.vendor  = 0x1357;
    uidev.id.product = 0x0002;
    uidev.id.version = 1;

    uidev.absmin[ABS_X]  = -32767;
    uidev.absmax[ABS_X]  =  32767;
    uidev.absfuzz[ABS_X] = 16;
    uidev.absflat[ABS_X] = 128;

    uidev.absmin[ABS_Y]  = -32767;
    uidev.absmax[ABS_Y]  =  32767;
    uidev.absfuzz[ABS_Y] = 16;
    uidev.absflat[ABS_Y] = 128;

    if (write(gs.fd, &uidev, sizeof(uidev)) < 0) {
        std::cerr << "[VirtualHID] gamepad write uidev failed\n";
        close(gs.fd);
        gs.fd = -1;
        return false;
    }

    if (ioctl(gs.fd, UI_DEV_CREATE) < 0) {
        std::cerr << "[VirtualHID] UI_DEV_CREATE (gamepad) failed: " << strerror(errno) << '\n';
        close(gs.fd);
        gs.fd = -1;
        return false;
    }

    std::cout << "[VirtualHID] Virtual gamepad created\n";
    return true;
}

void gamepad_button(const GamepadState& gs, GamepadBtn btn, bool pressed)
{
    if (gs.fd < 0) return;
    emit(gs.fd, EV_KEY, static_cast<uint16_t>(btn), pressed ? 1 : 0);
    syn(gs.fd);
}

void gamepad_stick(const GamepadState& gs, int x, int y)
{
    if (gs.fd < 0) return;
    auto clamp = [](int v) { return std::max(-32767, std::min(v, 32767)); };
    emit(gs.fd, EV_ABS, ABS_X, clamp(x));
    emit(gs.fd, EV_ABS, ABS_Y, clamp(y));
    syn(gs.fd);
}

void gamepad_close(GamepadState& gs)
{
    if (gs.fd < 0) return;
    ioctl(gs.fd, UI_DEV_DESTROY);
    close(gs.fd);
    gs.fd = -1;
    std::cout << "[VirtualHID] Virtual gamepad destroyed\n";
}

} // namespace VirtualHID
