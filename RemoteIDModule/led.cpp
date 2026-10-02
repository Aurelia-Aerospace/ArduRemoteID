#include <Arduino.h>
#include "led.h"
#include "board_config.h"
#include "parameters.h"

Led led;
int delay_time_ms = 450;

void Led::init(void)
{
    if (done_init) {
        return;
    }
    done_init = true;
#ifdef PIN_STATUS_LED
    pinMode(PIN_STATUS_LED, OUTPUT);
#endif
#ifdef WS2812_LED_PIN
    pinMode(WS2812_LED_PIN, OUTPUT);
    ledStrip.begin();
#endif
#ifdef AIRPORT_LED
    pinMode(AIRPORT_LED, OUTPUT);
#endif
#ifdef COUNTRY_LED
    pinMode(COUNTRY_LED, OUTPUT);
#endif
#ifdef PRISON_LED
    pinMode(PRISON_LED, OUTPUT);
#endif
#ifdef EXTRA_LED
    pinMode(EXTRA_LED, OUTPUT);
#endif
}

void Led::test(void){

    init();

    for (int i = 0; i < static_cast<int>(LedState::COUNT) - 1; i++) {
        set_state(static_cast<LedState>(i));
        update();
        delay(delay_time_ms);
    }

#ifdef AIRPORT_LED
    digitalWrite(AIRPORT_LED, HIGH);
    delay(delay_time_ms);
    digitalWrite(AIRPORT_LED, LOW);
#endif
#ifdef COUNTRY_LED
    digitalWrite(COUNTRY_LED, HIGH);
    delay(delay_time_ms);
    digitalWrite(COUNTRY_LED, LOW);
        
#endif
#ifdef PRISON_LED
    digitalWrite(PRISON_LED, HIGH);
    delay(delay_time_ms);
    digitalWrite(PRISON_LED, LOW);
#endif
#ifdef EXTRA_LED
    digitalWrite(EXTRA_LED, HIGH);
    delay(delay_time_ms);
    digitalWrite(EXTRA_LED, LOW);
#endif
}

void Led::update(void)
{
    init();

    const uint32_t now_ms = millis();

#ifdef PIN_STATUS_LED
    switch (state) {
    case LedState::ARM_OK: {
        digitalWrite(PIN_STATUS_LED, STATUS_LED_OK);
        last_led_trig_ms = now_ms;
        break;
    }

    default:
        if (now_ms - last_led_trig_ms > 100) {
            digitalWrite(PIN_STATUS_LED, !digitalRead(PIN_STATUS_LED));
            last_led_trig_ms = now_ms;
        }
        break;
    }
#endif

    if (now_ms - last_extra_led_trig_ms > 100) {
#ifdef AIRPORT_LED
        //Check parameter
        // AIRPORT_LED: any airport / FAA / EU zone bypass active
        digitalWrite(AIRPORT_LED, (g.options & OPTIONS_BYPASS_ZONES_MASK) ? HIGH : LOW);
#endif
#ifdef COUNTRY_LED
        // COUNTRY_LED: country bypass active
        digitalWrite(COUNTRY_LED, (g.options & OPTIONS_BYPASS_COUNTRY) ? HIGH : LOW);
#endif
#ifdef PRISON_LED
        // PRISON_LED: prison or stadium bypass active
        digitalWrite(PRISON_LED, (g.options & OPTIONS_BYPASS_ENCLOSURES_MASK) ? HIGH : LOW);
#endif
#ifdef EXTRA_LED
        // EXTRA_LED: RID checks bypass active
        digitalWrite(EXTRA_LED, (g.options & OPTIONS_BYPASS_RID_CHECKS) ? HIGH : LOW);
#endif
        last_extra_led_trig_ms=now_ms;
    }


#ifdef WS2812_LED_PIN
    ledStrip.clear();

    switch (state) {
    case LedState::ARM_OK:
        ledStrip.setPixelColor(0, ledStrip.Color(0, 255, 0));
        ledStrip.setPixelColor(0, ledStrip.Color(1, 255, 0)); //for db210pro, set the second LED to have the same output (for now)
        break;
    case LedState::STARTING:
        ledStrip.setPixelColor(0, ledStrip.Color(0, 0, 255));
        break;
    case LedState::OFF:
        ledStrip.setPixelColor(0, ledStrip.Color(0, 0, 0));
        break;
    case LedState::UPDATE_SUCCESS:
        ledStrip.setPixelColor(0, ledStrip.Color(255, 0, 255));
        break;
    case LedState::UPDATE_FAIL:
        ledStrip.setPixelColor(0, ledStrip.Color(255, 255, 0));
        break;
    case LedState::OTA_IN_PROGRESS:
        ledStrip.setPixelColor(0, ledStrip.Color(255, 80, 0));
        ledStrip.setPixelColor(1, ledStrip.Color(255, 80, 0));
        break;
    default:
        ledStrip.setPixelColor(0, ledStrip.Color(255, 0, 0));
        ledStrip.setPixelColor(1, ledStrip.Color(255, 0, 0)); //for db210pro, set the second LED to have the same output (for now)
        break;
    }
    if (now_ms - last_led_strip_ms >= 200) {
        last_led_strip_ms = now_ms;
        ledStrip.show();
    }
#endif
}

