# ESP32 Bluetooth Proxy Setup

This directory contains the ESPHome configuration for a Bluetooth Proxy that enables bleak-esphome to connect to the Bosch eBike from Linux, bypassing the BlueZ SMP key distribution issue.

## Files

- `bosch-ble-proxy.yaml` -- ESPHome configuration
- `secrets.yaml.example` -- Template for Wi-Fi credentials
- `.gitignore` -- Prevents secrets from being committed

## Quick Start

### 1. Install ESPHome

```bash
pip install esphome
```

### 2. Configure Wi-Fi

```bash
cd esphome
cp secrets.yaml.example secrets.yaml
# Edit secrets.yaml with your Wi-Fi credentials
```

### 3. Flash ESP32

Connect ESP32 via USB, then:

```bash
esphome run bosch-ble-proxy.yaml
```

Or compile and upload separately:

```bash
esphome compile bosch-ble-proxy.yaml
esphome upload bosch-ble-proxy.yaml --device /dev/ttyUSB0
```

### 4. Note the IP Address

After flashing, the ESP32 will connect to Wi-Fi. Check your router's DHCP leases or use a network scanner to find the ESP32's IP address.

Alternatively, check the serial logs:

```bash
esphome logs bosch-ble-proxy.yaml
```

Look for a line like:
```
[00:00:05][C][wifi:123]:   IP Address: 192.168.1.100
```

## Using with bleak-esphome

Once the ESP32 is running, use it with bleak-esphome:

```python
from bleak_esphome import APIConnectionManager, ESPHomeClient
from bleak_esphome.backend.device import ESPHomeBluetoothDevice

# Connect to ESP32
esphome_ip = "192.168.1.100"  # Replace with actual IP
config = ESPHomeDeviceConfig(
    address=esphome_ip,
    port=6053,
    password=None,
)
manager = APIConnectionManager(config)
await manager.connect()

# Scan for Bosch bike
scanner = manager.scanner
# ... scan for devices ...

# Connect to bike
bike_address = "XX:XX:XX:XX:XX:XX"  # Replace with bike's MAC
client = ESPHomeClient(
    address=bike_address,
    scanner=scanner,
    device=ESPHomeBluetoothDevice(...),
)
await client.connect()

# Now use client like a normal BleakClient
services = await client.get_services()
# ... read/write characteristics ...
```

## How It Works

1. **ESP32 handles BLE** -- The ESP32's BLE controller performs all BLE operations
2. **ESP32 handles SMP** -- The ESP32's BLE stack handles pairing with phone-like parameters (IRK distribution)
3. **Host proxies commands** -- Python code sends BLE commands to ESP32 over Wi-Fi via ESPHome API (port 6053)
4. **No BlueZ involvement** -- The Linux host's BlueZ stack is bypassed entirely

## Troubleshooting

### ESP32 won't connect to Wi-Fi

- Check `secrets.yaml` has correct credentials
- ESP32 will create a fallback hotspot "Bosch BLE Proxy" if Wi-Fi fails
- Connect to the hotspot and reflash with correct credentials

### bleak-esphome can't connect to ESP32

- Verify ESP32 is on the network and get its IP address
- Check port 6053 is accessible (not blocked by firewall)
- Check ESP32 logs via `esphome logs`

### BLE connection to bike fails

- Ensure ESP32 is within BLE range of the bike (<10m)
- Put bike in pairing mode (check pairing advertisement)
- Check ESP32 logs for BLE errors

### SMP pairing still fails

- Capture BLE traffic with a sniffer to verify ESP32's SMP parameters
- ESP32 should distribute IRK (not CSRK) like the phone does
- If ESP32 also distributes CSRK, the ESP32 BLE stack may need patching

## Hardware Recommendations

Any ESP32 board will work. Recommended options:

- **ESP32 DevKit V1** -- Cheap, widely available, works well
- **ESP32-S3** -- Newer, better BLE performance
- **ESP32-C3** -- RISC-V based, lower power

Avoid:
- ESP8266 -- No BLE support
- Boards with poor antenna design -- Check reviews for BLE range

## Next Steps

After validating the ESP32 proxy works:

1. Test discovery of Bosch bike in pairing mode
2. Test BLE connection to bike
3. Test SMP pairing (verify IRK distribution with sniffer)
4. Integrate into bosch_ble codebase (add `--backend esphome` flag)
5. Test MCSP handshake and MessageBus communication

See `findings/2026-07-23T12-00-00-bleak-esphome-implementation-plan.md` for the full implementation plan.
