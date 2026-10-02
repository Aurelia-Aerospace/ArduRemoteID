#pragma once
#include "Arduino.h"
#include <cstdio>
#include <cstring>
#include <sys/stat.h>

#define FILE_READ "rb"

class File {
    FILE *fp = nullptr;
    long fsize = 0;
public:
    File() = default;
    explicit File(FILE *f) : fp(f) {
        if (fp) {
            struct stat st;
            fstat(fileno(fp), &st);
            fsize = st.st_size;
        }
    }
    explicit operator bool() const { return fp != nullptr; }
    bool available() const { return fp && !feof(fp); }
    size_t size() const { return (size_t)fsize; }
    void close() { if (fp) { fclose(fp); fp = nullptr; } }
    void seek(long pos) { if (fp) fseek(fp, pos, SEEK_SET); }
    size_t read(uint8_t *buf, size_t n) { return fp ? fread(buf, 1, n, fp) : 0; }
    size_t position() const { return fp ? (size_t)ftell(fp) : 0; }

    String readStringUntil(char delim) {
        if (!fp) return String("");
        std::string result;
        int c;
        while ((c = fgetc(fp)) != EOF) {
            if (c == delim) break;
            result += (char)c;
        }
        return String(result);
    }
};
