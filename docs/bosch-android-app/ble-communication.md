# BLE Communication

The Bosch eBike Flow app communicates with the eBike via Bluetooth Low Energy
(BLE). This document covers the complete BLE stack from low-level GATT
operations to the high-level MessageBus API used by feature modules.

## BLE Stack Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Feature Modules                           │
│  (Riding, Antitheft, FOTA, BikeSettings, etc.)              │
│  Access bike data via typed DataPoint<T> objects            │
├─────────────────────────────────────────────────────────────┤
│                    MessageBus                                │
│  Typed API: Read/Write/Subscribe/RPC on DataPoints          │
│  10 entity proxies: DriveUnit, Battery, RemoteControl, etc. │
├─────────────────────────────────────────────────────────────┤
│                 CommunicationStack                           │
│  Binary protocol: message encoding/decoding                 │
│  Sequence numbers, routing, request/response correlation    │
├─────────────────────────────────────────────────────────────┤
│              BluetoothCommunication                          │
│  GATT operations: read/write/notify                         │
│  Connection lifecycle, bonding, MTU negotiation             │
├─────────────────────────────────────────────────────────────┤
│                    BLE Wrapper                               │
│  Coroutine-friendly wrapper around Android BluetoothGatt    │
│  Flow-based connection state and GATT events                │
├─────────────────────────────────────────────────────────────┤
│                 Android BLE API                              │
│  BluetoothLeScanner, BluetoothGatt, BluetoothDevice         │
└─────────────────────────────────────────────────────────────┘
```

## GATT Services and Characteristics

### MCSP (Main Communication Service Protocol)

The primary bidirectional data channel between the app and the bike.

| Role                                                     | UUID                                   |
| -------------------------------------------------------- | -------------------------------------- |
| **Service**                                              | `00000010-EAA2-11E9-81B4-2A2AE2DBCCE4` |
| **Receive Characteristic** (bike → phone, notifications) | `00000011-EAA2-11E9-81B4-2A2AE2DBCCE4` |
| **Send Characteristic** (phone → bike, write)            | `00000012-EAA2-11E9-81B4-2A2AE2DBCCE4` |

**Location:**
`smali_classes3/com/bosch/ebike/communicationstack/McspGattConfig.smali`

All MessageBus traffic (read/write/subscribe/RPC) flows through these two
characteristics. The app writes commands to the Send characteristic and receives
responses/notifications on the Receive characteristic.

### BES3 (Bosch eBike System 3)

A Bosch-proprietary service used for **BLE scan filtering** in background mode.

| Role        | UUID                                   |
| ----------- | -------------------------------------- |
| **Service** | `0000FE02-0000-1000-8000-00805F9B34FB` |

**Location:**
`smali_classes3/com/bosch/ebike/bluetoothcommunication/config/bes3/Bes3EbikeGattService.smali`

This 16-bit UUID (`0xFE02`) is used as the scan filter service UUID in
`BluetoothLeBackgroundScanner`. The background scan only wakes the app when a
device advertising this service UUID is detected.

### COBI (COBI Bike Integration)

Legacy integration for COBI bike systems.

| Device | Service UUID                           |
| ------ | -------------------------------------- |
| CUI050 | `C0B11800-FEE1-C001-FEE1-FA57FEE15AFE` |
| CUI100 | `C0B11802-FEE1-C001-FEE1-FA57FEE15AFE` |

**Location:**
`smali_classes3/com/bosch/ebike/bluetoothcommunication/config/cobi/CobiGattConfig.smali`

### Heart Rate Monitor

Standard Bluetooth SIG Heart Rate Service for external HR sensors.

| Role        | UUID                                   |
| ----------- | -------------------------------------- |
| **Service** | `0000180D-0000-1000-8000-00805F9B34FB` |

**Location:**
`smali_classes3/com/bosch/ebike/bluetoothcommunication/config/heartratemonitor/HeartRateMonitorGattService.smali`

### Standard GATT Descriptors

| Name                                      | UUID                                   |
| ----------------------------------------- | -------------------------------------- |
| Client Characteristic Configuration (CCC) | `00002902-0000-1000-8000-00805f9b34fb` |
| Client Characteristic Description         | `00002901-0000-1000-8000-00805f9b34fb` |
| GATT Database Hash                        | `00002B2A-0000-1000-8000-00805F9B34FB` |

## Connection Lifecycle

### 1. App Initialization

When the app starts, `App.onCreate()` initializes Koin and starts the pocket
mode services. The `KeepPrimaryBikeConnected` AppExtension begins observing the
primary bike and connection triggers.

**Key file:**
`smali_classes4/com/bosch/ebike/pocketmode/services/core/KeepPrimaryBikeConnected.smali`

### 2. Background Auto-Reconnection (Pocket Mode)

The app maintains a persistent connection to the primary bike using **Pocket
Mode** -- Bosch's term for background auto-reconnection.

**Pocket Mode Strategies:**

| Strategy                            | Mechanism                               | When Used                   |
| ----------------------------------- | --------------------------------------- | --------------------------- |
| `BackgroundScan`                    | BLE background scan with PendingIntent  | Default strategy            |
| `CompanionDeviceAssociationMissing` | Companion Device Manager (CDM) presence | When CDM association exists |
| `BackgroundScanPlusCompanionDevice` | Both BLE scan + CDM                     | Optimal/ideal state         |

**Key files:**

- `smali_classes4/com/bosch/ebike/pocketmode/services/PocketModeStrategy.smali`
- `smali_classes4/com/bosch/ebike/pocketmode/services/DefaultGetPocketModeStrategy.smali`
- `smali_classes4/com/bosch/ebike/pocketmode/services/optimal/DefaultPocketModeReconnection.smali`

#### Background BLE Scanning

Uses Android's `BluetoothLeScanner.startScan()` with:

**Scan Filter:**

- Device MAC address (primary bike)
- Service UUID: `0000FE02-0000-1000-8000-00805F9B34FB` (BES3)

**Scan Settings:**

- `callbackType = CALLBACK_TYPE_FIRST_MATCH` (1)
- `matchMode = MATCH_MODE_STICKY` (2)
- `setLegacy(true)`
- `scanMode = SCAN_MODE_LOW_POWER` (0) on API 28+, `SCAN_MODE_BALANCED` (1)
  below

**Callback:** PendingIntent targeting `BackgroundScanReceiver`

**Key file:**
`smali_classes4/com/bosch/ebike/pocketmode/services/optimal/backgroundscan/BluetoothLeBackgroundScanner.smali`

#### Companion Device Manager

The bike is registered as a **Companion Device** via Android's
`CompanionDeviceManager`. When the bike is detected nearby, Android calls
`CompanionBikeService.onDeviceAppeared()`.

**Key file:**
`smali_classes4/com/bosch/ebike/pocketmode/services/optimal/companiondevice/CompanionBikeService.smali`

**Manifest declarations:**

```xml
<uses-feature android:name="android.software.companion_device_setup"/>
<uses-permission android:name="android.permission.REQUEST_COMPANION_RUN_IN_BACKGROUND"/>
<uses-permission android:name="android.permission.REQUEST_OBSERVE_COMPANION_DEVICE_PRESENCE"/>

<service android:exported="true"
         android:name="com.bosch.ebike.pocketmode.services.optimal.companiondevice.CompanionBikeService"
         android:permission="android.permission.BIND_COMPANION_DEVICE_SERVICE">
    <intent-filter>
        <action android:name="android.companion.CompanionDeviceService"/>
    </intent-filter>
</service>
```

### 3. Connection Decision Chain

The connection is triggered by a reactive flow architecture:

```
ShouldConnectManager (aggregates multiple FlowProvider sources)
  ├─ BluetoothAvailabilityInForegroundFlowProvider
  │    Emits: ConnectReason.BluetoothAvailable
  ├─ BackgroundScanTriggerFlowProvider
  │    Emits: ConnectReason.BikeDetectedInBackgroundScan
  ├─ CompanionDeviceTriggerFlowProvider
  │    Emits: ConnectReason.BikeDetectedAsCompanionDevice
  └─ IsAppStartedFlowProvider
       Emits: ConnectReason.AppUiShown
```

When any `ConnectReason` fires,
`DefaultPocketModeReconnection.triggerConnectionTo()` initiates the connection.

**Key file:**
`smali_classes4/com/bosch/ebike/pocketmode/services/core/ShouldConnectManager.smali`

### 4. GATT Connection

`GattWrapperPeripheral` handles the low-level GATT connection:

**Connection sequence:**

1. `connect()` -- Create or reuse `BluetoothGatt` instance
2. `onConnectedInternallyCompleteSetup()`:
   - `discoverServicesAndLog()` -- Discover all GATT services
   - `requestMaximumMtuOrDisconnect()` -- Negotiate maximum MTU (up to 512
     bytes)
   - `enableNotifications()` -- Write CCC descriptor (`0x2902`) to enable
     notifications on MCSP receive characteristic
   - `detectGattDatabaseChanges()` -- Read GATT Database Hash (`0x2B2A`) to
     detect if bike's GATT database changed
   - `onConnectFinalizeSetup()` -- Finalize connection setup
3. Connection state transitions to `Connected`

**Key file:**
`smali_classes3/com/bosch/ebike/bluetoothcommunication/connection/GattWrapperPeripheral.smali`

### 5. Disconnection and Reconnection

When the bike disconnects:

1. `handleBikeDisconnected()` is called
2. Background scan and CDM observation are restarted
3. A cool-down period prevents rapid re-triggering
4. The cycle repeats from step 2

**Error handling:**

- `onBondingDeniedDisconnect()` -- Bonding was denied by user
- `onBluetoothTurnedOffDisconnect()` -- Bluetooth was turned off
- `ensureDisconnectOnBikeShutdown()` -- Bike powered off

## BLE Wrapper Layer

The `ble/wrapper/` package provides a coroutine-friendly wrapper around
Android's `BluetoothGatt` API.

**Key classes:**

| Class             | Purpose                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| `GattDevice`      | Interface for GATT operations                                                                                  |
| `GattDeviceImpl`  | Implementation wrapping `BluetoothGatt`                                                                        |
| `GattCallback`    | Converts Android callbacks to Kotlin Flows                                                                     |
| `ConnectionState` | Sealed class: Connecting, Connected, Disconnecting, Disconnected                                               |
| `GattEvent`       | Sealed class: CharacteristicRead, CharacteristicChanged, CharacteristicWritten, ServicesDiscovered, MtuChanged |
| `GattError`       | Sealed class: GattTimeoutError, GattException, GattDeviceClosed, GattCallNotSuccessful                         |

**Key file:** `smali_classes3/com/bosch/ebike/ble/wrapper/GattDeviceImpl.smali`

**Flow-based API:**

```kotlin
// Connection state as a Flow
val connectionState: Flow<ConnectionState>

// GATT events as a Flow
val gattEvents: Flow<GattEvent>

// Suspend functions for operations
suspend fun connect(): ConnectionState
suspend fun discoverServices()
suspend fun readCharacteristic(uuid: UUID): ByteArray
suspend fun writeCharacteristic(uuid: UUID, data: ByteArray)
suspend fun enableNotifications(uuid: UUID)
```

## CommunicationStack (Protocol Layer)

The `communicationstack/` package implements the binary protocol over BLE GATT.

### Message Types

**Outbound (phone → bike):**

- `ReadMessage` -- Read a data point value
- `WriteMessage` -- Write a data point value
- `SubscribeMessage` -- Subscribe to data point changes
- `UnsubscribeMessage` -- Unsubscribe from data point changes
- `RpcCallMessage` -- Remote procedure call

**Inbound (bike → phone):**

- `ReadResponseMessage` -- Response to read request
- `WriteResponseMessage` -- Response to write request
- `SubscribeResponseMessage` -- Response to subscribe request
- `RpcResponseMessage` -- Response to RPC call
- `NotifyMessage` -- Push notification from bike (data point changed)

### Message Encoding

Messages are encoded as binary payloads:

- **Sequence number** (2 bytes) -- For request/response correlation
- **Message type** (1 byte) -- Read, Write, Subscribe, etc.
- **Data point address** (2 bytes) -- Identifies the data point
- **Payload** (variable) -- Data value or RPC parameters

**Key files:**

- `smali_classes3/com/bosch/ebike/communicationstack/message/MessageEncodingKt.smali`
- `smali_classes3/com/bosch/ebike/communicationstack/message/MessageDecodingKt.smali`

### Gateway and Broker

The `Gateway` interface routes messages between the MessageBus and BLE
transport:

```text
MessageBus (typed DataPoint API)
    ↓
Broker (message router)
    ↓
InternalGateway (protocol encoder/decoder)
    ↓
CommunicationStack (BLE GATT operations)
```

**Key files:**

- `smali_classes3/com/bosch/ebike/communicationstack/messagebus/Broker.smali`
- `smali_classes3/com/bosch/ebike/communicationstack/messagebus/InternalGatewayImpl.smali`

## MessageBus (Application Layer)

The `messagebus/` package provides the high-level typed API used by feature
modules.

### Entity Proxies

The `MessageBus` class exposes 10 entity proxies, one per physical bike
component:

| Entity                | Represents          | Data Points                                                              |
| --------------------- | ------------------- | ------------------------------------------------------------------------ |
| `DriveUnit`           | Motor/drive unit    | 200+ (assist modes, speed, torque, cadence, bike light, crash detection) |
| `Battery`             | Primary battery     | 80+ (SoC, voltage, temperature, charge cycles)                           |
| `Battery2`            | Secondary battery   | Dual-battery systems                                                     |
| `RemoteControl`       | Handlebar remote    | 300+ (button events, BLE config, software updates, ride stats)           |
| `HeadUnit`            | Display head unit   | Tiles, view stripes, brightness, languages                               |
| `ConnectModule`       | GPS/cellular module | GNSS, modem, remote config                                               |
| `AntiLockBrakeSystem` | ABS module          | Brake events, wheel speeds, ABS modes                                    |
| `MobileApp`           | The phone itself    | Location, altitude, heart rate, navigation data (sent TO bike)           |
| `BoschDiagnoseApp`    | Diagnostic app      | Diagnostic interface                                                     |
| `CanTestNode`         | CAN bus test        | CAN bus testing                                                          |

### DataPoint Types

```kotlin
interface DataPoint<T> {
    val address: Address
    val gateway: Gateway
}

interface ReadableDataPoint<T> : DataPoint<T> {
    suspend fun read(): T
}

interface WritableDataPoint<T> : DataPoint<T> {
    suspend fun write(value: T)
}

interface SubscribableDataPoint<T> : DataPoint<T> {
    fun subscribe(): Flow<T>
}

interface CallableDataPoint : DataPoint<*> {
    suspend fun call(vararg args: Any): Any
}
```

### Addressing

Each entity has an `Addresses` enum with hundreds of named addresses. For
example:

**DriveUnitAddresses:**

- `BIKE_SPEED`
- `ASSIST_MODE`
- `MOTOR_TORQUE`
- `CRASH_DETECTION_CONFIG`
- `BIKE_LIGHT`
- `ODO_METER`

**BatteryAddresses:**

- `STATE_OF_CHARGE`
- `VOLTAGE`
- `CURRENT`
- `TEMPERATURE`
- `CHARGE_CYCLES`

**Key files:**

- `smali_classes4/com/bosch/ebike/messagebus/MessageBus.smali`
- `smali_classes4/com/bosch/ebike/messagebus/constants/DriveUnitAddresses.smali`
- `smali_classes4/com/bosch/ebike/messagebus/constants/BatteryAddresses.smali`

### Usage Example

```kotlin
// Inject MessageBus
val messageBus: MessageBus by inject()

// Read battery state of charge
val soc: Uint8 = messageBus.Battery.stateOfCharge.read()

// Subscribe to speed changes
messageBus.DriveUnit.bikeSpeed.subscribe().collect { speed ->
    updateSpeedDisplay(speed)
}

// Write assist mode
messageBus.DriveUnit.assistMode.write(AssistMode.TOUR)

// Read drive unit info
val info = messageBus.DriveUnit.driveUnitInfo.read()
```

## BES3 Protobuf Data Model

The `bes3/` package defines the Protocol Buffers schema for all bike data. This
is the canonical data model used for:

- BLE communication (MessageBus wire format)
- Cloud sync (REST API payloads)
- Activity storage (ride tracking)

### Key Protobuf Messages

**ActivityService:**

- `ActivityDetails` -- Per-second telemetry: bike speed, motor power/torque,
  rider cadence/power/torque, altitude, elevation gain/loss, road slope,
  atmospheric pressure, assist mode, odometer
- `ActivitySummary` -- Aggregate ride stats
- `LocationActivityDetails` -- GPS: lat/lon/accuracy
- `HealthActivityDetails` -- Heart rate
- `BrakeEvents` -- Brake usage
- `AssistModeUsage` -- Time in each assist mode
- `TrickStats` -- Jump distance, air time, etc.

**DashboardService:**

- `BikeLightOn/Off`
- `BatteryInfo` (SoC, remaining energy, serial number)
- `BatteryStateOfChargeChange`
- `AssistanceModeChange`
- `BikeSystemConnected/Disconnected`

**MessageBus wire format:**

- `Uint8Message`, `Uint16Message`, `Uint32Message`, `Uint64Message` -- Numeric
  types with normalization factors
- `AbsModeEnumType`, `WalkAssistStateEnumType`, `UpdateTypeEnumType` -- Enum
  types
- `WalkAssistConfiguration`, `ViewStripeConfiguration`, `UnlockToken` --
  Composite types

**Key files:**

- `smali_classes3/com/bosch/ebike/bes3/ActivityService.smali`
- `smali_classes3/com/bosch/ebike/bes3/DashboardService.smali`
- `smali_classes4/com/bosch/ebike/messagebus/message/` -- Wire format messages

## Large Binary Transport

FOTA firmware updates require transferring large binaries (several MB) over BLE.
The `largebinarytransport/` package implements a chunked transfer protocol.

**Key classes:**

- `LargeBinaryTransportService` -- Orchestrates the transfer
- `MessageChunker` -- Splits binary into chunks
- `Server/` -- Transfer server on the bike side

**Key file:** `smali_classes3/com/bosch/ebike/largebinarytransport/`

## Permissions

The app requires these BLE-related permissions:

```xml
<uses-feature android:name="android.hardware.bluetooth_le" android:required="true"/>
<uses-permission android:name="android.permission.BLUETOOTH_SCAN" android:usesPermissionFlags="neverForLocation"/>
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT"/>
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION"/>
<uses-permission android:name="android.permission.REQUEST_COMPANION_RUN_IN_BACKGROUND"/>
<uses-permission android:name="android.permission.REQUEST_COMPANION_USE_DATA_IN_BACKGROUND"/>
<uses-permission android:name="android.permission.REQUEST_OBSERVE_COMPANION_DEVICE_PRESENCE"/>
```

## Troubleshooting

### Common Issues

**Bike not detected:**

- Check if bike is powered on and advertising
- Verify BLE is enabled on the phone
- Check location permissions (required for BLE scan on Android 11+)
- Look for `BikeDetectedInBackgroundScan` or `BikeDetectedAsCompanionDevice` in
  logs

**Connection drops:**

- Check signal strength (RSSI)
- Verify bike battery level
- Check for interference (other BLE devices)
- Look for `GattTimeoutError` or `GattException` in logs

**Bonding issues:**

- Ensure bike is in pairing mode
- Check if phone has reached BLE bond limit (max 4 devices on most phones)
- Look for `onBondingDeniedDisconnect` in logs

**Background reconnection not working:**

- Verify Companion Device association exists
- Check if background scan is active (look for
  `BluetoothLeBackgroundScanner.startScan` in logs)
- Ensure battery optimization is disabled for the app
- Check `PocketModeStrategy` to see which strategy is active

## Further Reading

- [Architecture Overview](architecture.md) -- High-level system design
- [Backend & API](backend-api.md) -- Cloud services
- [Feature Modules](feature-modules.md) -- How features use the BLE stack
