#pragma once
#include <string>
#include <cstdint>
#include <cstdio>
#include <cmath>
#include <cstring>
#include <algorithm>

#ifndef PI
#define PI 3.14159265358979323846
#endif

static inline uint32_t millis() { return 0; }
static inline uint32_t micros() { return 0; }
static inline void delay(int) {}

struct SerialClass {
    void println(const char *s) { (void)s; }
    void println(const char *s, int) { (void)s; }
    template<typename T> void printf(const char *fmt, T a) { (void)fmt; (void)a; }
    template<typename T, typename U> void printf(const char *fmt, T a, U b) { (void)fmt; (void)a; (void)b; }
    template<typename T, typename U, typename V> void printf(const char *fmt, T a, U b, V c) { (void)fmt; (void)a; (void)b; (void)c; }
};
static SerialClass Serial;

// Arduino provides min/max in global namespace
template<typename T> static inline T min(T a, T b) { return a < b ? a : b; }
template<typename T> static inline T max(T a, T b) { return a > b ? a : b; }

// Minimal Arduino String backed by std::string
class String {
    std::string s;
public:
    String() = default;
    String(const char *c) : s(c ? c : "") {}
    String(const std::string &o) : s(o) {}
    String(double v, int decimals=2) { char buf[64]; snprintf(buf,sizeof(buf),"%.*f",decimals,v); s=buf; }
    String(int v) { s = std::to_string(v); }

    int indexOf(char c) const {
        auto p = s.find(c);
        return p == std::string::npos ? -1 : (int)p;
    }
    int indexOf(char c, int from) const {
        auto p = s.find(c, from);
        return p == std::string::npos ? -1 : (int)p;
    }
    String substring(int start) const { return String(s.substr(start)); }
    String substring(int start, int end) const { return String(s.substr(start, end - start)); }
    double toDouble() const { return s.empty() ? 0.0 : std::stod(s); }
    int toInt() const { return s.empty() ? 0 : std::stoi(s); }
    bool startsWith(const char *prefix) const { return s.rfind(prefix, 0) == 0; }
    bool startsWith(const String &prefix) const { return startsWith(prefix.c_str()); }
    size_t length() const { return s.length(); }
    const char *c_str() const { return s.c_str(); }
    String &operator+=(const char *c) { s += c; return *this; }
    String &operator+=(const String &o) { s += o.s; return *this; }
    bool operator==(const char *c) const { return s == c; }
};
