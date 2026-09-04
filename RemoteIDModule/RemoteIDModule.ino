/*
  implement OpenDroneID MAVLink and DroneCAN support
 */
/*
  released under GNU GPL v2 or later
 */

#include "options.h"
#include <Arduino.h>
#include "version.h"
#include <math.h>
#include <time.h>
#include <sys/time.h>
#include <opendroneid.h>
#include "mavlink.h"
#include "DroneCAN.h"
#include "WiFi_TX.h"
#include "BLE_TX.h"
#include <esp_wifi.h>
#include <WiFi.h>
#include "parameters.h"
#include "webinterface.h"
#include "check_firmware.h"
#include <esp_ota_ops.h>
#include "efuse.h"
#include "led.h"
#include <SPI.h>
#include <Wire.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_GFX.h>
#include <math.h>
#if defined(BOARD_AURELIA_RID_S3)
#include "flight_checker.h"
#endif
#include "distance_checker.h"
#include "monocypher.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define SCREEN_ADDRESS 0x3C
Adafruit_SSD1306 display(128, 64, &Wire, -1);

#if AP_DRONECAN_ENABLED
static DroneCAN dronecan;
#endif

#if defined(BOARD_AURELIA_RID_S3) && AP_DRONECAN_ENABLED
FlightChecks flight_checks(dronecan);
#endif

#if AP_MAVLINK_ENABLED
static MAVLinkSerial mavlink1{Serial, MAVLINK_COMM_0};
static MAVLinkSerial mavlink2{Serial1, MAVLINK_COMM_1};
#endif

static WiFi_TX wifi;
static BLE_TX ble;

#define DEBUG_BAUDRATE 57600

// OpenDroneID output data structure
ODID_UAS_Data UAS_data;
String status_reason;
static uint32_t last_location_ms;
static WebInterface webif;

#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

static bool arm_check_ok = false; // goes true for LED arm check status
static bool pfst_check_ok = false;

/*
  setup serial ports
 */
void setup()
{
    // SDA-SCL, I2C
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);

    // disable brownout checking
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    g.init();

    if (g.webserver_enable)
    {
        // need WiFi for web server
        wifi.init();
    }

    // Serial for debug printf
    Serial.begin(g.baudrate);
    led.test();
    led.set_state(Led::LedState::STARTING);
    led.update();
    // Serial1 for MAVLink
    Serial1.begin(g.baudrate, SERIAL_8N1, PIN_UART_RX, PIN_UART_TX);
    display.begin(0x02, SCREEN_ADDRESS); // SSD1306_SWITCHCAPVCC
    display.setTextColor(1);
    uint32_t flt_time_rid = g.find("FLT_TIME")->get_uint32();
    print_i2c_display(flt_time_rid);

    // set all fields to invalid/initial values
    odid_initUasData(&UAS_data);

#if AP_MAVLINK_ENABLED
    mavlink1.init();
    mavlink2.init();
#endif
#if AP_DRONECAN_ENABLED
    dronecan.init();
#endif
#if AP_DRONECAN_ENABLED && defined(BOARD_AURELIA_RID_S3)
flight_checks.init();
#endif
    set_efuses();
    CheckFirmware::check_OTA_running();

#if defined(PIN_CAN_EN)
    // optional CAN enable pin
    pinMode(PIN_CAN_EN, OUTPUT);
    digitalWrite(PIN_CAN_EN, HIGH);
#endif

#if defined(PIN_CAN_nSILENT)
    // disable silent pin
    pinMode(PIN_CAN_nSILENT, OUTPUT);
    digitalWrite(PIN_CAN_nSILENT, HIGH);
#endif

#if defined(PIN_CAN_TERM)
    // optional CAN termination control
    pinMode(PIN_CAN_TERM, OUTPUT);
    digitalWrite(PIN_CAN_TERM, HIGH);
#endif

#if defined(BUZZER_PIN)
    // set BuZZER OUTPUT ACTIVE, just to show it works
    pinMode(GPIO_NUM_39, OUTPUT);
    digitalWrite(GPIO_NUM_39, HIGH);
#endif
    pfst_check_ok = true; // note - this will need to be expanded to better capture PFST test status
    // initially set LED for fail

    esp_log_level_set("*", ESP_LOG_DEBUG);

    esp_ota_mark_app_valid_cancel_rollback();
}

#define IMIN(x, y) ((x) < (y) ? (x) : (y))
#define ODID_COPY_STR(to, from) strncpy(to, (const char *)from, IMIN(sizeof(to), sizeof(from)))

void print_i2c_display(uint32_t flt_time)
{
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(40, 3);
    display.println("FLT TIME");
    String hrs = scs_to_hrs(flt_time);
    String min = scs_to_min(hrs.toInt(), flt_time);
    display.setTextSize(2);
    String txt = hrs + " min"; // hrs
    center_txt_screen(txt, 17);
    txt = min + " s"; // min
    center_txt_screen(txt, 38);
    display.setTextSize(1);
    display.setCursor(28, 57);
    display.println("Time counter");
    display.display();
}

void center_txt_screen(String txt, int ver_pos)
{
    int len = txt.length();
    int begin = ((round(10 - len) / 2) * 12) + 2;
    display.setCursor(begin, ver_pos);
    display.println(txt);
}

String scs_to_hrs(int scs)
{
    // return String(scs / 3600000);
    return String(scs / 60); // test
}
String scs_to_min(int hrs, int scs)
{
    // return String((scs - hrs * 3600) / 60);
    return String(scs - (hrs * 60)); // test
}

#if defined(BOARD_AURELIA_RID_S3)
const char *check_flight_area()
{
    String ret = flight_checks.is_flying_allowed();
    if (ret != "")
    {
        static char return_string[50];
        memset(return_string, 0, sizeof(return_string));
        snprintf(return_string, sizeof(return_string) - 1, "%s", ret.c_str());
        return return_string;
    }
    return nullptr;
}
#endif

/*
  check parsing of UAS_data, this checks ranges of values to ensure we
  will produce a valid pack
  returns nullptr on no error, or a string error
 */
static const char *check_parse(void)
{
    String ret = "";

    {
        ODID_Location_encoded encoded{};
        if (encodeLocationMessage(&encoded, &UAS_data.Location) != ODID_SUCCESS)
        {
            ret += "LOC ";
        }
        else
        {
#if AP_DRONECAN_ENABLED && defined(BOARD_AURELIA_RID_S3)
            flight_checks.update_location(UAS_data.Location.Latitude, UAS_data.Location.Longitude);
#endif
        }
    }
    {
        ODID_System_encoded encoded{};
        if (encodeSystemMessage(&encoded, &UAS_data.System) != ODID_SUCCESS)
        {
            ret += "SYS ";
        }
    }
    {
        ODID_BasicID_encoded encoded{};
        if (UAS_data.BasicIDValid[0] == 1)
        {
            if (encodeBasicIDMessage(&encoded, &UAS_data.BasicID[0]) != ODID_SUCCESS)
            {
                ret += "ID_1 ";
            }
        }
        memset(&encoded, 0, sizeof(encoded));
        if (UAS_data.BasicIDValid[1] == 1)
        {
            if (encodeBasicIDMessage(&encoded, &UAS_data.BasicID[1]) != ODID_SUCCESS)
            {
                ret += "ID_2 ";
            }
        }
    }
    {
        ODID_SelfID_encoded encoded{};
        if (encodeSelfIDMessage(&encoded, &UAS_data.SelfID) != ODID_SUCCESS)
        {
            ret += "SELF_ID ";
        }
    }
    {
        ODID_OperatorID_encoded encoded{};
        if (encodeOperatorIDMessage(&encoded, &UAS_data.OperatorID) != ODID_SUCCESS)
        {
            ret += "OP_ID ";
        }
    }
    if (ret.length() > 0)
    {
        // if all errors would occur in this function, it will fit in
        // 50 chars that is also the max for the arm status message
        static char return_string[50];
        memset(return_string, 0, sizeof(return_string));
        snprintf(return_string, sizeof(return_string) - 1, "bad %s data", ret.c_str());
        return return_string;
    }
    return nullptr;
}

/*
  fill in UAS_data from MAVLink packets
 */
static void set_data(Transport &t)
{
    const auto &operator_id = t.get_operator_id();
    const auto &basic_id = t.get_basic_id();
    const auto &system = t.get_system();
    const auto &self_id = t.get_self_id();
    const auto &location = t.get_location();
    const auto &flt_time = t.get_flt_time();
    const auto &serial_number = t.get_serial_number();

    odid_initUasData(&UAS_data);

    /*
      if we don't have BasicID info from parameters and we have it
      from the DroneCAN or MAVLink transport then copy it to the
      parameters to persist it. This makes it possible to set the
      UAS_ID string via a MAVLink BASIC_ID message and also offers a
      migration path from the old approach of GCS setting these values
      to having them as parameters

      BasicID 2 can be set in parameters, or provided via mavlink We
      don't persist the BasicID2 if provided via mavlink to allow
      users to change BasicID2 on different days
     */
    if (!g.have_basic_id_info() && !(g.options & OPTIONS_DONT_SAVE_BASIC_ID_TO_PARAMETERS))
    {
        if (basic_id.ua_type != 0 &&
            basic_id.id_type != 0 &&
            strnlen((const char *)basic_id.uas_id, 20) > 0)
        {
            g.set_by_name_uint8("UAS_TYPE", basic_id.ua_type);
            g.set_by_name_uint8("UAS_ID_TYPE", basic_id.id_type);
            char uas_id[21]{};
            ODID_COPY_STR(uas_id, basic_id.uas_id);
            g.set_by_name_string("UAS_ID", uas_id);
        }
    }

    // BasicID
    if (g.have_basic_id_info() && !(g.options & OPTIONS_DONT_SAVE_BASIC_ID_TO_PARAMETERS))
    {
        // from parameters
        UAS_data.BasicID[0].UAType = (ODID_uatype_t)g.ua_type;
        UAS_data.BasicID[0].IDType = (ODID_idtype_t)g.id_type;
        ODID_COPY_STR(UAS_data.BasicID[0].UASID, g.uas_id);
        UAS_data.BasicIDValid[0] = 1;

        // BasicID 2
        if (g.have_basic_id_2_info())
        {
            // from parameters
            UAS_data.BasicID[1].UAType = (ODID_uatype_t)g.ua_type_2;
            UAS_data.BasicID[1].IDType = (ODID_idtype_t)g.id_type_2;
            ODID_COPY_STR(UAS_data.BasicID[1].UASID, g.uas_id_2);
            UAS_data.BasicIDValid[1] = 1;
        }
        else if (strcmp((const char *)g.uas_id, (const char *)basic_id.uas_id) != 0)
        {
            /*
              no BasicID 2 in the parameters, if one is provided on MAVLink
              and it is a different uas_id from the basicID1 then use it as BasicID2
            */
            if (basic_id.ua_type != 0 &&
                basic_id.id_type != 0 &&
                strnlen((const char *)basic_id.uas_id, 20) > 0)
            {
                UAS_data.BasicID[1].UAType = (ODID_uatype_t)basic_id.ua_type;
                UAS_data.BasicID[1].IDType = (ODID_idtype_t)basic_id.id_type;
                ODID_COPY_STR(UAS_data.BasicID[1].UASID, basic_id.uas_id);
                UAS_data.BasicIDValid[1] = 1;
            }
        }
    }

    if (g.options & OPTIONS_DONT_SAVE_BASIC_ID_TO_PARAMETERS)
    {
        if (basic_id.ua_type != 0 &&
            basic_id.id_type != 0 &&
            strnlen((const char *)basic_id.uas_id, 20) > 0)
        {
            if (strcmp((const char *)UAS_data.BasicID[0].UASID, (const char *)basic_id.uas_id) != 0 && strnlen((const char *)basic_id.uas_id, 20) > 0)
            {
                UAS_data.BasicID[1].UAType = (ODID_uatype_t)basic_id.ua_type;
                UAS_data.BasicID[1].IDType = (ODID_idtype_t)basic_id.id_type;
                ODID_COPY_STR(UAS_data.BasicID[1].UASID, basic_id.uas_id);
                UAS_data.BasicIDValid[1] = 1;
            }
            else
            {
                UAS_data.BasicID[0].UAType = (ODID_uatype_t)basic_id.ua_type;
                UAS_data.BasicID[0].IDType = (ODID_idtype_t)basic_id.id_type;
                ODID_COPY_STR(UAS_data.BasicID[0].UASID, basic_id.uas_id);
                UAS_data.BasicIDValid[0] = 1;
            }
        }
    }

    // OperatorID
    if (strlen(operator_id.operator_id) > 0)
    {
        UAS_data.OperatorID.OperatorIdType = (ODID_operatorIdType_t)operator_id.operator_id_type;
        ODID_COPY_STR(UAS_data.OperatorID.OperatorId, operator_id.operator_id);
        UAS_data.OperatorIDValid = 1;
    }

    // SelfID
    if (strlen(self_id.description) > 0)
    {
        UAS_data.SelfID.DescType = (ODID_desctype_t)self_id.description_type;
        ODID_COPY_STR(UAS_data.SelfID.Desc, self_id.description);
        UAS_data.SelfIDValid = 1;
    }

    // System
    if (system.timestamp != 0)
    {
        UAS_data.System.OperatorLocationType = (ODID_operator_location_type_t)system.operator_location_type;
        UAS_data.System.ClassificationType = (ODID_classification_type_t)system.classification_type;
        UAS_data.System.OperatorLatitude = system.operator_latitude * 1.0e-7;
        UAS_data.System.OperatorLongitude = system.operator_longitude * 1.0e-7;
        UAS_data.System.AreaCount = system.area_count;
        UAS_data.System.AreaRadius = system.area_radius;
        UAS_data.System.AreaCeiling = system.area_ceiling;
        UAS_data.System.AreaFloor = system.area_floor;
        UAS_data.System.CategoryEU = (ODID_category_EU_t)system.category_eu;
        UAS_data.System.ClassEU = (ODID_class_EU_t)system.class_eu;
        UAS_data.System.OperatorAltitudeGeo = system.operator_altitude_geo;
        UAS_data.System.Timestamp = system.timestamp;
        UAS_data.SystemValid = 1;
    }

    // Location
    if (location.timestamp != 0)
    {
        UAS_data.Location.Status = (ODID_status_t)location.status;
        UAS_data.Location.Direction = location.direction * 0.01;
        UAS_data.Location.SpeedHorizontal = location.speed_horizontal * 0.01;
        UAS_data.Location.SpeedVertical = location.speed_vertical * 0.01;
        UAS_data.Location.Latitude = location.latitude * 1.0e-7;
        UAS_data.Location.Longitude = location.longitude * 1.0e-7;
        UAS_data.Location.AltitudeBaro = location.altitude_barometric;
        UAS_data.Location.AltitudeGeo = location.altitude_geodetic;
        UAS_data.Location.HeightType = (ODID_Height_reference_t)location.height_reference;
        UAS_data.Location.Height = location.height;
        UAS_data.Location.HorizAccuracy = (ODID_Horizontal_accuracy_t)location.horizontal_accuracy;
        UAS_data.Location.VertAccuracy = (ODID_Vertical_accuracy_t)location.vertical_accuracy;
        UAS_data.Location.BaroAccuracy = (ODID_Vertical_accuracy_t)location.barometer_accuracy;
        UAS_data.Location.SpeedAccuracy = (ODID_Speed_accuracy_t)location.speed_accuracy;
        UAS_data.Location.TSAccuracy = (ODID_Timestamp_accuracy_t)location.timestamp_accuracy;
        UAS_data.Location.TimeStamp = location.timestamp;
        UAS_data.LocationValid = 1;
    }

    uint32_t flt_time_aux = g.find("FLT_TIME_AUX")->get_uint32();
    if (flt_time.flt_time > 0 && flt_time_aux != flt_time.flt_time)
    {
        uint32_t flt_time_rid = g.find("FLT_TIME")->get_uint32();
        uint32_t new_time = flt_time.flt_time > flt_time_rid ? flt_time.flt_time : (abs((int32_t)(flt_time.flt_time - flt_time_aux)) + flt_time_rid);
        bool flt_time_flag = flt_time.flt_time >= flt_time_aux;
        g.set_by_name_uint32("FLT_TIME_AUX", flt_time.flt_time);

        if (flt_time_flag)
        {
            print_i2c_display(new_time);
            g.set_by_name_uint32("FLT_TIME", new_time);
        }
    }
    const char *reason = check_parse();
#if defined(BOARD_AURELIA_RID_S3)
    const char *flt_check = check_flight_area();
    const char *res = flt_check==nullptr?reason:flt_check;
#else
    const char *res = reason;
#endif
    t.status_check(res);
    t.set_parse_fail(res);

    arm_check_ok = (res == nullptr);

#if AP_DRONECAN_ENABLED && defined(BOARD_AURELIA_RID_S3)
    led.set_state(pfst_check_ok && arm_check_ok ? Led::LedState::ARM_OK : flight_checks.get_files_read() ? Led::LedState::ARM_FAIL                                                                                                      : Led::LedState::STARTING);
#else
    led.set_state(pfst_check_ok && arm_check_ok ? Led::LedState::ARM_OK : Led::LedState::ARM_FAIL);
#endif

    uint32_t now_ms = millis();
    uint32_t location_age_ms = now_ms - t.get_last_location_ms();
    uint32_t last_location_age_ms = now_ms - last_location_ms;
    if (location_age_ms < last_location_age_ms)
    {
        last_location_ms = t.get_last_location_ms();
    }
}

static uint8_t loop_counter = 0;

void loop()
{
#if AP_MAVLINK_ENABLED
    mavlink1.update();
    mavlink2.update();
#endif
#if AP_DRONECAN_ENABLED
    dronecan.update();
#endif

    const uint32_t now_ms = millis();

    // the transports have common static data, so we can just use the
    // first for status
#if AP_MAVLINK_ENABLED
    auto &transport = mavlink1;
#elif AP_DRONECAN_ENABLED
    auto &transport = dronecan;
#else
#error "Must enable DroneCAN or MAVLink"
#endif

    bool have_location = false;
    const uint32_t last_location_ms = transport.get_last_location_ms();
    const uint32_t last_system_ms = transport.get_last_system_ms();

    led.update();

    status_reason = "";

    if (last_location_ms == 0 ||
        now_ms - last_location_ms > 5000)
    {
        UAS_data.Location.Status = ODID_STATUS_REMOTE_ID_SYSTEM_FAILURE;
    }

    if (last_system_ms == 0 ||
        now_ms - last_system_ms > 5000)
    {
        UAS_data.Location.Status = ODID_STATUS_REMOTE_ID_SYSTEM_FAILURE;
    }

    if (transport.get_parse_fail() != nullptr)
    {
        UAS_data.Location.Status = ODID_STATUS_REMOTE_ID_SYSTEM_FAILURE;
        status_reason = String(transport.get_parse_fail());
    }

    // web update has to happen after we update Status above
    if (g.webserver_enable)
    {
        webif.update();
    }

    if (g.bcast_powerup)
    {
        // if we are broadcasting on powerup we always mark location valid
        // so the location with default data is sent
        if (!UAS_data.LocationValid)
        {
            UAS_data.Location.Status = ODID_STATUS_REMOTE_ID_SYSTEM_FAILURE;
            UAS_data.LocationValid = 1;
        }
    }
    else
    {
        // only broadcast if we have received a location at least once
        if (last_location_ms == 0)
        {
            delay(1);
            return;
        }
    }

    set_data(transport);

    static uint32_t last_update_wifi_nan_ms;
    if (g.wifi_nan_rate > 0 &&
        now_ms - last_update_wifi_nan_ms > 1000 / g.wifi_nan_rate)
    {
        last_update_wifi_nan_ms = now_ms;
        wifi.transmit_nan(UAS_data);
    }

    static uint32_t last_update_wifi_beacon_ms;
    if (g.wifi_beacon_rate > 0 &&
        now_ms - last_update_wifi_beacon_ms > 1000 / g.wifi_beacon_rate)
    {
        last_update_wifi_beacon_ms = now_ms;
        wifi.transmit_beacon(UAS_data);
    }

    static uint32_t last_update_bt5_ms;
    if (g.bt5_rate > 0 &&
        now_ms - last_update_bt5_ms > 1000 / g.bt5_rate)
    {
        last_update_bt5_ms = now_ms;
        ble.transmit_longrange(UAS_data);
    }

    static uint32_t last_update_bt4_ms;
    int bt4_states = UAS_data.BasicIDValid[1] ? 7 : 6;
    if (g.bt4_rate > 0 &&
        now_ms - last_update_bt4_ms > (1000.0f / bt4_states) / g.bt4_rate)
    {
        last_update_bt4_ms = now_ms;
        ble.transmit_legacy(UAS_data);
    }
    // sleep for a bit for power saving
    delay(1);
}
