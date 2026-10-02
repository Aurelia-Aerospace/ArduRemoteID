#pragma once
#include "FS.h"
#include <cstring>

// Base path for data files — relative to where the test binary runs
static const char *SPIFFS_BASE = nullptr; // set before use

class SPIFFSClass {
public:
    bool begin(bool) { return true; }

    File open(const char *path, const char * /*mode*/) {
        // Map SPIFFS path "/foo.txt" -> SPIFFS_BASE + "/foo.txt"
        char full[512];
        const char *base = SPIFFS_BASE ? SPIFFS_BASE : "../airport_check";
        snprintf(full, sizeof(full), "%s%s", base, path);
        FILE *fp = fopen(full, "rb");
        return File(fp);
    }
} static SPIFFS;
