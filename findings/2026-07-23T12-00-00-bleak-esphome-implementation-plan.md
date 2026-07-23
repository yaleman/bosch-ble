# Implementation Plan: ESP32 Bluetooth Proxy via bleak-esphome

**Date:** 2026-07-23  
**Status:** Planning  
**Hypothesis:** Using an ESP32 Bluetooth Proxy via `bleak-esphome` will bypass the Linux BlueZ SMP key distribution mismatch and enable reliable pairing with the Bosch eBike.

## Background

### Current Blocker

The Linux BlueZ stack distributes **CSRK** (Connection Signature Resolving Key) during SMP pairing, while the Android phone distributes **IRK** (Identity Resolving Key). The Bosch bike rejects the CSRK distribution, causing `AuthenticationCanceled` errors.

From our sniffer captures:

| Field | Phone | Linux BlueZ |
|---|---|---|
| Initiator keys | `0x0b` = LTK + **IRK** + LinkKey | `0x0d` = LTK + **CSRK** + LinkKey |
| Responder keys | `0x0b` = LTK + **IRK** + LinkKey | `0x0f` = LTK + IRK + **CSRK** + LinkKey |

This is a kernel-level behavior in BlueZ's SMP handler -- not something our Python code controls.

### Why ESP32 Proxy Should Work

The ESP32 Bluetooth Proxy handles BLE operations on the ESP32 itself:

1. **ESP32 BLE stack** -- The ESP32 uses Espressif's BLE stack (not BlueZ)
2. **Phone-like SMP** -- ESP32's BLE stack is closer to a phone's stack than Linux BlueZ
3. **Correct key distribution** -- ESP32 should distribute IRK like the phone does
4. **No BlueZ involvement** -- The Linux host just proxies commands over Wi-Fi

The ESP32 acts as a remote BLE adapter, similar to how a phone's integrated BLE controller works.

### What bleak-esphome Provides

`bleak-esphome` is a Bleak backend that proxies BLE through an ESP32 running ESPHome with the Bluetooth Proxy component:

- **ESPHomeScanner** -- Remote scanner that feeds advertisements from ESP32 to host
- **ESPHomeClient** -- BleakClient-compatible backend for GATT operations
- **APIConnectionManager** -- Manages ESPHome API connection over TCP (port 6053)
- **Feature negotiation** -- Detects proxy capabilities (pairing, connection params, etc.)

**Key features for our use case:**
- `PAIRING` flag -- Enables `BleakClient.pair()` and `unpair()`
- `CONNECTION_PARAMS_SETTING` flag -- Enables `set_connection_params()`
- `ACTIVE_CONNECTIONS` flag -- Enables BLE connections (not just advertisement forwarding)

**Source:** https://bleak-esphome.readthedocs.io/en/latest/architecture.html

## Implementation Plan

### Phase 1: ESP32 Setup and Validation

**Goal:** Get a working ESP32 Bluetooth Proxy and validate basic BLE operations.

#### Steps

1. **Flash ESP32 with Bluetooth Proxy firmware**
   - Use ESPHome's pre-built Bluetooth Proxy firmware
   - Or build custom firmware with `bluetooth_proxy:` component
   - Ensure `active: true` for active connections (not just passive scanning)

2. **Connect ESP32 to Wi-Fi**
   - Configure Wi-Fi credentials in ESPHome YAML
   - Verify ESP32 appears on network
   - Note ESP32's IP address for API connection

3. **Validate basic BLE operations from host**
   - Install `bleak-esphome` on the remote Linux host
   - Write a test script that:
     - Connects to ESP32 via `APIConnectionManager`
     - Scans for BLE devices
     - Connects to a known BLE peripheral (e.g., a phone or HRM)
     - Reads a characteristic
   - Verify the proxy works for basic operations

4. **Validate pairing capability**
   - Check if ESP32 proxy reports `PAIRING` feature flag
   - If yes: test pairing with a simple BLE peripheral
   - If no: may need to update ESPHome firmware or enable pairing in config

**Success criteria:**
- ESP32 proxy can scan, connect, read/write characteristics
- ESP32 proxy can pair with a BLE peripheral (if PAIRING flag is present)

### Phase 2: Bosch Bike Discovery via ESP32 Proxy

**Goal:** Verify the ESP32 can detect the Bosch bike in pairing mode.

#### Steps

1. **Put bike in pairing mode**
   - Follow standard Bosch pairing procedure
   - Verify bike is visible to a phone (known-good baseline)

2. **Scan for bike via ESP32 proxy**
   - Use `bleak-esphome` scanner to scan for BLE devices
   - Look for:
     - Service UUID: `0000FE02-0000-1000-8000-00805F9B34FB` (BES3)
     - Manufacturer data: company ID `0x02A6` (Bosch)
     - Pairable flag: byte[3] == `0x01`
   - Log full advertisement data for analysis

3. **Compare with phone capture**
   - Compare ESP32's advertisement data with phone's known-good capture
   - Verify all expected fields are present
   - Check if ESP32 sees scan-response data (active scan)

**Success criteria:**
- ESP32 detects bike in pairing mode
- Advertisement data matches phone's capture

### Phase 3: Bosch Bike Connection via ESP32 Proxy

**Goal:** Connect to the Bosch bike via ESP32 proxy and perform GATT operations.

#### Steps

1. **Connect to bike via ESP32 proxy**
   - Use `ESPHomeClient` to connect to bike's MAC address
   - Monitor connection state
   - Log any connection errors

2. **Discover services**
   - Call `client.get_services()`
   - Verify MCSP service is present: `00000010-EAA2-11E9-81B4-2A2AE2DBCCE4`
   - Verify MCSP characteristics:
     - Receive: `00000011-EAA2-11E9-81B4-2A2AE2DBCCE4`
     - Send: `00000012-EAA2-11E9-81B4-2A2AE2DBCCE4`

3. **Enable notifications (trigger bonding)**
   - Write CCCD `0x2902` on receive characteristic
   - This should trigger implicit bonding (like the Android app)
   - Monitor for bonding/pairing flow

4. **Capture SMP traffic**
   - If possible, use BLE sniffer to capture SMP traffic during ESP32-bike pairing
   - Compare SMP parameters with phone's known-good capture
   - Verify ESP32 distributes IRK (not CSRK)

**Success criteria:**
- ESP32 connects to bike
- Services discovered
- Bonding/pairing succeeds (or at least progresses past SMP)

### Phase 4: MCSP Handshake via ESP32 Proxy

**Goal:** Complete the MCSP handshake and establish a live session.

#### Steps

1. **Subscribe to MCSP receive characteristic**
   - Enable notifications on `00000011-EAA2-11E9-81B4-2A2AE2DBCCE4`
   - Wait for bike's startup messages

2. **Send MCSP handshake response**
   - Use existing `live.build_handshake_response()` logic
   - Send version, max packet size, disable flow control commands

3. **Wait for bike handshake**
   - Accumulate command frames from bike
   - Detect handshake completion using `live.is_bike_handshake()`
   - Log handshake commands

4. **Start MessageBus communication**
   - Subscribe to MessageBus data points
   - Read initial values (battery, drive unit info, etc.)
   - Verify data is valid

**Success criteria:**
- MCSP handshake completes
- MessageBus data is readable
- Live session is stable

### Phase 5: Codebase Integration

**Goal:** Integrate ESP32 proxy support into the existing codebase.

#### Architecture Changes

The current codebase has a clear separation:

```
bluez.py      -- BlueZ orchestration (scan, connect, pair)
dump_gatt.py  -- Bleak connection + security staging
live.py       -- MCSP session handling
```

We need to add an ESP32 proxy path alongside the BlueZ path:

```
bluez.py          -- BlueZ orchestration (existing)
esphome_proxy.py  -- ESP32 proxy orchestration (NEW)
dump_gatt.py      -- Bleak connection + security staging (refactor for backend selection)
live.py           -- MCSP session handling (unchanged)
```

#### New Module: `esphome_proxy.py`

```python
# bosch_ble/esphome_proxy.py

from bleak_esphome import APIConnectionManager, ESPHomeClient, ESPHomeScanner
from bleak_esphome.backend.device import ESPHomeBluetoothDevice

async def connect_via_esphome(
    esphome_ip: str,
    bike_address: str,
) -> ESPHomeClient:
    """Connect to bike via ESP32 Bluetooth Proxy."""
    
    # 1. Connect to ESP32
    config = ESPHomeDeviceConfig(
        address=esphome_ip,
        port=6053,
        password=None,  # or from config
    )
    manager = APIConnectionManager(config)
    await manager.connect()
    
    # 2. Get scanner and client
    scanner = manager.scanner
    client = ESPHomeClient(
        address=bike_address,
        scanner=scanner,
        device=ESPHomeBluetoothDevice(...),
    )
    
    # 3. Connect to bike
    await client.connect()
    
    return client
```

#### Refactor: `dump_gatt.py`

Add backend selection:

```python
# bosch_ble/dump_gatt.py

async def prepare_connection(
    address: str,
    backend: Literal["bluez", "esphome"] = "bluez",
    esphome_ip: str | None = None,
) -> BleakClient:
    """Prepare connection to bike."""
    if backend == "esphome":
        if esphome_ip is None:
            raise ValueError("esphome_ip required for esphome backend")
        return await esphome_proxy.connect_via_esphome(esphome_ip, address)
    else:
        # existing BlueZ path
        state = await resolve_device(address)
        connected_state = await bluez.connect_device(address)
        target = client_target_for_state(connected_state)
        return BleakClient(target, timeout=20.0)
```

#### Update CLI Entry Points

Add `--backend` flag to existing commands:

```python
# bosch_ble/dump_gatt.py

def cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("address")
    parser.add_argument("--backend", choices=["bluez", "esphome"], default="bluez")
    parser.add_argument("--esphome-ip", help="ESP32 proxy IP address")
    args = parser.parse_args()
    
    asyncio.run(main(args.address, args.backend, args.esphome_ip))
```

#### Configuration

Add ESP32 proxy configuration to environment or config file:

```bash
# .env
BOSCH_BLE_BACKEND=esphome
BOSCH_BLE_ESPHOME_IP=192.168.1.100
```

Or in `pyproject.toml`:

```toml
[tool.bosch-ble]
backend = "esphome"
esphome_ip = "192.168.1.100"
```

### Phase 6: Testing and Validation

**Goal:** Validate the ESP32 proxy path works end-to-end.

#### Test Cases

1. **Discovery test**
   - Scan for bike via ESP32 proxy
   - Verify pairing advertisement is detected

2. **Connection test**
   - Connect to bike via ESP32 proxy
   - Verify services are discovered

3. **Pairing test**
   - Trigger bonding via CCCD write
   - Verify pairing succeeds
   - Capture SMP traffic and verify IRK distribution

4. **MCSP handshake test**
   - Complete MCSP handshake
   - Verify handshake commands match expected values

5. **Live session test**
   - Start live session
   - Read MessageBus data points
   - Verify data is valid

6. **Stability test**
   - Run live session for 10+ minutes
   - Verify no disconnects or errors

#### Validation Commands

```bash
# Scan for bike
uv run bosch-ble-scan --backend esphome --esphome-ip 192.168.1.100

# Dump GATT
uv run bosch-ble-dump-gatt <BLE_ADDRESS> --backend esphome --esphome-ip 192.168.1.100

# Live session
uv run bosch-ble-handshake <BLE_ADDRESS> --backend esphome --esphome-ip 192.168.1.100
```

## Risks and Unknowns

### Risk 1: ESP32 SMP Parameters

**Unknown:** Will the ESP32 distribute IRK like the phone, or will it also distribute CSRK?

**Mitigation:** Capture SMP traffic during ESP32-bike pairing. If ESP32 also distributes CSRK, we may need to:
- Patch ESP32 BLE stack (unlikely to be feasible)
- Use a different BLE adapter (e.g., Nordic nRF52)
- Accept that this approach won't work

**Probability:** Low -- ESP32's BLE stack is closer to a phone's stack than Linux BlueZ.

### Risk 2: ESP32 Connection Parameters

**Unknown:** Will the ESP32 use phone-like connection parameters (30ms/720ms) by default?

**Mitigation:** If ESP32 uses different parameters, we can use `set_connection_params()` if the proxy supports `CONNECTION_PARAMS_SETTING` flag.

**Probability:** Low -- ESP32's default parameters are likely reasonable.

### Risk 3: ESP32 MTU Negotiation

**Unknown:** Will the ESP32 negotiate the same MTU as the phone (up to 512 bytes)?

**Mitigation:** If MTU is smaller, we may need to adjust MCSP packet sizes. The existing code already handles MTU negotiation.

**Probability:** Low -- ESP32 supports MTU negotiation.

### Risk 4: ESP32 Proxy Latency

**Unknown:** Will the Wi-Fi proxy add significant latency that breaks the MCSP handshake timing?

**Mitigation:** The MCSP handshake is not time-critical (seconds, not milliseconds). Latency should not be an issue.

**Probability:** Very low.

### Risk 5: ESP32 Proxy Reliability

**Unknown:** Will the ESP32 proxy be reliable enough for long-running sessions?

**Mitigation:** ESPHome Bluetooth Proxy is widely used in Home Assistant and is generally stable. If issues arise, we can add reconnection logic.

**Probability:** Low.

## Dependencies

### Hardware

- ESP32 development board (e.g., ESP32-DevKitC, ESP32-WROOM-32)
- USB cable for flashing
- Power supply (USB or battery)

### Software

- ESPHome firmware with `bluetooth_proxy:` component
- `bleak-esphome` Python package (add to `pyproject.toml`)
- `aioesphomeapi` Python package (dependency of `bleak-esphome`)

### Network

- Wi-Fi network accessible by both ESP32 and Linux host
- ESP32 IP address (static or DHCP reservation recommended)

## Timeline

| Phase | Duration | Dependencies |
|---|---|---|
| Phase 1: ESP32 Setup | 1-2 days | Hardware, ESPHome |
| Phase 2: Discovery | 1 day | Phase 1 |
| Phase 3: Connection | 1-2 days | Phase 2 |
| Phase 4: MCSP Handshake | 1 day | Phase 3 |
| Phase 5: Codebase Integration | 2-3 days | Phase 4 |
| Phase 6: Testing | 2-3 days | Phase 5 |
| **Total** | **8-12 days** | |

## Success Criteria

The ESP32 proxy approach is successful if:

1. ESP32 can detect the Bosch bike in pairing mode
2. ESP32 can connect to the bike
3. ESP32 can pair with the bike (SMP succeeds)
4. MCSP handshake completes
5. MessageBus data is readable
6. Live session is stable for 10+ minutes

If all criteria are met, we have a working path that bypasses the BlueZ SMP issue.

## Fallback Plan

If the ESP32 proxy approach fails (e.g., ESP32 also distributes CSRK), we can:

1. **Try a different BLE adapter** -- Nordic nRF52840 dongle with Zephyr firmware
2. **Patch BlueZ** -- Modify BlueZ's SMP handler to distribute IRK (complex, kernel-level)
3. **Use a phone as a bridge** -- Run a BLE proxy app on a phone, forward to Linux (hacky)
4. **Accept the limitation** -- Document that Linux pairing is not possible with current hardware

## Conclusion

The ESP32 Bluetooth Proxy approach is a pragmatic solution that leverages existing, well-tested infrastructure (ESPHome, bleak-esphome) to bypass the Linux BlueZ SMP issue. It requires minimal code changes and has a high probability of success.

The key insight is that the ESP32's BLE stack is closer to a phone's stack than Linux BlueZ, so it should produce phone-like SMP parameters (IRK distribution) that the Bosch bike will accept.

## Next Steps

1. Order ESP32 hardware (if not already available)
2. Flash ESP32 with Bluetooth Proxy firmware
3. Begin Phase 1 testing
4. Document findings in `findings/` directory

## References

- bleak-esphome documentation: https://bleak-esphome.readthedocs.io/
- ESPHome Bluetooth Proxy: https://esphome.io/components/bluetooth_proxy.html
- Bosch Android app pairing flow: `docs/bosch-android-app/pairing-flow.md`
- Current design: `docs/current-design.md`
- Pairing blocker summary: `docs/2026-04-20-pairing-blocker-summary.md`
