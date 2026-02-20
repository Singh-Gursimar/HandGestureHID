#ifndef VIRTUAL_HID_H
#define VIRTUAL_HID_H
/*
 * virtual_hid.h
 * Kernel-level virtual HID interface using Linux uinput.
 * Creates virtual mouse and gamepad devices accessible system-wide.
 */

#include <string>
#include <cstdint>

namespace VirtualHID {

// ---------- Mouse ----------------------------------------------------------

struct MouseState {
    int   fd          = -1;
    int   screen_w    = 1920;
    int   screen_h    = 1080;
};

/**
 * Open /dev/uinput and register a virtual absolute mouse.
 * @return true on success.
 */
bool mouse_open(MouseState& ms, int screen_w = 1920, int screen_h = 1080);

/**
 * Move the virtual cursor to absolute (x, y) in screen pixels.
 */
void mouse_move_abs(const MouseState& ms, int x, int y);

/**
 * Emit a left/right/middle button click (press + release).
 * @param button  BTN_LEFT | BTN_RIGHT | BTN_MIDDLE
 */
void mouse_click(const MouseState& ms, uint16_t button);

/**
 * Emit a scroll wheel event. delta > 0 = scroll up.
 */
void mouse_scroll(const MouseState& ms, int delta);

/** Destroy the virtual mouse device and close the fd. */
void mouse_close(MouseState& ms);


// ---------- Gamepad --------------------------------------------------------

/** Gamepad button bit-flags (matching evdev BTN_* constants). */
enum class GamepadBtn : uint16_t {
    A      = 0x130,   // BTN_SOUTH
    B      = 0x131,   // BTN_EAST
    X      = 0x133,   // BTN_NORTH
    Y      = 0x134,   // BTN_WEST
    LB     = 0x136,   // BTN_TL
    RB     = 0x137,   // BTN_TR
    SELECT = 0x138,   // BTN_SELECT
    START  = 0x139,   // BTN_START
};

struct GamepadState {
    int fd = -1;
};

/**
 * Open /dev/uinput and register a virtual gamepad (Xbox-style layout).
 * @return true on success.
 */
bool gamepad_open(GamepadState& gs);

/**
 * Press or release a gamepad button.
 * @param pressed  true = press, false = release
 */
void gamepad_button(const GamepadState& gs, GamepadBtn btn, bool pressed);

/**
 * Set left analogue stick position. x/y in range [-32767, 32767].
 */
void gamepad_stick(const GamepadState& gs, int x, int y);

/** Destroy the virtual gamepad device and close the fd. */
void gamepad_close(GamepadState& gs);

} // namespace VirtualHID

#endif // VIRTUAL_HID_H
