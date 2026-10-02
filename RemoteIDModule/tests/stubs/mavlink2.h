#pragma once
#include <cstdint>

// Minimal mavlink type stubs for flight_checker tests

typedef uint8_t  mavlink_channel_t;
typedef struct { uint8_t sysid; uint8_t compid; } mavlink_system_t;
extern mavlink_system_t mavlink_system;

typedef struct { double latitude; double longitude; float altitude_geodetic; uint8_t speed_accuracy; uint8_t vertical_accuracy; uint8_t horizontal_accuracy; uint8_t baro_accuracy; float speed_horizontal; float speed_vertical; float direction; float height; uint8_t height_ref; uint8_t status; uint16_t timestamp; uint8_t location_source; } mavlink_open_drone_id_location_t;
typedef struct { char uas_id[21]; uint8_t id_or_mac[20]; uint8_t id_type; uint8_t ua_type; uint8_t target_system; uint8_t target_component; } mavlink_open_drone_id_basic_id_t;
typedef struct { float timestamp; uint8_t data[17]; uint8_t last_page_index; uint8_t length; uint8_t page_index; uint8_t authentication_type; uint8_t target_system; uint8_t target_component; } mavlink_open_drone_id_authentication_t;
typedef struct { char description[24]; uint8_t description_type; uint8_t target_system; uint8_t target_component; } mavlink_open_drone_id_self_id_t;
typedef struct { double operator_latitude; double operator_longitude; float area_ceiling; float area_floor; float operator_altitude_geo; uint32_t timestamp; uint16_t area_count; uint16_t area_radius; uint8_t operator_location_type; uint8_t classification_type; uint8_t category_eu; uint8_t class_eu; uint8_t operator_id_type; char operator_id[21]; uint8_t target_system; uint8_t target_component; } mavlink_open_drone_id_system_t;
typedef struct { char operator_id[21]; uint8_t operator_id_type; uint8_t target_system; uint8_t target_component; } mavlink_open_drone_id_operator_id_t;

// ARM STATUS values used by flight_checker/transport
enum MAV_ODID_ARM_STATUS {
    MAV_ODID_ARM_STATUS_GOOD_TO_ARM         = 0,
    MAV_ODID_ARM_STATUS_PRE_ARM_FAIL_GENERIC = 1,
};
