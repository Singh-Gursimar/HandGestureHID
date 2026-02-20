/*
 * hid_driver.cpp
 * Main entry point for the GestureLink HID driver.
 *
 * Reads a simple text-based command protocol from stdin (one command per line)
 * and dispatches to the appropriate uinput virtual device.
 *
 * Protocol
 * --------
 *   MOUSE_MOVE   <x> <y>          - absolute cursor position (pixels)
 *   MOUSE_LEFT                    - left click
 *   MOUSE_RIGHT                   - right click
 *   MOUSE_SCROLL  <delta>         - scroll wheel (+up / -down)
 *   GAMEPAD_BTN   <name> <1|0>    - press / release button (A/B/X/Y/LB/RB/START/SELECT)
 *   GAMEPAD_STICK <x> <y>         - left stick (-32767..32767)
 *   QUIT                          - graceful shutdown
 *
 * Usage
 * -----
 *   ./hid_driver [screen_width] [screen_height]
 *   python3 main.py | ./hid_driver 1920 1080
 */

#include "virtual_hid.h"

#include <linux/input-event-codes.h>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <csignal>
#include <atomic>

static std::atomic<bool> g_running{true};

static void signal_handler(int /*sig*/) {
    g_running = false;
}

static const std::unordered_map<std::string, VirtualHID::GamepadBtn> kBtnMap = {
    {"A",      VirtualHID::GamepadBtn::A},
    {"B",      VirtualHID::GamepadBtn::B},
    {"X",      VirtualHID::GamepadBtn::X},
    {"Y",      VirtualHID::GamepadBtn::Y},
    {"LB",     VirtualHID::GamepadBtn::LB},
    {"RB",     VirtualHID::GamepadBtn::RB},
    {"START",  VirtualHID::GamepadBtn::START},
    {"SELECT", VirtualHID::GamepadBtn::SELECT},
};

int main(int argc, char* argv[])
{
    std::signal(SIGINT,  signal_handler);
    std::signal(SIGTERM, signal_handler);

    int screen_w = 1920;
    int screen_h = 1080;
    if (argc >= 3) {
        screen_w = std::atoi(argv[1]);
        screen_h = std::atoi(argv[2]);
    }

    VirtualHID::MouseState   mouse;
    VirtualHID::GamepadState gamepad;

    if (!VirtualHID::mouse_open(mouse, screen_w, screen_h)) {
        std::cerr << "[hid_driver] Failed to create virtual mouse.\n";
        return 1;
    }
    if (!VirtualHID::gamepad_open(gamepad)) {
        std::cerr << "[hid_driver] Failed to create virtual gamepad.\n";
        VirtualHID::mouse_close(mouse);
        return 1;
    }

    std::cerr << "[hid_driver] Ready. Listening on stdin...\n";

    std::string line;
    while (g_running && std::getline(std::cin, line)) {
        if (line.empty() || line[0] == '#') continue;

        std::istringstream ss(line);
        std::string cmd;
        ss >> cmd;

        if (cmd == "QUIT") {
            break;
        }
        else if (cmd == "MOUSE_MOVE") {
            int x, y;
            if (ss >> x >> y) {
                VirtualHID::mouse_move_abs(mouse, x, y);
            }
        }
        else if (cmd == "MOUSE_LEFT") {
            VirtualHID::mouse_click(mouse, BTN_LEFT);
        }
        else if (cmd == "MOUSE_RIGHT") {
            VirtualHID::mouse_click(mouse, BTN_RIGHT);
        }
        else if (cmd == "MOUSE_SCROLL") {
            int delta;
            if (ss >> delta) {
                VirtualHID::mouse_scroll(mouse, delta);
            }
        }
        else if (cmd == "GAMEPAD_BTN") {
            std::string name;
            int state;
            if (ss >> name >> state) {
                auto it = kBtnMap.find(name);
                if (it != kBtnMap.end()) {
                    VirtualHID::gamepad_button(gamepad, it->second, state != 0);
                } else {
                    std::cerr << "[hid_driver] Unknown gamepad button: " << name << '\n';
                }
            }
        }
        else if (cmd == "GAMEPAD_STICK") {
            int x, y;
            if (ss >> x >> y) {
                VirtualHID::gamepad_stick(gamepad, x, y);
            }
        }
        else {
            std::cerr << "[hid_driver] Unknown command: " << cmd << '\n';
        }
    }

    VirtualHID::mouse_close(mouse);
    VirtualHID::gamepad_close(gamepad);
    std::cerr << "[hid_driver] Exited cleanly.\n";
    return 0;
}
