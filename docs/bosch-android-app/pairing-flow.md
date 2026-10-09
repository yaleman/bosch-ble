# Bosch eBike Flow Android App -- Pairing Flow Deep Dive

This document reconstructs the complete bike pairing flow from the decompiled Bosch eBike Flow Android app (v1.34.6). This is the reference implementation we need to replicate from Linux.

## Overview

The Android pairing flow is a 7-state state machine managed by `BikePairingProcessServiceImpl`. It handles discovery, Companion Device Manager association, BLE connection, implicit bonding, and cloud registration.

**Key source file:** `smali_classes3/com/bosch/ebike/bikepairing/services/internal/BikePairingProcessServiceImpl.smali`

## State Machine

```
PairingProcessState (sealed class)
├── Searching              -- BLE scan active, looking for pairable bikes
├── Detected               -- A pairable bike was found
├── Connecting             -- GATT connection + bonding in progress
├── Paired                 -- BLE bonding succeeded
├── Registering            -- Cloud registration in progress
├── CreateCompanionship    -- CDM association dialog shown (Android 12+)
└── Failed(reason)         -- Terminal failure with FailedErrorCase
```

**Source:** `smali_classes3/com/bosch/ebike/bikepairing/services/PairingProcessState.smali`

## 19 Failure Cases

| Error Case | Meaning |
|---|---|
| `AlreadyRegisteredToAnotherUser` | Ownership conflict -- bike registered to different account |
| `AppOutdated` | App version too old for this bike |
| `BikeMarkedAsStolen` | Bike flagged stolen in backend |
| `BluetoothBondingRemoved` | Bond deleted mid-process |
| `BluetoothPermissionsNotGranted` | Required BT permissions denied |
| `BluetoothUnavailable` | Bluetooth hardware not available |
| `CompanionshipCreationFailed` | Android CDM association failed |
| `ConnectionError` | Generic BLE connection error |
| `DiscoveryTimeoutError` | No pairable bike found within timeout |
| `GenericError` | Catch-all |
| `HeadUnitInBootloader` | Display unit in firmware update mode |
| `IncompatibleBike` | Bike not compatible with Flow app (BES2/COBI) |
| `IncompatibleBluetoothSpec` | Phone BT hardware not supported |
| `InvalidBikeData` | Corrupt/unreadable bike data |
| `InvalidBikeId` | Bad bike identifier |
| `OneOrMoreComponentsInBootloader` | Components in firmware update mode |
| `PairingRejected` | Bike rejected the pairing request |
| `RegistrationTimeout` | Cloud registration timed out |
| `ServerError` | Backend error during registration |

**Source:** `smali_classes3/com/bosch/ebike/bikepairing/services/FailedErrorCase.smali`

## Complete Pairing Sequence

### Phase 0: Preconditions Check

Before pairing starts, the app verifies:
- Bluetooth is on
- Location services are on
- Internet connectivity is available
- Bluetooth permissions granted
- Location permissions granted

**Source:** `smali_classes3/com/bosch/ebike/bikepairing/views/preconditions/check/PairingConditionsCheckFragment.smali`

### Phase 1: BRC Selection

The user selects which Bike Ride Computer (BRC) type they are pairing:

| BRC Type | Description |
|---|---|
| `LedRemote` | LED remote control |
| `SystemController` | System controller |
| `Purion200` | Purion 200 display |
| `Kiox400` | Kiox 400 display |
| `BRC3610` | BRC 3610 display |

**Source:** `smali_classes3/com/bosch/ebike/bikepairing/services/BrcType.smali`

### Phase 2: BLE Discovery (Searching State)

The app calls `pairBike.discoverPairableBikes()` which returns a `Flow<Result<BikeDiscoveryError, Set<PairableBike>>>`.

#### Scan Parameters

The underlying BLE scan in `CentralManagerImpl.startDiscovery()` uses:

```
ScanSettings:
  scanMode = SCAN_MODE_LOW_LATENCY (2)
  callbackType = CALLBACK_TYPE_ALL_MATCHES (1)
  scanFilters = null  (NO FILTERS -- completely unfiltered scan)
```

**Critical:** The scan is completely unfiltered. All BLE devices are returned, and filtering happens in post-processing.

**Source:** `smali_classes3/com/bosch/ebike/bluetoothcommunication/internal/scanning/CentralManagerImplKt.smali` (line ~241)

#### Advertisement Post-Processing

For each `ScanResult`, the app calls `AdvertisementDataMappingKt.toPeripheralDiscoveryInfo()` which:

1. Extracts MAC address, device name, service UUIDs, RSSI, bond state, manufacturer data
2. Calls `getPeripheralType(serviceUUIDs, manufacturerData)` to classify the device
3. Calls `getPairability(manufacturerData, peripheralType)` to determine if it's pairable

#### Peripheral Type Detection

Classification checks service UUIDs and manufacturer data in order:

| Priority | Type | Detection Method |
|---|---|---|
| 1 | COBI CobiPro | Service UUID `C0B11800-FEE1-C001-FEE1-FA57FEE15AFE` |
| 2 | COBI SmartphoneHub | Service UUID `C0B11802-FEE1-C001-FEE1-FA57FEE15AFE` |
| 3 | Heart Rate Monitor | Service UUID `0000180D-0000-1000-8000-00805F9B34FB` |
| 4 | BES2 | Manufacturer-specific data format check |
| 5 | **BES3** | Service UUID `0000FE02-0000-1000-8000-00805F9B34FB` + valid manufacturer data |
| 6 | Unknown | Fallback |

**Source:** `smali_classes3/com/bosch/ebike/bluetoothcommunication/internal/AdvertisementDataMappingKt.smali` (line ~248)

#### BES3 Advertisement Data Format

The critical detection for modern Bosch bikes:

```
Manufacturer ID: 0x02A6 (678 decimal = Bosch)
Data length: exactly 6 bytes

Byte layout:
  [0..1] prefix (not interpreted by the Android BES3 mapper)
  [2] eBikeComponentIdVersion
  [3] eBikeComponentId
  [4] dataFormatVersion
  [5] pairable flag (MUST equal 0x01 for pairing)
```

Component IDs map to: BRC3100 (0), BRC3300 (1), BRC3600 (2), BRC3800 (3), BRC3200 (4), BRC3610 (5)

**Source:** `smali_classes3/com/bosch/ebike/bluetoothcommunication/internal/bes3/BES3AdvertismentDataMappingKt.smali` (method `bes3AdvertisementInformation`)

#### Pairability Determination

| Peripheral Type | Pairable When |
|---|---|
| BES3 | byte[5] == 0x01 in the six-byte Bosch manufacturer payload |
| BES2 | Never (`NotPairable(IsBES2Bike)`) |
| COBI | Never (`NotPairable(IsCOBIBike)` or `NotPairable(NotInPairingMode)`) |
| HRM | Never (`NotPairable(IsHeartRateMonitor)`) |
| Unknown | `Pairability.Unknown` |

**Source:** `smali_classes3/com/bosch/ebike/bluetoothcommunication/internal/AdvertisementDataMappingKt.smali` (method `getPairability`)

#### Key Takeaway for Linux Implementation

The app looks for:
1. Service UUID `0000FE02-0000-1000-8000-00805F9B34FB` in advertisement
2. Manufacturer data with company ID `0x02A6` and exactly 6 bytes
3. byte[5] == `0x01` (pairable flag)

Bleak strips the two-byte Bluetooth company ID, but retains all six payload bytes.
The captured Purion 200 payload is `10eb01030001`: component version 1,
component ID 3 (BRC3800), data format 0, and pairable 1. The former Linux check
compared that entire payload with `01030001`, incorrectly rejecting it. Linux now
selects company `0x02A6`, validates the six-byte length, and reads the final field,
matching the Android mapper rather than comparing an exact component-specific blob.

### Phase 3: Companion Device Manager Association (Android 12+ only)

Before BLE connection, on Android 12+ (API 31), the app creates a Companion Device association.

#### When CDM Is Required

`companionDeviceManagerCompat.isCompanionshipRequiredForBike(uuid)` returns true when:
- Android 12+ (API 31+)
- No existing CDM association for this bike

**Source:** `smali_classes3/com/bosch/ebike/ble/companiondevice/CompanionDeviceManagerCompat.smali`

#### CDM Association Flow

1. Emit `PairingProcessState.CreateCompanionship`
2. Create `ScanFilter` with `setDeviceAddress(bikeMacAddress)`
3. Wrap in `BluetoothLeDeviceFilter`
4. Create `AssociationRequest` with `setSingleDevice(true)`
5. Call `CompanionDeviceManager.associate(request, callback, handler)`
6. Wait up to **30 seconds** for result
7. On success: `onCompanionshipCreated()` -> continue to BLE pairing
8. On failure: emit `Failed(CompanionshipCreationFailed)` and cancel

**Source:** `BikePairingProcessServiceImpl.smali` (line ~759, `createCompanionship()`)

#### CDM Result Handling

- On `RESULT_OK`:
  - Android 14+: extract `AssociationInfo` from intent, get MAC address
  - Android 12-13: extract `ScanResult` from intent, get `BluetoothDevice`
  - Log "CDM Pairing successful {address}"
- On device not found: `Result.Failure(DeviceNotFoundAfterPairing)`
- On cancel: `Result.Failure(PairingCancelledByUser)`

#### Key Takeaway for Linux

CDM is Android-specific and has no Linux equivalent. On Linux, we skip this step entirely. The ESP32 proxy approach also bypasses this since the ESP32 handles the BLE radio directly.

### Phase 4: BLE Connection (Connecting State)

After CDM (or if not needed), the app calls:

```kotlin
pairBike.pair(peripheralId, autoConnect = true)
```

This returns a `Flow<BikePairingState>` that emits state updates.

#### GATT Connection

The underlying connection in `GattDeviceImplKt.connectGattDevice()`:

```java
bluetoothDevice.connectGatt(context, autoConnect, gattCallback, TRANSPORT_LE, phy, handler)
```

**Key detail:** The app does NOT explicitly call `createBond()`. Bonding happens **implicitly** when the bike firmware requires encrypted access to GATT characteristics during service discovery.

**Source:** `smali_classes3/com/bosch/ebike/ble/wrapper/GattDeviceImplKt.smali` (line ~26)

#### Post-Connection Setup

After GATT connection is established:

1. `discoverServicesAndLog()` -- Discover all GATT services
2. `requestMaximumMtuOrDisconnect()` -- Negotiate maximum MTU (up to 512 bytes)
3. `enableNotifications()` -- Write CCC descriptor (`0x2902`) to enable notifications on MCSP receive characteristic
4. `detectGattDatabaseChanges()` -- Read GATT Database Hash (`0x2B2A`)
5. `onConnectFinalizeSetup()` -- Finalize connection

**Source:** `smali_classes3/com/bosch/ebike/bluetoothcommunication/connection/GattWrapperPeripheral.smali`

### Phase 5: Implicit Bonding (Paired State)

When the app tries to access secured GATT characteristics (e.g., write CCCD for notifications), the bike firmware initiates SMP pairing.

#### Bond State Monitoring

`DefaultBondStateManager` monitors bonding via `BroadcastReceiver` for `BluetoothDevice.ACTION_BOND_STATE_CHANGED`:

| Android Value | Mapped State |
|---|---|
| 10 (`BOND_NONE`) | `BondingState.NONE` |
| 11 (`BOND_BONDING`) | `BondingState.BONDING` |
| 12 (`BOND_BONDED`) | `BondingState.BONDED` |

#### Bonding Denial Handling

`GattWrapperPeripheral.onBondingDeniedDisconnect()` monitors bond state transitions:
- If transition is `[BONDING -> NONE]` while connected
- Log: "User denied bonding explicitly, giving up"
- Disconnect with reason `DisconnectReason.BONDING_DENIED`

#### No PIN/Passkey Handling

The app does NOT handle explicit PIN/passkey. It uses Android's default bonding mechanism, which for BLE devices with MITM protection shows the system pairing dialog (numeric comparison or just-works depending on device capabilities).

**Key Takeaway for Linux:** This confirms our connect-first approach is correct. The Android app doesn't explicitly pair either -- it connects and lets the bike trigger bonding when it needs encryption.

### Phase 6: Cloud Registration (Registering State)

After BLE bonding succeeds, the app registers the bike with the Bosch cloud:

1. Send bike identity (MAC address / peripheral ID) to backend
2. Send pairing proof (established during BLE bonding)
3. Backend validates and creates the bike-rider association

#### Registration States

```
BikePairingState (sealed class)
├── PairingBike                    -- BLE pairing in progress
├── RegisteringWithCloud           -- Cloud registration started
├── AskForRegisteringWithObcRetry  -- Network error, retry available
│   └── reason: NetworkError | Unknown
│   └── retryRegistration: () -> Unit
└── Registered                     -- Success
```

#### Error Handling

- **Network error**: `AskForRegisteringWithObcRetry` -- user can retry registration
- **Already registered**: `Failed(AlreadyRegisteredToAnotherUser)` -- ownership conflict
- **Stolen bike**: `Failed(BikeMarkedAsStolen)` -- diverted to stolen bike flow
- **Server error**: `Failed(ServerError)`
- **Timeout**: `Failed(RegistrationTimeout)`

### Phase 7: Success

On successful registration, the app navigates to `BikePairingSuccessfulFragment` which can navigate to:
- `NavigateToBikePass` -- Show digital bike pass
- `NavigateToHome` -- Go to home screen
- `NavigateToOemPromo` -- OEM promotional content

## Complete Flow Diagram

```
User taps "Pair Bike"
  |
  v
[Preconditions Check]
  BT on? Permissions? Location? Internet?
  |-- No --> [Missing Conditions Screen] --> Settings
  |-- Yes --> v
  |
[BRC Selection]
  User selects BRC type (LedRemote/Purion200/Kiox400/etc.)
  |
  v
[Searching State]
  Unfiltered BLE scan (SCAN_MODE_LOW_LATENCY)
  Post-filter for:
    - BES3 service UUID 0000FE02-...
    - Manufacturer data: company 0x02A6, 6 bytes
    - Pairable flag: byte[5] == 0x01
  |
  v (bike found)
[Detected State]
  |
  v
[CDM Association] (Android 12+ only)
  ScanFilter: deviceAddress = bike MAC
  AssociationRequest: singleDevice = true
  System dialog --> User confirms
  Wait up to 30s for result
  |-- Fail --> [Failed: CompanionshipCreationFailed]
  |-- Success --> v
  |
[Connecting State]
  connectGatt(autoConnect=true, TRANSPORT_LE)
  GATT connection established
  Discover services, negotiate MTU
  |
  v
[Implicit Bonding]
  Bike firmware triggers SMP when secured characteristics accessed
  Bond state: NONE -> BONDING -> BONDED
  |-- Bonding denied --> Disconnect with BONDING_DENIED
  |-- Timeout --> [Failed: ConnectionError]
  |
  v
[Paired State]
  |
  v
[Registering State]
  Send bike ID + pairing proof to Bosch cloud
  |-- Network error --> AskForRegisteringWithObcRetry (retryable)
  |-- Already registered --> [Failed: AlreadyRegisteredToAnotherUser]
  |-- Stolen --> [Failed: BikeMarkedAsStolen]
  |-- Server error --> [Failed: ServerError]
  |-- Success --> v
  |
[Registered] --> [BikePairingSuccessful Screen]
  --> NavigateToBikePass / NavigateToHome / NavigateToOemPromo
```

## Comparison with Linux Implementation

### What We Do the Same

| Aspect | Android App | Our Linux Path |
|---|---|---|
| Discovery | Unfiltered scan, post-process for BES3 | Same -- `scan_device_advertisement()` with post-filter |
| Pairing advertisement check | Company 0x02A6, 6 bytes, byte[5] == 0x01 | Same -- parsed pairable field |
| Connection approach | connect-first, implicit bonding | Same -- `connect_device()` then `stage_bosch_security()` |
| CCCD write for security trigger | Write `0x2902` to enable notifications | Same -- `write_gatt_descriptor(descriptor.handle, b"\x00\x00")` |
| MCSP service UUID | `00000010-EAA2-11E9-81B4-2A2AE2DBCCE4` | Same -- `BOSCH_SERVICE_UUID` |

### What We Do Differently

| Aspect | Android App | Our Linux Path | Impact |
|---|---|---|---|
| CDM association | Required on Android 12+ | N/A on Linux | No equivalent needed |
| Explicit pairing | Never -- implicit bonding | `stage_bosch_security()` pairs if needed | Same end result |
| Connection parameters | Phone defaults (30ms/720ms) | `bluez_load_connection_parameters()` | Requires root mgmt socket |
| SMP key distribution | IRK (Identity Resolving Key) | CSRK (Connection Signature Resolving Key) | **BLOCKER** -- bike rejects CSRK |
| BLE adapter | Phone's integrated BLE | USB CSR adapter (suspect) | Hardware limitation |

### The SMP Key Distribution Problem

From our sniffer captures, the phone sends:

| Field | Phone | Linux |
|---|---|---|
| IO Capability | `KeyboardDisplay` | `KeyboardDisplay` |
| AuthReq | `Bonding, MITM, SC, CT2` | `Bonding, MITM, SC, CT2` |
| Initiator keys | `0x0b` = **LTK + IRK + LinkKey** | `0x0d` = **LTK + CSRK + LinkKey** |
| Responder keys | `0x0b` = **LTK + IRK + LinkKey** | `0x0f` = **LTK + IRK + CSRK + LinkKey** |

The bike expects the initiator to distribute an **IRK** (Identity Resolving Key) for resolvable private address resolution. Linux distributes **CSRK** instead, which the bike rejects, causing `AuthenticationCanceled`.

This is a BlueZ/kernel-level behavior -- the SMP handler in the Linux kernel chooses which keys to distribute, not our Python code.

## Implications for ESP32 Proxy Approach

Using an ESP32 Bluetooth Proxy via `bleak-esphome` bypasses the Linux BlueZ SMP stack entirely:

1. **ESP32 handles BLE radio** -- The ESP32's BLE controller performs the actual BLE operations
2. **ESP32 handles SMP** -- The ESP32's BLE stack handles SMP pairing with its own key distribution
3. **Host just proxies** -- Our Python code sends commands to the ESP32 over Wi-Fi

This means:
- No BlueZ SMP key distribution mismatch
- No USB adapter hardware limitations
- No root mgmt socket requirement for connection parameters
- ESP32's BLE stack is closer to a phone's BLE stack than Linux BlueZ

The ESP32 should produce SMP parameters similar to the phone (IRK instead of CSRK), which the bike will accept.

## Key Files Reference

| File | Path | Purpose |
|---|---|---|
| Pairing state machine | `smali_classes3/.../bikepairing/services/internal/BikePairingProcessServiceImpl.smali` | Core pairing logic |
| Pairing states | `smali_classes3/.../bikepairing/services/PairingProcessState.smali` | State enum |
| Error cases | `smali_classes3/.../bikepairing/services/FailedErrorCase.smali` | 19 failure modes |
| BLE scanning | `smali_classes3/.../bluetoothcommunication/internal/scanning/CentralManagerImplKt.smali` | Scan parameters |
| Advertisement parsing | `smali_classes3/.../bluetoothcommunication/internal/AdvertisementDataMappingKt.smali` | Peripheral type detection |
| BES3 advertisement | `smali_classes3/.../bluetoothcommunication/internal/bes3/BES3AdvertismentDataMappingKt.smali` | BES3 mfg data format |
| GATT connection | `smali_classes3/.../ble/wrapper/GattDeviceImplKt.smali` | connectGatt() call |
| GATT peripheral | `smali_classes3/.../bluetoothcommunication/connection/GattWrapperPeripheral.smali` | Post-connection setup |
| Bond state | `smali_classes3/.../bluetoothcommunication/connection/DefaultBondStateManager.smali` | Bond monitoring |
| CDM manager | `smali_classes3/.../ble/companiondevice/CompanionDeviceManagerCompat.smali` | CDM association |
| PairBike use case | `smali_classes2/.../appcore/usecases/PairBike.smali` | High-level pair interface |
| Nav graph | `res/navigation/bike_pairing_nav_graph.xml` | Screen flow |
