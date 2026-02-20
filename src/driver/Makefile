# Makefile – GestureLink HID Driver
# Targets: hid_driver (default), clean

CXX      := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -Wpedantic -pthread
LDFLAGS  :=

TARGET   := hid_driver
SRCS     := hid_driver.cpp virtual_hid.cpp
OBJS     := $(SRCS:.cpp=.o)

.PHONY: all clean install check-uinput

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)
	@echo "Build successful: ./$(TARGET)"

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

# Quick sanity-check: ensure uinput module is loaded
check-uinput:
	@lsmod | grep uinput > /dev/null 2>&1 || \
	  (echo "Loading uinput kernel module..." && sudo modprobe uinput)
	@ls -la /dev/uinput 2>/dev/null || \
	  (echo "ERROR: /dev/uinput not found even after modprobe." && exit 1)
	@echo "/dev/uinput is available."

# Optional: install to /usr/local/bin (requires sudo)
install: $(TARGET)
	install -m 755 $(TARGET) /usr/local/bin/gesture_hid_driver
	@echo "Installed to /usr/local/bin/gesture_hid_driver"

clean:
	rm -f $(OBJS) $(TARGET)
	@echo "Cleaned build artifacts."
