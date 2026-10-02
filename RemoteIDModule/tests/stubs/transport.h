#pragma once
#include <cstdint>

// Stub — only the methods flight_checker uses
class Transport {
public:
    void set_fl_status(uint8_t) {}
    void set_parse_fail(const char *) {}
    void update() {}
};
