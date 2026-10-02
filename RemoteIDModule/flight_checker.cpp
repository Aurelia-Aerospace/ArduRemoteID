#include "flight_checker.h"

#if defined(BOARD_AURELIA_RID_S3)
#include <Arduino.h>
#include <stdlib.h>
#include <string.h>
#include "parameters.h"

// Static member definitions
Coordinate              FlightChecks::origin;
bool                    FlightChecks::files_read;
float                   FlightChecks::origin_alt_m;
FlightChecks::ZoneTile* FlightChecks::tile_index;
uint16_t                FlightChecks::n_tiles;
uint8_t                 FlightChecks::tile_deg = 4;
uint32_t                FlightChecks::zones_data_off;
uint32_t                FlightChecks::country_offset;
uint8_t*                FlightChecks::country_data;
uint32_t                FlightChecks::country_data_size;
int8_t                  FlightChecks::cached_lat_tile;
int8_t                  FlightChecks::cached_lon_tile;
uint8_t*                FlightChecks::tile_cache;
uint32_t                FlightChecks::tile_cache_bytes;
uint32_t                FlightChecks::unlocked_zones[32];
uint8_t                 FlightChecks::n_unlocked;

uint32_t            FlightChecks::last_scan_us;

static_assert(sizeof(FlightChecks::ZoneTile) == 8, "ZoneTile must be 8 bytes");

// Category (zone_id >> 27) → OPTIONS bypass bit  [5-bit category, zones.bin VERSION=3]
static const uint32_t CAT_BYPASS_BIT[18] = {
    OPTIONS_BYPASS_AIRPORT_L,   // 0
    OPTIONS_BYPASS_AIRPORT_M,   // 1
    OPTIONS_BYPASS_AIRPORT_S,   // 2
    OPTIONS_BYPASS_SEAPLANE,    // 3
    OPTIONS_BYPASS_HELIPORT,    // 4
    OPTIONS_BYPASS_BALLOONPORT, // 5
    OPTIONS_BYPASS_FAA_B,       // 6
    OPTIONS_BYPASS_FAA_C,       // 7
    OPTIONS_BYPASS_FAA_D,       // 8
    OPTIONS_BYPASS_EU_CTR,      // 9
    OPTIONS_BYPASS_EU_ATZ,      // 10
    OPTIONS_BYPASS_EU_R,        // 11
    OPTIONS_BYPASS_EU_TMA,      // 12
    OPTIONS_BYPASS_EU_P,        // 13
    OPTIONS_BYPASS_PRISON,      // 14
    OPTIONS_BYPASS_STADIUM,     // 15
    OPTIONS_BYPASS_MILITARY,    // 16
    OPTIONS_BYPASS_COUNTRY,     // 17 (country is in flat section, not tiles)
};

// Category → GCS message tag
static const char *CAT_MSG[18] = {
    "APT_L ",   "APT_M ",   "APT_S ",   "APT_SEA ", "APT_HEL ", "APT_BAL ",
    "FAA_B ",   "FAA_C ",   "FAA_D ",
    "EU_CTR ",  "EU_ATZ ",  "EU_R ",    "EU_TMA ",  "EU_P ",
    "PRISON ",  "STADIUM ", "MZ ",      "COUNTRY ",
};

static void append_tag(String &ret, const char *tag, bool &truncated)
{
    if (ret.length() + strlen(tag) > 48) {
        ret += "+";
        truncated = true;
    } else {
        ret += tag;
    }
}

void FlightChecks::init()
{
    free(tile_index);   tile_index        = nullptr;
    free(country_data); country_data      = nullptr;
    free(tile_cache);   tile_cache        = nullptr;
    files_read        = false;
    n_tiles           = 0;
    n_unlocked        = 0;
    cached_lat_tile   = -128;
    cached_lon_tile   = -128;
    origin            = {0, 0};
    origin_alt_m      = 0.0f;
    if (!SPIFFS.begin(false)) {
        Serial.println("SPIFFS mount error");
        spiffs_mounted = false;
    }
}

void FlightChecks::load_zones_binary()
{
    File f = SPIFFS.open("/zones.bin", FILE_READ);
    if (!f) return;

    // Header (16 bytes): magic(u32) version(u16) tile_deg(u8) _pad(u8)
    //                    n_tiles(u16) _pad(u16) data_offset(u32)
    uint8_t hdr[16];
    if (f.read(hdr, 16) != 16) { f.close(); return; }

    uint32_t magic; memcpy(&magic, hdr,    4);
    uint16_t ver;   memcpy(&ver,   hdr+4,  2);
    uint16_t nt;    memcpy(&nt,    hdr+8,  2);
    uint32_t doff;  memcpy(&doff,  hdr+12, 4);

    if (magic != 0x5A4F4E45U || ver != 3) { f.close(); return; }

    tile_deg       = (hdr[6] > 0) ? hdr[6] : 4;
    n_tiles        = nt;
    zones_data_off = doff;

    // Load tile index (8 bytes per entry)
    if (n_tiles > 0) {
        tile_index = (ZoneTile*)malloc((uint32_t)n_tiles * 8U);
        if (!tile_index) { f.close(); return; }
        if (f.read((uint8_t*)tile_index, (uint32_t)n_tiles * 8U) != (uint32_t)n_tiles * 8U) {
            free(tile_index); tile_index = nullptr; f.close(); return;
        }
    }

    // Find country section start by scanning to the end of the last tile
    if (n_tiles == 0) {
        country_offset = zones_data_off;
    } else {
        uint32_t last_off = zones_data_off + tile_index[n_tiles - 1].offset;
        f.seek(last_off);
        uint8_t nr_buf[2];
        if (f.read(nr_buf, 2) != 2) { free(tile_index); tile_index = nullptr; f.close(); return; }
        uint16_t nr; memcpy(&nr, nr_buf, 2);
        for (uint16_t i = 0; i < nr; i++) {
            uint8_t rec5[5];
            if (f.read(rec5, 5) != 5) { free(tile_index); tile_index = nullptr; f.close(); return; }
            if (rec5[4] == 0) {  // circle: skip floor_m(2)+lat(4)+lon(4)+radius(2)
                uint8_t skip[12];
                if (f.read(skip, 12) != 12) { free(tile_index); tile_index = nullptr; f.close(); return; }
            } else {             // polygon: floor_m(2)+n_pts(1)+clat(4)+clon(4), then n_pts*4
                uint8_t ph[11];
                if (f.read(ph, 11) != 11) { free(tile_index); tile_index = nullptr; f.close(); return; }
                uint8_t n_pts = ph[2];
                uint8_t skip4[4];
                for (uint8_t j = 0; j < n_pts; j++) {
                    if (f.read(skip4, 4) != 4) { free(tile_index); tile_index = nullptr; f.close(); return; }
                }
            }
        }
        country_offset = (uint32_t)f.position();
    }

    // Load country section into RAM
    uint32_t file_size = (uint32_t)f.size();
    if (country_offset < file_size) {
        country_data_size = file_size - country_offset;
        country_data = (uint8_t*)malloc(country_data_size);
        if (country_data) {
            f.seek(country_offset);
            if (f.read(country_data, country_data_size) != country_data_size) {
                free(country_data); country_data = nullptr; country_data_size = 0;
            }
        } else {
            country_data_size = 0;
        }
    }

    f.close();
    files_read = true;
}

void FlightChecks::load_unlocked_zones()
{
    size_t len = sizeof(unlocked_zones);
    if (!g.nvs_load_blob("zones_ok", unlocked_zones, &len)) {
        n_unlocked = 0;
        return;
    }
    n_unlocked = uint8_t(len / sizeof(uint32_t));
}

bool FlightChecks::zone_ok(uint32_t zone_id)
{
    if (is_zone_unlocked(zone_id)) return true;
    if (n_unlocked >= 32) return false;
    unlocked_zones[n_unlocked++] = zone_id;
    g.nvs_save_blob("zones_ok", unlocked_zones, n_unlocked * sizeof(uint32_t));
    return true;
}

bool FlightChecks::zone_lock(uint32_t zone_id)
{
    for (uint8_t i = 0; i < n_unlocked; i++) {
        if (unlocked_zones[i] == zone_id) {
            unlocked_zones[i] = unlocked_zones[--n_unlocked];
            g.nvs_save_blob("zones_ok", unlocked_zones, n_unlocked * sizeof(uint32_t));
            return true;
        }
    }
    return false;
}

void FlightChecks::zone_clear()
{
    n_unlocked = 0;
    g.nvs_save_blob("zones_ok", unlocked_zones, 0);
}

bool FlightChecks::is_zone_unlocked(uint32_t zone_id)
{
    for (uint8_t i = 0; i < n_unlocked; i++) {
        if (unlocked_zones[i] == zone_id) return true;
    }
    return false;
}

bool FlightChecks::checkEdge(double x, double y, double x1, double y1, double x2, double y2)
{
    if (y > min(y1, y2) && y <= max(y1, y2) && x <= max(x1, x2)) {
        if (y1 != y2) {
            double xinters = (y - y1) * (x2 - x1) / (y2 - y1) + x1;
            if (x1 == x2 || x <= xinters)
                return true;
        }
    }
    return false;
}

double FlightChecks::degrees_to_radians(double degrees) { return degrees * PI / 180.0; }
double FlightChecks::radians_to_degrees(double radians) { return radians * 180.0 / PI; }

bool FlightChecks::check_circle(double lat, double lon,
                                 double clat, double clon, double radius_m)
{
    double cos_lat = cos(clat * PI / 180.0);
    if (cos_lat < 0.001) cos_lat = 0.001;
    double dy = (lat - clat) * 111320.0;
    double dx = (lon - clon) * 111320.0 * cos_lat;
    return (dy * dy + dx * dx) <= (radius_m * radius_m);
}

bool FlightChecks::check_polygon_deltas(double lat, double lon,
                                         double clat, double clon,
                                         const uint8_t *delta_buf, uint8_t n_pts)
{
    if (n_pts < 3) return false;
    double cos_lat = cos(clat * PI / 180.0);
    if (cos_lat < 0.001) cos_lat = 0.001;
    double py = (lat - clat) * 111320.0;          // meters north from centroid
    double px = (lon - clon) * 111320.0 * cos_lat; // meters east
    int crossings = 0;
    for (uint8_t i = 0; i < n_pts; i++) {
        uint8_t j = (i + 1) % n_pts;
        int16_t dy_i, dx_i, dy_j, dx_j;
        memcpy(&dy_i, delta_buf + i * 4,     2);
        memcpy(&dx_i, delta_buf + i * 4 + 2, 2);
        memcpy(&dy_j, delta_buf + j * 4,     2);
        memcpy(&dx_j, delta_buf + j * 4 + 2, 2);
        double y1 = dy_i * 10.0, x1 = dx_i * 10.0;
        double y2 = dy_j * 10.0, x2 = dx_j * 10.0;
        if ((y1 > py) != (y2 > py)) {
            double xi = x1 + (py - y1) * (x2 - x1) / (y2 - y1);
            if (px < xi) crossings++;
        }
    }
    return (crossings & 1) == 1;
}

bool FlightChecks::is_inside_country(double lat, double lon)
{
    if (!country_data || country_data_size < 2) return false;
    uint16_t n_polys;
    memcpy(&n_polys, country_data, 2);
    uint32_t pos = 2;
    for (uint16_t p = 0; p < n_polys; p++) {
        if (pos + 2 > country_data_size) break;
        uint16_t n_pts;
        memcpy(&n_pts, country_data + pos, 2);
        pos += 2;
        uint32_t pts_bytes = (uint32_t)n_pts * 8U;
        if (pos + pts_bytes > country_data_size) break;
        if (n_pts >= 3) {
            // closed ring: last point == first; iterate n_pts-1 edges
            int crossings = 0;
            for (uint16_t i = 0; i + 1 < n_pts; i++) {
                uint16_t j = i + 1;
                int32_t lat5_i, lon5_i, lat5_j, lon5_j;
                memcpy(&lat5_i, country_data + pos + i * 8,     4);
                memcpy(&lon5_i, country_data + pos + i * 8 + 4, 4);
                memcpy(&lat5_j, country_data + pos + j * 8,     4);
                memcpy(&lon5_j, country_data + pos + j * 8 + 4, 4);
                double y1 = lat5_i * 1e-5, x1 = lon5_i * 1e-5;
                double y2 = lat5_j * 1e-5, x2 = lon5_j * 1e-5;
                if ((y1 > lat) != (y2 > lat)) {
                    double xi = x1 + (lat - y1) * (x2 - x1) / (y2 - y1);
                    if (lon < xi) crossings++;
                }
            }
            if (crossings & 1) return true;
        }
        pos += pts_bytes;
    }
    return false;
}

void FlightChecks::scan_tile(double lat, double lon, float alt_m,
                              String &ret, bool &truncated)
{
    int8_t lt = (int8_t)floor(lat / tile_deg);
    int8_t ln = (int8_t)floor(lon / tile_deg);

    // Binary search tile_index sorted by (lat_tile, lon_tile)
    int lo = 0, hi = (int)n_tiles - 1, idx = -1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        int8_t ml = tile_index[mid].lat_tile, mn = tile_index[mid].lon_tile;
        if (ml == lt && mn == ln) { idx = mid; break; }
        if (ml < lt || (ml == lt && mn < ln)) lo = mid + 1;
        else                                   hi = mid - 1;
    }
    if (idx < 0) return;

    // Load tile into cache when it changes (typically every ~444 km)
    if (lt != cached_lat_tile || ln != cached_lon_tile) {
        uint32_t tile_off = zones_data_off + tile_index[idx].offset;
        uint32_t tile_end = (idx + 1 < (int)n_tiles)
            ? zones_data_off + tile_index[idx + 1].offset
            : country_offset;
        uint32_t tile_bytes = tile_end - tile_off;

        free(tile_cache);
        tile_cache = (uint8_t*)malloc(tile_bytes);
        if (!tile_cache) return;

        File f = SPIFFS.open("/zones.bin", FILE_READ);
        if (!f) { free(tile_cache); tile_cache = nullptr; return; }
        f.seek(tile_off);
        if (f.read(tile_cache, tile_bytes) != tile_bytes) {
            f.close(); free(tile_cache); tile_cache = nullptr; return;
        }
        f.close();
        cached_lat_tile  = lt;
        cached_lon_tile  = ln;
        tile_cache_bytes = tile_bytes;
    }

    if (tile_cache_bytes < 2) return;
    uint16_t n_rec; memcpy(&n_rec, tile_cache, 2);
    uint32_t pos = 2;
    uint32_t reported_cats = 0;  // one tag per category, dedup within tile

    for (uint16_t i = 0; i < n_rec && !truncated; i++) {
        if (pos + 5 > tile_cache_bytes) break;
        uint32_t zone_id; uint8_t shape;
        memcpy(&zone_id, tile_cache + pos, 4);
        shape = tile_cache[pos + 4];
        pos += 5;

        uint8_t cat = (uint8_t)(zone_id >> 27);

        if (shape == 0) {  // circle: floor_m(2)+clat(4)+clon(4)+radius(2)=12
            if (pos + 12 > tile_cache_bytes) break;
            uint16_t floor_m; int32_t clat_i, clon_i; uint16_t radius;
            memcpy(&floor_m, tile_cache + pos,      2);
            memcpy(&clat_i,  tile_cache + pos + 2,  4);
            memcpy(&clon_i,  tile_cache + pos + 6,  4);
            memcpy(&radius,  tile_cache + pos + 10, 2);
            pos += 12;
            if (cat >= 17 || (g.options & CAT_BYPASS_BIT[cat])) continue;
            if (is_zone_unlocked(zone_id))               continue;
            if (floor_m > 0 && alt_m < (float)floor_m)  continue;
            if (reported_cats & (1U << cat))             continue;
            double clat = clat_i * 1e-5, clon = clon_i * 1e-5;
            if (check_circle(lat, lon, clat, clon, (double)radius)) {
                append_tag(ret, CAT_MSG[cat], truncated);
                reported_cats |= (1U << cat);
            }
        } else {  // polygon: floor_m(2)+n_pts(1)+clat(4)+clon(4)=11, then n_pts*4
            if (pos + 11 > tile_cache_bytes) break;
            uint16_t floor_m; uint8_t n_pts; int32_t clat_i, clon_i;
            memcpy(&floor_m, tile_cache + pos,     2);
            n_pts = tile_cache[pos + 2];
            memcpy(&clat_i,  tile_cache + pos + 3, 4);
            memcpy(&clon_i,  tile_cache + pos + 7, 4);
            pos += 11;
            uint32_t delta_bytes = (uint32_t)n_pts * 4U;
            if (pos + delta_bytes > tile_cache_bytes) break;
            const uint8_t *delta_buf = tile_cache + pos;
            pos += delta_bytes;
            if (cat >= 17 || (g.options & CAT_BYPASS_BIT[cat])) continue;
            if (is_zone_unlocked(zone_id))               continue;
            if (floor_m > 0 && alt_m < (float)floor_m)  continue;
            if (reported_cats & (1U << cat))             continue;
            double clat = clat_i * 1e-5, clon = clon_i * 1e-5;
            if (check_polygon_deltas(lat, lon, clat, clon, delta_buf, n_pts)) {
                append_tag(ret, CAT_MSG[cat], truncated);
                reported_cats |= (1U << cat);
            }
        }
    }
}

String FlightChecks::is_flying_allowed()
{
    if (!spiffs_mounted) {
        if (g.options & OPTIONS_BYPASS_SPIFFS) return "";
        return "FS ";
    }
    if (origin.lat == 0 && origin.lon == 0) return "GPS ";

    if (!files_read) {
        load_zones_binary();
        load_unlocked_zones();
        if (!files_read) {
            if (g.options & OPTIONS_BYPASS_SPIFFS) return "";
            return "FS ";
        }
    }

    String ret;
    bool truncated = false;

    const uint32_t t0 = micros();
    scan_tile(origin.lat, origin.lon, origin_alt_m, ret, truncated);
    if (!truncated && !(g.options & OPTIONS_BYPASS_COUNTRY)) {
        if (is_inside_country(origin.lat, origin.lon)) {
            append_tag(ret, "COUNTRY ", truncated);
        }
    }
    last_scan_us = micros() - t0;

    return ret;
}
#endif
