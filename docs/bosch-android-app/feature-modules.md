# Feature Modules

This document provides deep dives into the major feature modules of the Bosch
eBike Flow app.

## Antitheft (3,352 files)

**Location:** `smali_classes2/com/bosch/ebike/antitheft/`

The largest feature module. Comprehensive anti-theft and bike security system
covering the full lifecycle from locking to theft recovery.

### Sub-packages

| Sub-package                  | Purpose                                      |
| ---------------------------- | -------------------------------------------- |
| `services/bikelock/`         | Core bike lock/unlock logic                  |
| `services/batterylock/`      | Battery lock system                          |
| `services/bikeprotect/`      | Onboarding/setup for all anti-theft features |
| `services/crashdetection/`   | Crash detection config and monitoring        |
| `services/theftdetection/`   | Theft alarm system, GPS tracking             |
| `services/markasstolen/`     | Mark bike as stolen in backend               |
| `services/insurance/`        | Theft insurance integration                  |
| `services/ownership/`        | Component ownership management               |
| `services/unlock/`           | Unlock orchestration                         |
| `services/transportmode/`    | Transport mode (disables alarm for shipping) |
| `services/alarmdisablement/` | Disables alarm when subscription lapses      |
| `services/invalidalarm/`     | False alarm handling/reporting               |
| `services/notification/`     | Push notifications for theft events          |
| `datasources/`               | Room DB, remote API, data wiping             |
| `views/`                     | UI fragments                                 |

### Bike Lock System

**Key classes:**

- `BikeLockService` -- Manages lock state with nonces, freshness counters,
  unlock tokens
- `BhuAsKeyService` -- "Bike Head Unit as Key" -- lets head unit or phone act as
  key
- `UnlockService` -- Handles unlock flow

**Error model:** `BikeUnlockError` has 20+ variants:

- `FreshnessError` -- Stale unlock token
- `SignatureError` -- Invalid signature
- `MissingKeyError` -- Key not found
- `Timeout` -- Lock operation timed out
- `ExpirationError` -- Token expired
- `ComponentOwnershipError` -- User doesn't own the component

### Theft Detection

**Key classes:**

- `TheftDetectionService` -- Monitors lock state, tracks alarm duration, manages
  false alarms
- `TheftDetectionStateService` -- Computes overall theft state
- `GeocoderService` -- Reverse-geocodes bike location
- `TrackingModePrimaryBikeManager` -- Runs foreground service for tracking mode

### Subscription Gating

`PremiumFeaturesSubscriptionService` gates alarm features behind Flow+
subscription:

```kotlin
fun isFlowPlusSubscribedAndAlarmDisabled(): Flow<Boolean>
```

When subscription lapses, alarm features are disabled.

---

## FOTA (1,422 files)

**Location:** `smali_classes3/com/bosch/ebike/fota/`

Firmware Over-The-Air update system for all bike components.

### 4-Stage Pipeline

| Stage               | Sub-package              | Key Classes                                                                     |
| ------------------- | ------------------------ | ------------------------------------------------------------------------------- |
| **1. Check**        | `services/check/`        | `CheckAndValidateAndStoreUpdateSet` -- queries backend, validates compatibility |
| **2. Download**     | `services/download/`     | `FotaDownloadService` -- downloads firmware binaries                            |
| **3. Transfer**     | `services/transfer/`     | `FotaTransferService` -- transfers firmware to bike via BLE                     |
| **4. Installation** | `services/installation/` | `FotaInstallationService` -- triggers and monitors installation                 |

### Orchestration

`FotaServiceImpl` is the central orchestrator:

**Dependencies:**

- `connectedPrimaryBikeIdFlow` -- Tracks connected bike
- `networkStatusFlow` -- Checks internet availability
- `fotaPreconditionsService` -- Validates preconditions (battery level, etc.)
- `FotaCleanupService` -- Cleans up old files
- `FotaReportService` -- Generates installation reports

**State flows:**

- `isFotaInstalling(): Flow<Boolean>`
- `isFotaTransferring(): Flow<Boolean>`
- `isFotaPendingOrOngoing(): Flow<Boolean>`

### Other Sub-packages

| Sub-package               | Purpose                         |
| ------------------------- | ------------------------------- |
| `services/appupgrade/`    | Checks if app needs updating    |
| `services/preconditions/` | Validates FOTA preconditions    |
| `services/releasenotes/`  | Release notes display           |
| `services/fotacards/`     | UI cards for FOTA status        |
| `services/analytics/`     | FOTA analytics tracking         |
| `systemtest/`             | Factory/diagnostic FOTA testing |
| `report/`                 | Installation report generation  |
| `views/`                  | UI fragments                    |

---

## MessageBus (1,056 files)

**Location:** `smali_classes4/com/bosch/ebike/messagebus/`

The core communication layer between the app and all bike components over BLE.
Implements a typed publish-subscribe data bus protocol.

### Entity Proxies

The `MessageBus` class exposes 10 entity proxies:

| Entity                | Represents          | Data Points                                                              |
| --------------------- | ------------------- | ------------------------------------------------------------------------ |
| `DriveUnit`           | Motor/drive unit    | 200+ (assist modes, speed, torque, cadence, bike light, crash detection) |
| `Battery`             | Primary battery     | 80+ (SoC, voltage, temperature, charge cycles)                           |
| `Battery2`            | Secondary battery   | Dual-battery systems                                                     |
| `RemoteControl`       | Handlebar remote    | 300+ (button events, BLE config, software updates, ride stats)           |
| `HeadUnit`            | Display head unit   | Tiles, view stripes, brightness, languages                               |
| `ConnectModule`       | GPS/cellular module | GNSS, modem, remote config                                               |
| `AntiLockBrakeSystem` | ABS module          | Brake events, wheel speeds, ABS modes                                    |
| `MobileApp`           | The phone itself    | Location, altitude, heart rate, navigation (sent TO bike)                |
| `BoschDiagnoseApp`    | Diagnostic app      | Diagnostic interface                                                     |
| `CanTestNode`         | CAN bus test        | CAN bus testing                                                          |

### DataPoint Types

```kotlin
interface DataPoint<T>
interface ReadableDataPoint<T> : DataPoint<T> { suspend fun read(): T }
interface WritableDataPoint<T> : DataPoint<T> { suspend fun write(value: T) }
interface SubscribableDataPoint<T> : DataPoint<T> { fun subscribe(): Flow<T> }
interface CallableDataPoint : DataPoint<*> { suspend fun call(vararg args: Any): Any }
```

### Protocol Layer

**Message types:**

- Outbound: `ReadMessage`, `WriteMessage`, `SubscribeMessage`, `RpcCallMessage`
- Inbound: `ReadResponseMessage`, `WriteResponseMessage`,
  `SubscribeResponseMessage`, `RpcResponseMessage`, `NotifyMessage`

**Gateway/Broker:**

- `Broker` -- Routes messages between MessageBus and BLE transport
- `InternalGateway` -- Encodes/decodes binary protocol

### Addressing

Each entity has an `Addresses` enum with hundreds of named addresses:

**DriveUnitAddresses:**

- `BIKE_SPEED`, `ASSIST_MODE`, `MOTOR_TORQUE`, `CRASH_DETECTION_CONFIG`,
  `BIKE_LIGHT`, `ODO_METER`

**BatteryAddresses:**

- `STATE_OF_CHARGE`, `VOLTAGE`, `CURRENT`, `TEMPERATURE`, `CHARGE_CYCLES`

---

## BES3 (~3,163 files)

**Location:** `smali_classes3/com/bosch/ebike/bes3/` + classes 5-7

BES3 = **Bosch eBike System 3** -- the Protocol Buffers data model for all bike
data.

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
- `TrickStats` -- Jump distance, air time

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

---

## Riding (1,677 files)

**Location:** `smali_classes4/com/bosch/ebike/riding/`

The main ride screen and everything that happens during an active ride.

### Sub-packages

| Sub-package               | Purpose                                                                             |
| ------------------------- | ----------------------------------------------------------------------------------- |
| `views/`                  | `RidingFragment`, `RidingViewModel`, `RidingPagesFragment` (carousel of data pages) |
| `services/hud/`           | Head-up display: assist mode, ride buttons, accessory controls                      |
| `services/performance/`   | Real-time metrics: altitude, ascent, cadence, power                                 |
| `services/fitness/`       | Heart rate sensor integration                                                       |
| `services/navigation/`    | Turn-by-turn navigation status                                                      |
| `services/bike/`          | Bike motion detection, UI priority management                                       |
| `services/orientation/`   | Portrait/landscape handling                                                         |
| `services/pageselection/` | Manages visible ride data pages                                                     |
| `services/notifications/` | In-ride notifications                                                               |
| `services/alerts/`        | Ride alerts (distracted riding)                                                     |
| `eshift/`                 | Electronic gear shifting UI                                                         |
| `walkassist/`             | Walk assist mode controls                                                           |
| `snail/`                  | "Snail mode" -- low-speed/limited assist                                            |
| `options/`                | Ride options panel                                                                  |
| `datasources/`            | Persists riding preferences                                                         |
| `analytics/`              | Ride analytics tracking                                                             |

### Ride State

`RidingViewState` tracks:

- `isStanding` -- Standing detection
- `closeButtonHasBadge` -- Badge on close button
- `isStopButtonAvailable` -- Stop button visibility
- `pageCount` -- Number of data pages
- `currentPage` -- Current page index
- `isUserScrolling` -- User is scrolling pages

---

## Subscription (768 files)

**Location:** `smali_classes4/com/bosch/ebike/subscription/`

Google Play Billing subscription management for Flow+ premium features.

### Architecture

| Sub-package    | Purpose                                                         |
| -------------- | --------------------------------------------------------------- |
| `billing/`     | Google Play Billing Library wrapper                             |
| `services/`    | Business logic: subscription status, eligibility, purchase flow |
| `datasources/` | Local cache, remote API, DTOs                                   |
| `views/`       | UI: feature details, plan selection, pricing, success           |

### Billing Integration

**Key classes:**

- `BillingClientProvider` -- Manages BillingClient connection
- `Connection` -- Sealed class: Connected, Disconnected, Error
- `DoPurchase` -- Initiates purchase flow
- `QueryProduct` -- Queries available products
- `QueryPurchaseHistory` -- Queries purchase history
- `AcknowledgePurchase` -- Acknowledges purchases

**Retry logic:** `BackoffDelayCalculator` for connection retries

### Subscription Status

```kotlin
sealed class SubscriptionStatus {
    object Active : SubscriptionStatus()
    object NotActive : SubscriptionStatus()
}
```

### Purchase Flow

1. User selects plan (monthly/yearly)
2. `DoPurchase` launches Google Play billing flow
3. User completes purchase in Google Play
4. `ProcessPurchaseResult` handles outcome:
   - `Successful` -- Purchase acknowledged
   - `FailedToAcknowledge` -- Acknowledgement failed
   - `FailedToProcess` -- Processing failed
   - `PurchaseMadeOutsideApp` -- Purchase made on another device
5. `SyncPurchasesWithRemote` syncs with backend

### Paywall Model

Flow+ subscription gates:

- Anti-theft alarm features
- `ShouldPromoteFlowPlus` determines when to upsell
- `HardwareAvailabilityService` checks if bike supports features
- `BcmEligibility` checks if Connect Module is present

---

## CloudSync (182 files)

**Location:** `smali_classes3/com/bosch/ebike/cloudsync/`

Synchronizes bike profile data between the app and Bosch backend.

### Data Format

JSON:API format with Kotlin-serialized DTOs.

### DTO Categories

| Category           | Examples                                                                     |
| ------------------ | ---------------------------------------------------------------------------- |
| **Bike Profile**   | `BikeProfileGetDto`, `BikeProfilePostDto`, `BikeRegisterPostDto`             |
| **Drive Unit**     | `DriveUnitGetDto`, `DriveUnitPostDto`, `DriveUnitAssistModesDto`             |
| **Battery**        | `BatteryDto`, `BatteryPostDto`, `NumberOfFullChargeCyclesDto`                |
| **Head Unit**      | `HeadUnitDto`, `HeadUnitPostDto`                                             |
| **Remote Control** | `RemoteControlDto`, `RemoteControlPostDto`                                   |
| **Connect Module** | `ConnectedModuleDto`, `ConnectedModulePostDto`                               |
| **Settings**       | `AdjustmentsDto`, `AlarmFeatureSettingsDto`, `AssistModeDto`, `BikeLightDto` |
| **JSON:API**       | `JsonApiDocument*`, `JsonApiResource*`, `JsonApiRelationship`                |

### Sync Flow

```
1. BLE reads component data via MessageBus
2. Data mapped from BES3 protobuf to CloudSync DTOs
3. DTOs serialized to JSON:API format
4. POST request to Rider Profile API
5. Backend acknowledges
6. CloudSyncRequest deleted from Room
```

---

## Navigation (1,708 files)

**Location:** `smali_classes4/com/bosch/ebike/navigation/`

Turn-by-turn navigation with Mapbox.

### Sub-packages

| Sub-package          | Purpose                               |
| -------------------- | ------------------------------------- |
| `services/`          | Navigation service, route calculation |
| `views/`             | Navigation UI, map overlays           |
| `datasources/`       | Favorite locations, route history     |
| `analytics/`         | Navigation analytics                  |
| `favoritelocations/` | Favorite locations management         |
| `common/`            | Shared navigation utilities           |
| `debug/`             | Debug tools                           |

### Map Integration

Uses Mapbox SDK for:

- Map rendering
- Route display
- Turn-by-turn instructions
- Location tracking

---

## Bike Pairing (558 files)

**Location:** `smali_classes3/com/bosch/ebike/bikepairing/`

Multi-step bike pairing flow.

### Sub-packages

| Sub-package | Purpose                      |
| ----------- | ---------------------------- |
| `services/` | Pairing logic, BLE scanning  |
| `views/`    | Pairing UI, progress screens |

### Pairing Flow

1. Scan for nearby bikes
2. User selects bike
3. Initiate BLE connection
4. Bond with bike (pairing)
5. Read bike info (components, firmware versions)
6. Register bike in cloud
7. Sync bike profile

---

## Bike Settings (1,382 files)

**Location:** `smali_classes3/com/bosch/ebike/bikesettings/`

Bike configuration and settings.

### Sub-packages

| Sub-package | Purpose                            |
| ----------- | ---------------------------------- |
| `services/` | Settings read/write via MessageBus |
| `views/`    | Settings UI                        |
| `bikename/` | Bike name management               |

### Settings

- Assistance modes (customize levels)
- Ride settings (light, walk assist)
- Bike info (name, components)
- Communication settings
- Display configuration

---

## Activity Tracking (1,201 files)

**Location:** `smali_classes2/com/bosch/ebike/activitytracking/`

Ride tracking and statistics.

### Sub-packages

| Sub-package        | Purpose                     |
| ------------------ | --------------------------- |
| `datasources/`     | Room DB, location filters   |
| `services/`        | Ride recording, upload      |
| `views/`           | Ride history, statistics UI |
| `model/`           | Ride data models            |
| `locationfilters/` | GPS data filtering          |
| `optionspanel/`    | Ride options                |
| `provider/`        | Data providers              |
| `settings/`        | Tracking settings           |

### Ride Recording

1. User starts ride
2. Service subscribes to MessageBus data points
3. Per-second telemetry written to ActivityDatabase
4. GPS coordinates recorded
5. Heart rate data recorded (if sensor connected)
6. User stops ride
7. Activity marked complete
8. WorkManager triggers upload
9. Activity uploaded to Ingestion API

---

## Home (2,412 files)

**Location:** `smali_classes3/com/bosch/ebike/home/`

Main dashboard with cards.

### Sub-packages

| Sub-package    | Purpose             |
| -------------- | ------------------- |
| `datasources/` | Card data sources   |
| `services/`    | Card logic, refresh |
| `views/`       | Dashboard UI        |

### Cards

- Battery info (SoC, range)
- Maintenance reminders
- Mileage stats
- Tracking mode status
- Getting started cards
- Bike issues
- App highlights
- Promotions (Flow+, PowerMore, Komoot, BCM)

---

## Further Reading

- [Architecture Overview](architecture.md) -- High-level system design
- [BLE Communication](ble-communication.md) -- How the app talks to the bike
- [Module Catalog](module-catalog.md) -- Complete module listing
