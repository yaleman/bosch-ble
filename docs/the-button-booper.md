# The button booper

To remotely control the physical device I've got a remote ESPHome device at `bike-button-booper.local`.

## ESPHome config

```yaml
# Board: Generic ESP32 Board (Generic)
# Definition: definitions/boards/generic-esp32/manifest.yaml

esphome:
  name: bike-button-booper
  friendly_name: Bike Button Booper

esp32:
  variant: esp32
  framework:
    type: esp-idf

logger:

api:
  encryption:
    key: <env var BOOPER_API_KEY>

ota:
  - platform: esphome

captive_portal:


light:
  - platform: status_led
    name: "Onboard Led"
    restore_mode: ALWAYS_OFF
    pin:
      number: GPIO02
      inverted: False

switch:
  - platform: gpio
    pin: GPIO19
    name: "Solenoid Relay"
    id: ESP32_relay

binary_sensor:
  - platform: gpio
    pin:
      number: GPIO09
      mode: INPUT_PULLUP
    name: Button
    filters:
      - invert
      - delayed_on_off: 50ms
    on_press:
      then:
        - switch.turn_on: ESP32_relay
```
