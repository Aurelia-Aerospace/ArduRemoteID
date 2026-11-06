#pragma once

#if defined(BOARD_AURELIA_RID_S3)
#include "SPIFFS.h"
#include <math.h>
#include "spiffs_utils.h"
#include "transport.h"

typedef struct {
    double lat;
    double lon;
} Coordinate;

class FlightChecks {
public:
    struct __attribute__((packed)) ZoneTile {
        int8_t   lat_tile;
        int8_t   lon_tile;
        uint16_t _pad;
        uint32_t offset;   // relative to zones_data_off
    };

    FlightChecks(Transport &transport) : t(transport) {}

    String is_flying_allowed();

    void update_location(double lat, double lon, float alt_m = 0.0f) {
        origin.lat = lat;
        origin.lon = lon;
        origin_alt_m = alt_m;
    }

    bool get_files_read() const { return files_read; }
    // last is_flying_allowed() hit a locked zone (status 3); false for a deadline zone with no valid time (status 1)
    bool get_zone_locked() const { return zone_locked; }
    void init();

    bool zone_ok(uint32_t zone_id, uint32_t until = 0);  // add/overwrite in unlock list + persist; until 0 = no deadline; false = full or NVS failed
    bool zone_ok(const char *arg);                       // ZONE_OK "<id>", strict; false = rejected
    bool zone_ok_until(const char *arg);                 // "<id>,<deadline_unix_s>", strict; false = rejected
    bool zone_lock(uint32_t zone_id);  // remove from unlock list + persist; false = NVS failed
    bool zone_lock(const char *arg);   // ZONE_LOCK "<id>", strict; false = rejected
    void zone_clear();                  // clear unlock list + persist

private:
    bool checkEdge(double x, double y, double x1, double y1, double x2, double y2);
    double degrees_to_radians(double degrees);
    double radians_to_degrees(double radians);

    void load_zones_binary();
    void scan_tile(double lat, double lon, float alt_m, String &ret, bool &truncated);
    bool check_circle(double lat, double lon, double clat, double clon, double radius_m);
    bool check_polygon_deltas(double lat, double lon, double clat, double clon,
                              const uint8_t *delta_buf, uint8_t n_pts);
    bool is_inside_country(double lat, double lon);
    void load_unlocked_zones();
    bool save_unlocked_zones();
    int  find_unlocked(uint32_t zone_id);
    bool is_zone_unlocked(uint32_t zone_id);
    void report_hit(uint32_t zone_id, uint8_t cat, uint32_t &reported_cats, String &ret, bool &truncated);
    uint32_t unix_time();   // seconds, from the ODID System timestamp; 0 = no valid time

    bool spiffs_mounted = true;

    static bool       files_read;
    static Coordinate origin;
    static float      origin_alt_m;

    static ZoneTile*  tile_index;
    static uint16_t   n_tiles;
    static uint8_t    tile_deg;
    static uint32_t   zones_data_off;
    static uint32_t   country_offset;
    static uint8_t*   country_data;
    static uint32_t   country_data_size;

    static int8_t     cached_lat_tile;
    static int8_t     cached_lon_tile;
    static uint8_t*   tile_cache;
    static uint32_t   tile_cache_bytes;

    struct UnlockedZone { uint32_t id, until; };
    static UnlockedZone unlocked_zones[32];
    static uint8_t    n_unlocked;
    static uint32_t   now_s;        // unix_time() taken once per is_flying_allowed()
    static bool       zone_locked;

public:
    static uint32_t   last_scan_us;   // scan duration set by is_flying_allowed(), read by bench

    Transport &t;
};

extern FlightChecks flight_checks;
#endif
